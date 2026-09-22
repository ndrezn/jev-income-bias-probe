#!/usr/bin/env python3
"""Score synthetic applications with TypeSafe Jev, twice per applicant.

Each applicant is sent through the same rubric in two arms:

    without_income  state = {"resume": ...}
    with_income     state = {"resume": ..., "family_annual_income": ...}

The rubric is byte-identical across arms, so the only variable is whether the
income field is present in the state. Pair the two arms with analyze_results.py
to see whether it moved anything.

API: POST https://api.typesafe.ai/v1/systemone   (docs.typesafe.ai/api)

The key is read from TYPESAFE_API_KEY and is never logged or written to output.

    export TYPESAFE_API_KEY=...
    python3 run_screening.py --dry-run          # payload preview, no calls
    python3 run_screening.py --limit 10         # smoke test, 20 calls
    python3 run_screening.py                    # full run, 1000 calls
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DEFAULT_BASE_URL = "https://api.typesafe.ai"
ENDPOINT_PATH = "/v1/systemone"
DEFAULT_MODEL = "jev-latest"
ARMS = ("without_income", "with_income")

# Retry on rate limit, overload, and transient server errors, per the API docs.
RETRY_STATUS = {408, 429, 500, 502, 503, 504, 529}
# Published input price: $0.042 per million input tokens. Output is unmetered.
USD_PER_INPUT_TOKEN = 0.042 / 1_000_000


def load_dotenv(path: Path) -> None:
    """Populate os.environ from a KEY=VALUE file. Existing vars win."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().removeprefix("export ").strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


class RateLimiter:
    """Token bucket shared by every worker thread."""

    def __init__(self, rate_per_sec: float) -> None:
        self.rate = rate_per_sec
        self.lock = threading.Lock()
        self.next_slot = time.monotonic()

    def acquire(self) -> None:
        if self.rate <= 0:
            return
        with self.lock:
            now = time.monotonic()
            self.next_slot = max(now, self.next_slot) + 1.0 / self.rate
            wait = self.next_slot - now
        if wait > 0:
            time.sleep(wait)


def validate_rubric(rubric: dict) -> None:
    """Fail before spending money on a malformed rubric."""
    problems = []
    for key, q in rubric.items():
        qtype = q.get("type")
        if qtype not in ("score", "noul", "choice"):
            problems.append(f"{key}: unknown type {qtype!r}")
            continue
        if not q.get("instructions"):
            problems.append(f"{key}: missing instructions")
        criteria = q.get("criteria")
        if qtype == "score":
            if not isinstance(criteria, list) or not 2 <= len(criteria) <= 10:
                problems.append(f"{key}: score needs a list of 2-10 criteria")
        elif qtype == "choice":
            if not isinstance(criteria, dict) or len(criteria) < 2:
                problems.append(f"{key}: choice needs a dict of 2+ criteria")
        elif qtype == "noul" and criteria is not None and not isinstance(criteria, dict):
            problems.append(f"{key}: noul criteria must be a dict of true/false")
    if problems:
        raise SystemExit("Invalid rubric:\n  " + "\n  ".join(problems))


def build_state(record: dict, arm: str) -> dict:
    state = {"resume": record["resume"]}
    if arm == "with_income":
        state["family_annual_income"] = record["family_annual_income"]
    return state


def post(url: str, payload: dict, api_key: str, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "harvard-admissions-bias-probe/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def call_with_retries(url: str, payload: dict, api_key: str, args) -> tuple[dict | None, str | None, int]:
    """Return (response, error, attempts). Retries only transient failures."""
    delay = args.backoff
    for attempt in range(1, args.max_retries + 2):
        try:
            return post(url, payload, api_key, args.timeout), None, attempt
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            if exc.code not in RETRY_STATUS or attempt > args.max_retries:
                return None, f"HTTP {exc.code}: {detail}", attempt
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            sleep_for = float(retry_after) if (retry_after or "").replace(".", "", 1).isdigit() else delay
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt > args.max_retries:
                return None, f"{type(exc).__name__}: {exc}", attempt
            sleep_for = delay
        time.sleep(sleep_for * random.uniform(0.7, 1.3))
        delay = min(delay * 2, args.backoff_max)
    return None, "exhausted retries", args.max_retries + 1


def flatten_answers(answers: dict) -> dict:
    """One flat row per call: a value and a confidence per question."""
    flat = {}
    for key, answer in answers.items():
        kind = answer.get("type")
        if kind == "score":
            flat[key] = answer.get("score")
            flat[f"{key}__confidence"] = answer.get("confidence")
        elif kind == "noul":
            flat[key] = answer.get("noul")
        elif kind == "choice":
            flat[key] = answer.get("choice")
            flat[f"{key}__confidence"] = answer.get("confidence")
        else:
            flat[key] = answer
    return flat


def load_done(path: Path) -> set[tuple[str, str]]:
    """Completed (applicant_id, arm) pairs, so a rerun does not re-bill them."""
    done = set()
    if not path.exists():
        return done
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("error") is None:
                done.add((row["applicant_id"], row["arm"]))
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    here = Path(__file__).parent
    parser.add_argument("--applications", type=Path, default=here / "applications.json")
    parser.add_argument("--rubric", type=Path, default=here / "rubrics" / "admission_rubric.json")
    parser.add_argument("--out", type=Path, default=here / "results" / "screening.jsonl")
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    parser.add_argument("--limit", type=int, help="only the first N applicants")
    parser.add_argument("--model", default=os.environ.get("TYPESAFE_DEFAULT_MODEL", DEFAULT_MODEL))
    parser.add_argument("--base-url", default=os.environ.get("TYPESAFE_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--rps", type=float, default=10.0, help="request ceiling per second (0 = unlimited)")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--backoff", type=float, default=1.0)
    parser.add_argument("--backoff-max", type=float, default=30.0)
    parser.add_argument("--no-resume", action="store_true",
                        help="ignore existing results and redo every call")
    parser.add_argument("--dry-run", action="store_true",
                        help="print one payload and exit without calling")
    parser.add_argument("--allow-insecure-base-url", action="store_true",
                        help="permit an http:// base URL, for testing against a local mock only")
    parser.add_argument("--env-file", type=Path, default=here / ".env",
                        help="file holding TYPESAFE_API_KEY (default: .env beside this script)")
    args = parser.parse_args()
    load_dotenv(args.env_file)
    if args.model == DEFAULT_MODEL:
        args.model = os.environ.get("TYPESAFE_DEFAULT_MODEL", DEFAULT_MODEL)
    if args.base_url == DEFAULT_BASE_URL:
        args.base_url = os.environ.get("TYPESAFE_BASE_URL", DEFAULT_BASE_URL)

    records = json.loads(args.applications.read_text(encoding="utf-8"))
    if args.limit:
        records = records[: args.limit]
    rubric = json.loads(args.rubric.read_text(encoding="utf-8"))
    validate_rubric(rubric)

    url = args.base_url.rstrip("/") + ENDPOINT_PATH
    if not url.startswith("https://") and not args.allow_insecure_base_url:
        raise SystemExit(f"refusing to send applications over a non-HTTPS URL: {url}\n"
                         "pass --allow-insecure-base-url only for a local mock")

    if args.dry_run:
        preview = {"model": args.model, "state": build_state(records[0], "with_income"), "questions": rubric}
        print(f"POST {url}")
        print("Authorization: Bearer ***redacted***")
        print("Content-Type: application/json\n")
        print(json.dumps(preview, indent=2, ensure_ascii=False)[:2500] + "\n...")
        print(f"\n{len(records)} applicants x {len(args.arms)} arms = "
              f"{len(records) * len(args.arms)} requests against {len(rubric)} questions each")
        return

    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        raise SystemExit(f"TYPESAFE_API_KEY not found in the environment or {args.env_file}. "
                         "Keys are read from there only, never from the command line.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = set() if args.no_resume else load_done(args.out)
    jobs = [(r, arm) for r in records for arm in args.arms if (r["applicant_id"], arm) not in done]
    if done:
        print(f"resuming: {len(done)} calls already complete, {len(jobs)} to go")
    if not jobs:
        print("nothing to do")
        return

    limiter = RateLimiter(args.rps)
    write_lock = threading.Lock()
    counters = {"ok": 0, "failed": 0, "input_tokens": 0}
    started = time.monotonic()

    def run_one(record: dict, arm: str) -> dict:
        payload = {"model": args.model, "state": build_state(record, arm), "questions": rubric}
        limiter.acquire()
        t0 = time.monotonic()
        response, error, attempts = call_with_retries(url, payload, api_key, args)
        latency_ms = round((time.monotonic() - t0) * 1000)
        row = {
            "applicant_id": record["applicant_id"],
            "arm": arm,
            "family_annual_income": record["family_annual_income"],
            # Ground-truth strength label, carried through for analysis only.
            # build_state never puts it in the state sent to the model.
            "strength_tier": record.get("strength_tier"),
            "model": (response or {}).get("model", args.model),
            "latency_ms": latency_ms,
            "attempts": attempts,
            "error": error,
        }
        if response:
            row.update(flatten_answers(response.get("answers", {})))
            row["usage"] = response.get("usage")
        return row

    mode = "w" if args.no_resume else "a"
    with open(args.out, mode, encoding="utf-8") as fh, \
            ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(run_one, record, arm): (record["applicant_id"], arm)
                   for record, arm in jobs}
        for i, future in enumerate(as_completed(futures), start=1):
            applicant_id, arm = futures[future]
            try:
                row = future.result()
            except Exception as exc:  # a bug in run_one, not an API failure
                row = {"applicant_id": applicant_id, "arm": arm,
                       "error": f"{type(exc).__name__}: {exc}"}
            with write_lock:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                if row.get("error"):
                    counters["failed"] += 1
                    print(f"  [{i}/{len(jobs)}] {applicant_id} {arm} FAILED: {row['error'][:120]}",
                          file=sys.stderr)
                else:
                    counters["ok"] += 1
                    counters["input_tokens"] += (row.get("usage") or {}).get("input_tokens", 0)
                if i % 50 == 0 or i == len(jobs):
                    rate = i / max(time.monotonic() - started, 1e-6)
                    print(f"  [{i}/{len(jobs)}] ok={counters['ok']} failed={counters['failed']} "
                          f"{rate:.1f} req/s")

    elapsed = time.monotonic() - started
    print(f"\ndone in {elapsed:.0f}s: {counters['ok']} ok, {counters['failed']} failed -> {args.out}")
    if counters["input_tokens"]:
        print(f"input tokens: {counters['input_tokens']:,} "
              f"(about ${counters['input_tokens'] * USD_PER_INPUT_TOKEN:.2f} at list price)")
    if counters["failed"]:
        print("rerun the same command to retry only the failed calls")


if __name__ == "__main__":
    main()
