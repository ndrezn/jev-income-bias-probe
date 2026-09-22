#!/usr/bin/env python3
"""Render the screening comparison in results/ as static PNG charts.

Reads results/summary.json and results/per_applicant_deltas.csv (both written
by analyze_results.py) and writes PNGs into charts/. Every chart plots the
paired delta, with_income minus without_income, on the same applicant. The
delta is what isolates the income field: the resume is byte-identical on both
sides, so anything that moves is the field and not the applicant.

    uv run --group charts python make_charts.py
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots

SUMMARY = Path("results/summary.json")
DELTAS = Path("results/per_applicant_deltas.csv")
OUT_DIR = Path("charts")

# Kaleido renders one PNG per figure; a runaway input would otherwise spawn
# unbounded work, so cap what we will read and draw.
MAX_APPLICANTS = 50_000
MAX_SUMMARY_BYTES = 8 * 1024 * 1024

SCALE_MAX = {  # score questions, from the rubric's criteria count
    "academic_strength": 5,
    "extracurricular_distinction": 5,
    "leadership_and_initiative": 5,
    "overall_applicant_quality": 5,
    "rigor_relative_to_opportunity": 4,
    "intellectual_curiosity": 4,
    "impact_on_others": 4,
}
STRENGTH_ORDER = ["limited", "developing", "solid", "strong", "elite"]

NOUL_FIELDS = [
    "sustained_commitment",
    "founded_something",
    "research_experience",
    "external_recognition",
    "significant_work_or_family_responsibility",
    "evidence_of_constrained_resources",
]

INK = "#1f2933"
MUTED = "#8a94a6"
GRID = "#e4e7eb"
WARM = "#c05621"   # movement that favors higher income
COOL = "#2b6cb0"   # movement that favors lower income
NEUTRAL = "#4a5568"

LAYOUT = dict(
    template="plotly_white",
    font=dict(family="Helvetica Neue, Helvetica, Arial, sans-serif", size=13, color=INK),
    title=dict(font=dict(size=18), x=0, xanchor="left"),
    margin=dict(l=90, r=40, t=90, b=70),
    paper_bgcolor="white",
    plot_bgcolor="white",
    showlegend=False,
)


def label(field: str) -> str:
    return field.replace("_", " ")


def load_summary(path: Path) -> dict:
    if not path.exists():
        msg = f"{path} not found; run analyze_results.py first"
        raise FileNotFoundError(msg)
    size = path.stat().st_size
    if size > MAX_SUMMARY_BYTES:
        msg = f"{path} is {size} bytes, above the {MAX_SUMMARY_BYTES} byte limit"
        raise ValueError(msg)
    return json.loads(path.read_text(encoding="utf-8"))


def load_deltas(path: Path) -> list[dict]:
    if not path.exists():
        msg = f"{path} not found; run analyze_results.py first"
        raise FileNotFoundError(msg)
    rows = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if len(rows) >= MAX_APPLICANTS:
                msg = f"{path} holds more than {MAX_APPLICANTS} rows"
                raise ValueError(msg)
            rows.append(row)
    return rows


def styled(fig: go.Figure, title: str, subtitle: str) -> go.Figure:
    fig.update_layout(**LAYOUT)
    fig.update_layout(title_text=f"{title}<br><span style='font-size:13px;color:{MUTED}'>{subtitle}</span>")
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID)
    return fig


def legend_below(fig: go.Figure) -> None:
    """Park the legend under the x axis, clear of the title block."""
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation="h", y=-0.22, yanchor="top", x=0.5, xanchor="center"),
        margin=dict(l=fig.layout.margin.l, r=fig.layout.margin.r,
                    t=fig.layout.margin.t, b=120),
    )


def save(fig: go.Figure, out_dir: Path, name: str, width: int, height: int) -> Path:
    path = out_dir / name
    fig.write_image(path, width=width, height=height, scale=2)
    return path


def chart_quality_gradient(summary: dict) -> go.Figure:
    """Score movement across income quintiles for the two headline questions."""
    quintiles = [f"Q{q['quintile']}" for q in summary["admit_rate_by_income_quintile"]]
    by_q = summary["delta_by_income_quintile"]
    fig = go.Figure()
    # The two lines cross at Q3, so park each label on the side its line is free.
    positions = {"overall_applicant_quality": "bottom center", "academic_strength": "top center"}
    for field, color in (("overall_applicant_quality", WARM), ("academic_strength", NEUTRAL)):
        values = by_q[field]
        fig.add_trace(go.Scatter(
            x=quintiles, y=values, name=label(field), mode="lines+markers+text",
            line=dict(color=color, width=2.5), marker=dict(size=9, color=color),
            text=[f"{v:+.3f}" for v in values], textposition=positions[field],
            textfont=dict(size=11, color=color), cliponaxis=False,
        ))
        fig.add_annotation(x=quintiles[-1], y=values[-1], text=label(field),
                           xanchor="left", xshift=16, showarrow=False,
                           font=dict(size=12, color=color))
    fig.add_hline(y=0, line=dict(color=MUTED, width=1))
    styled(fig, "Showing income moves scores along an income gradient",
           "Mean paired delta (with income minus without), by income quintile, 0–5 scale")
    fig.update_layout(margin=dict(l=90, r=210, t=90, b=70))
    fig.update_yaxes(title_text="mean score delta", tickformat="+.3f")
    fig.update_xaxes(title_text="family income quintile (Q1 lowest)")
    return fig


def chart_field_deltas(summary: dict) -> go.Figure:
    """Every question's mean delta with its bootstrap CI.

    Score questions and probability claims sit on different scales, so they get
    their own panel and their own x axis rather than one misleading shared one.
    """
    fields = summary["numeric_fields"]
    panels = [
        ("Score questions (0\u20135 scale)", sorted((f for f in fields if f in SCALE_MAX),
                                                    key=lambda f: fields[f]["mean_delta"])),
        ("Probability claims (0\u20131)", sorted((f for f in fields if f in NOUL_FIELDS),
                                                 key=lambda f: fields[f]["mean_delta"])),
    ]
    heights = [len(names) for _, names in panels]
    fig = make_subplots(rows=2, cols=1, vertical_spacing=0.12,
                        row_heights=[h / sum(heights) for h in heights],
                        subplot_titles=[title for title, _ in panels])

    for row, (_, names) in enumerate(panels, start=1):
        ys, xs, lo, hi, colors = [], [], [], [], []
        for field in names:
            stats = fields[field]
            ys.append(label(field))
            xs.append(stats["mean_delta"])
            lo.append(stats["mean_delta"] - stats["ci95"][0])
            hi.append(stats["ci95"][1] - stats["mean_delta"])
            crosses_zero = stats["ci95"][0] <= 0 <= stats["ci95"][1]
            colors.append(MUTED if crosses_zero else (WARM if stats["mean_delta"] > 0 else COOL))
        fig.add_trace(go.Bar(
            x=xs, y=ys, orientation="h", marker=dict(color=colors),
            error_x=dict(type="data", symmetric=False, array=hi, arrayminus=lo,
                         color=INK, thickness=1.2, width=4),
        ), row=row, col=1)
        fig.add_vline(x=0, line=dict(color=INK, width=1), row=row, col=1)

    styled(fig, "What the income field moved, question by question",
           "Mean paired delta with 95% bootstrap CI. Orange moved up, blue down, grey crosses zero.")
    fig.update_layout(margin=dict(l=250, r=60, t=110, b=70))
    for note in fig.layout.annotations:
        note.update(x=0, xanchor="left", font=dict(size=13, color=MUTED))
    fig.update_xaxes(title_text="mean delta (with income minus without)", row=2, col=1)
    return fig


def chart_constrained_resources(summary: dict) -> go.Figure:
    """The one field where reading income is the point, not leakage."""
    quintiles = [f"Q{q['quintile']}" for q in summary["admit_rate_by_income_quintile"]]
    values = summary["delta_by_income_quintile"]["evidence_of_constrained_resources"]
    colors = [COOL if v > 0 else WARM for v in values]
    fig = go.Figure(go.Bar(
        x=quintiles, y=values, marker=dict(color=colors),
        text=[f"{v:+.3f}" for v in values], textposition="outside",
        textfont=dict(size=12, color=INK),
    ))
    fig.add_hline(y=0, line=dict(color=INK, width=1))
    styled(fig, "Legitimate use: constrained-resources claim tracks income",
           "Mean paired delta in P(evidence of constrained resources), by income quintile")
    fig.update_yaxes(title_text="mean probability delta", tickformat="+.2f")
    fig.update_xaxes(title_text="family income quintile (Q1 lowest)")
    return fig


def chart_income_scatter(summary: dict, rows: list[dict]) -> go.Figure:
    """Per-applicant delta against income, the shape behind the r."""
    points = sorted(((float(r["family_annual_income"]), float(r["overall_quality_delta"]))
                     for r in rows), key=lambda pair: pair[0])
    incomes = [income for income, _ in points]
    deltas = [delta for _, delta in points]
    r_value = summary["income_correlation"]["overall_quality_delta_r"]

    # Decile means, so the gradient the r reports is visible under the jitter.
    bins = 10
    size = len(points) / bins
    bin_x, bin_y = [], []
    for i in range(bins):
        chunk = points[int(i * size):int((i + 1) * size)]
        if not chunk:
            continue
        bin_x.append(statistics.median(income for income, _ in chunk))
        bin_y.append(statistics.fmean(delta for _, delta in chunk))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=incomes, y=deltas, mode="markers", name="applicant",
        marker=dict(size=6, color=NEUTRAL, opacity=0.35, line=dict(width=0)),
    ))
    fig.add_trace(go.Scatter(
        x=bin_x, y=bin_y, mode="lines+markers", name="decile mean",
        line=dict(color=WARM, width=2.5), marker=dict(size=8, color=WARM),
    ))
    fig.add_hline(y=0, line=dict(color=INK, width=1))
    fig.add_annotation(x=0.02, xref="paper", y=0.97, yref="paper", showarrow=False,
                       xanchor="left", align="left", font=dict(size=13, color=INK),
                       text=f"r = {r_value:.3f}  \u00b7  n = {len(points)}")
    styled(fig, "Per-applicant quality delta against family income",
           "Each grey point is one applicant scored twice. Above the line, income helped them.")
    legend_below(fig)
    fig.update_xaxes(title_text="family annual income (USD, log scale)", type="log",
                     tickvals=[10_000, 30_000, 100_000, 300_000, 1_000_000],
                     ticktext=["$10k", "$30k", "$100k", "$300k", "$1M"])
    fig.update_yaxes(title_text="overall quality delta", tickformat="+.2f", dtick=0.05)
    return fig


def chart_admit_by_quintile(summary: dict) -> go.Figure:
    """The recommendation field across income, now that it has a floor."""
    quintiles = summary["admit_rate_by_income_quintile"]
    labels = [f"Q{q['quintile']}" for q in quintiles]
    series = [
        ("admit or better, without income", "admit_or_better_without_income", MUTED),
        ("admit or better, with income", "admit_or_better_with_income", WARM),
        ("strong admit, without income", "strong_admit_without_income", "#c3cad6"),
        ("strong admit, with income", "strong_admit_with_income", "#e9b08a"),
    ]
    fig = go.Figure()
    for name, key, color in series:
        values = [q[key] for q in quintiles]
        fig.add_trace(go.Bar(x=labels, y=values, name=name, marker_color=color,
                             text=[f"{v:.0%}" for v in values], textposition="outside",
                             textfont=dict(size=10, color=INK)))
    styled(fig, "Admission recommendation by income quintile",
           "Both bands now vary, so the question is measuring something")
    fig.update_layout(barmode="group")
    legend_below(fig)
    fig.update_yaxes(title_text="share of applicants", tickformat=".0%", range=[0, 1.0])
    fig.update_xaxes(title_text="family income quintile (Q1 lowest)")
    return fig


def chart_strength_discrimination(summary: dict) -> go.Figure:
    """Ground truth against outcome: does the rubric separate the tiers?"""
    rows = [r for tier in STRENGTH_ORDER
            for r in summary.get("outcome_by_strength_tier", []) if r["tier"] == tier]
    if not rows:
        return None
    labels = [r["tier"] for r in rows]
    admit = [r["admit_or_better_without_income"] for r in rows]
    strong = [r["strong_admit_without_income"] for r in rows]
    quality = [r["mean_overall_quality_without_income"] for r in rows]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=labels, y=admit, name="admit or better", marker_color=MUTED,
                         text=[f"{v:.0%}" for v in admit], textposition="outside",
                         textfont=dict(size=11, color=INK)), secondary_y=False)
    fig.add_trace(go.Bar(x=labels, y=strong, name="strong admit", marker_color=WARM,
                         text=[f"{v:.0%}" for v in strong], textposition="outside",
                         textfont=dict(size=11, color=WARM)), secondary_y=False)
    fig.add_trace(go.Scatter(x=labels, y=quality, name="mean overall quality (right axis)",
                             mode="lines+markers", line=dict(color=INK, width=2, dash="dot"),
                             marker=dict(size=8, color=INK)), secondary_y=True)
    styled(fig, "The rubric separates the generator's strength tiers",
           "Without-income arm. Tier is ground truth and is never sent to the model.")
    fig.update_layout(barmode="group")
    legend_below(fig)
    fig.update_yaxes(title_text="share of applicants", tickformat=".0%",
                     range=[0, 1.15], secondary_y=False)
    fig.update_yaxes(title_text="mean overall quality (0\u20135)", range=[0, 5],
                     showgrid=False, secondary_y=True)
    fig.update_xaxes(title_text="generator strength tier")
    return fig


def chart_gap_by_strength(summary: dict) -> go.Figure:
    """Where the leak lives: the Q1-to-Q5 spread inside each strength tier."""
    data = summary.get("quality_delta_by_strength_tier", {})
    rows = [(tier, data[tier]) for tier in STRENGTH_ORDER if tier in data]
    if not rows:
        return None
    labels = [tier for tier, _ in rows]
    low = [r["q1_mean_delta"] for _, r in rows]
    high = [r["q5_mean_delta"] for _, r in rows]

    fig = go.Figure()
    for x, lo, hi in zip(labels, low, high, strict=True):
        fig.add_trace(go.Scatter(x=[x, x], y=[lo, hi], mode="lines",
                                 line=dict(color=GRID, width=3), showlegend=False))
    fig.add_trace(go.Scatter(x=labels, y=low, mode="markers", name="lowest income quintile",
                             marker=dict(size=13, color=COOL)))
    fig.add_trace(go.Scatter(x=labels, y=high, mode="markers", name="highest income quintile",
                             marker=dict(size=13, color=WARM)))
    fig.add_hline(y=0, line=dict(color=INK, width=1))
    styled(fig, "The income effect concentrates in the middle of the range",
           "Mean paired quality delta for the bottom and top income quintile, within each tier")
    legend_below(fig)
    fig.update_yaxes(title_text="mean quality delta", tickformat="+.2f")
    fig.update_xaxes(title_text="generator strength tier")
    return fig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--summary", type=Path, default=SUMMARY)
    parser.add_argument("--deltas", type=Path, default=DELTAS)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    summary = load_summary(args.summary)
    rows = load_deltas(args.deltas)
    args.out.mkdir(parents=True, exist_ok=True)

    figures = [
        ("quality_by_income_quintile.png", chart_quality_gradient(summary), 900, 520),
        ("delta_by_question.png", chart_field_deltas(summary), 950, 640),
        ("constrained_resources_by_quintile.png", chart_constrained_resources(summary), 820, 500),
        ("quality_delta_vs_income.png", chart_income_scatter(summary, rows), 900, 600),
        ("admit_by_income_quintile.png", chart_admit_by_quintile(summary), 940, 620),
        ("rubric_discrimination.png", chart_strength_discrimination(summary), 900, 600),
        ("gap_by_strength_tier.png", chart_gap_by_strength(summary), 880, 580),
    ]
    for name, fig, width, height in figures:
        if fig is None:
            print(f"skipped {name}: results/summary.json has no strength-tier data")
            continue
        path = save(fig, args.out, name, width, height)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
