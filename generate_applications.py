#!/usr/bin/env python3
"""Generate synthetic college admissions applications (Harvard, fictional).

Every value is fabricated. Names, schools, emails, scores, activities, and
incomes are composed from hardcoded word lists under a fixed seed, so the
output is reproducible and contains no real person's data.

Usage:
    python3 generate_applications.py --count 500 --seed 20260917
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

# --------------------------------------------------------------------------
# Name, place, and school pools
# --------------------------------------------------------------------------

FIRST_NAMES = [
    "Amara", "Sasha", "Diego", "Priya", "Noor", "Elena", "Jomar", "Kaito",
    "Linnea", "Tariq", "Imani", "Rafael", "Yusuf", "Marisol", "Dmitri",
    "Aoife", "Chidi", "Hana", "Ravi", "Beatriz", "Soren", "Nadia", "Mateo",
    "Ingrid", "Kwame", "Lucia", "Ozan", "Talia", "Bodhi", "Camille",
    "Anaya", "Ezra", "Freya", "Gustavo", "Halima", "Ignacio", "Juno",
    "Keziah", "Leilani", "Milo", "Nikhil", "Octavia", "Paloma", "Quinn",
    "Rhea", "Sebastián", "Thandiwe", "Ulises", "Vera", "Wren", "Xiomara",
    "Yara", "Zeke", "Amira", "Bennet", "Cosima", "Dara", "Esme", "Fidel",
    "Giulia", "Hassan", "Isolde", "Jonah", "Kenji", "Lior", "Mireille",
    "Nasir", "Odalys", "Petra", "Rasheed", "Saoirse", "Tomas", "Ume",
    "Valentina", "Wei", "Yannick", "Zainab", "Arjun", "Blythe", "Caspian",
    "Delphine", "Emeka", "Fatima", "Gideon", "Hyewon", "Ilya", "Jaylen",
]

LAST_NAMES = [
    "Bernoulli", "Okonkwo", "Vasquez", "Nakamura", "Lindqvist", "Al-Rashid",
    "Fitzgerald", "Moreau", "Petrov", "Santos", "Adeyemi", "Kowalski",
    "Bianchi", "Haddad", "O'Sullivan", "Marchetti", "Delgado", "Ferreira",
    "Ivanova", "Thakur", "Mbeki", "Larsen", "Castellanos", "Reyes",
    "Novotny", "Abara", "Hoffmann", "Duarte", "Sinclair", "Radhakrishnan",
    "Whitfield", "Zhao", "Sandoval", "Beaumont", "Oyelaran", "Kessler",
    "Amadi", "Villanueva", "Tanaka", "Brennan", "Solberg", "Khoury",
    "Escobar", "Nurmi", "Bhattacharya", "Lindgren", "Mensah", "Carrasco",
    "Weiss", "Ferrante", "Osei", "Kapoor", "Blomqvist", "Montoya",
    "Achebe", "Rosenthal", "Iglesias", "Yamamoto", "Dziedzic", "Bakker",
    "Traoré", "Calderón", "Hensley", "Nwachukwu", "Sørensen", "Barrientos",
    "Chaudhry", "Marchand", "Okafor", "Pereira", "Rautio", "Silvestri",
]

CITIES = [
    ("San Francisco", "CA"), ("Austin", "TX"), ("Columbus", "OH"),
    ("Raleigh", "NC"), ("Providence", "RI"), ("Boise", "ID"),
    ("Tulsa", "OK"), ("Fresno", "CA"), ("Ann Arbor", "MI"),
    ("Scranton", "PA"), ("Savannah", "GA"), ("Laredo", "TX"),
    ("Spokane", "WA"), ("Burlington", "VT"), ("Gary", "IN"),
    ("Flagstaff", "AZ"), ("Shreveport", "LA"), ("Bozeman", "MT"),
    ("Dearborn", "MI"), ("Cambridge", "MA"), ("Bronx", "NY"),
    ("Brooklyn", "NY"), ("Newark", "NJ"), ("Miami", "FL"),
    ("Des Moines", "IA"), ("Lincoln", "NE"), ("Chattanooga", "TN"),
    ("Albuquerque", "NM"), ("Anchorage", "AK"), ("Honolulu", "HI"),
    ("Charleston", "WV"), ("Sioux Falls", "SD"), ("Bentonville", "AR"),
    ("Yakima", "WA"), ("Camden", "NJ"), ("Lowell", "MA"),
    ("Greeley", "CO"), ("Kalamazoo", "MI"), ("Macon", "GA"),
    ("Pawtucket", "RI"), ("Nogales", "AZ"), ("Bakersfield", "CA"),
]

SCHOOL_STEMS = [
    "Westbrook", "Oakridge", "Cedar Hollow", "Northgate", "Lakeshore",
    "Riverton", "Hillcrest", "Fairmont", "Stonebridge", "Brookfield",
    "Ashland", "Maplewood", "Sunnyvale", "Clearwater", "Ironwood",
    "Kingsley", "Alderbrook", "Granite Peak", "Willow Creek", "Harborview",
    "Pinecrest", "Silverton", "Eastvale", "Marbury", "Thornfield",
]

SCHOOL_TYPES_BY_TIER = {
    "low": [
        "{stem} High School", "{city} Public High School",
        "{stem} Community High School", "{city} Early College High School",
    ],
    "mid": [
        "{stem} High School", "{stem} Senior High School",
        "{city} Magnet High School", "{stem} STEM Academy",
        "{city} School for Science and Technology",
    ],
    "high": [
        "{stem} Preparatory School", "{stem} Academy",
        "{stem} Country Day School", "{stem} Latin School",
        "{stem} Friends School",
    ],
}

# --------------------------------------------------------------------------
# Income tiers. Weights approximate the skew of a selective applicant pool:
# a long low-income tail, a thick upper-middle band, and a small very high
# band. Tier also nudges school type and test scores, so the data set has a
# mild, deliberate income signal for fairness testing. It is synthetic and
# is NOT evidence about real admissions.
# --------------------------------------------------------------------------

INCOME_TIERS = [
    ("low", 0.09, 8_000, 32_000, -55, "low"),
    ("lower_mid", 0.14, 32_000, 65_000, -30, "low"),
    ("mid", 0.20, 65_000, 105_000, -10, "mid"),
    ("upper_mid", 0.22, 105_000, 165_000, 10, "mid"),
    ("affluent", 0.16, 165_000, 255_000, 25, "mid"),
    ("high", 0.12, 255_000, 520_000, 40, "high"),
    ("very_high", 0.07, 520_000, 2_400_000, 50, "high"),
]

AP_COURSES = [
    "AP Calculus BC", "AP Physics C: Mechanics", "AP Chemistry", "AP Biology",
    "AP Statistics", "AP Computer Science A", "AP English Literature",
    "AP English Language", "AP U.S. History", "AP World History",
    "AP Comparative Government", "AP Macroeconomics", "AP Psychology",
    "AP Spanish Language", "AP French Language", "AP Latin",
    "AP Environmental Science", "AP Art History", "AP Music Theory",
    "AP Studio Art: 2-D Design", "AP Human Geography", "AP Microeconomics",
]

DUAL_ENROLLMENT = [
    "Multivariable Calculus (dual enrollment, {city} Community College)",
    "Linear Algebra (dual enrollment, state university extension)",
    "Organic Chemistry I (dual enrollment)",
    "Introduction to Political Theory (dual enrollment)",
    "Discrete Mathematics (dual enrollment)",
    "Microbiology (dual enrollment)",
]

# --------------------------------------------------------------------------
# Applicant archetypes
# --------------------------------------------------------------------------

ARCHETYPES = {
    "stem_research": {
        "clubs": ["Science Club", "Math Team", "Environmental Club", "Health Careers Club"],
        "majors": ["Molecular and Cellular Biology", "Chemistry", "Physics",
                   "Neuroscience", "Chemical and Physical Biology"],
        "summary": [
            "Prospective {major} concentrator with {n1} semesters of wet-lab research experience and a first-author poster at a regional symposium.",
            "Student researcher focused on {topic}, with independent lab work sustained across {n1} summers and a published abstract.",
            "Aspiring {major} concentrator whose independent research on {topic} advanced to state-level science fair competition.",
        ],
        "topics": ["antibiotic resistance in soil bacteria", "microplastic uptake in freshwater invertebrates",
                   "CRISPR knockouts in zebrafish pigment genes", "perovskite solar cell degradation",
                   "tardigrade desiccation tolerance", "protein folding kinetics"],
        "activities": [
            {"role": "Student Researcher", "org": "{stem} University Summer Research Program",
             "bullets": [
                 "Designed and ran {n1} independent assays investigating {topic}, logging {n3} hours of bench work across the summer",
                 "Presented findings as a first-author poster to a review panel of {n2} faculty and graduate students",
                 "Processed and analyzed a {n4}-sample dataset in Python (pandas, SciPy), writing the group's reusable analysis notebook",
             ]},
            {"role": "Co-President", "org": "Science Olympiad",
             "bullets": [
                 "Led a {n2}-member team to a top-{n1} state finish, personally medaling in {n1} events",
                 "Built a practice-exam bank of {n4} questions now used by {n1} feeder middle schools",
                 "Recruited {n2} underclassmen, growing the club {pct1}% year over year",
             ]},
            {"role": "Founder", "org": "Peer Lab Skills Workshop",
             "bullets": [
                 "Taught micropipetting, gel electrophoresis, and lab-notebook practice to {n3} students with no prior lab access",
                 "Secured {amt1} dollars in donated consumables from a local hospital lab",
             ]},
            {"role": "Volunteer", "org": "{city} Regional Hospital",
             "bullets": [
                 "Logged {n3} hours in patient transport and the outpatient pharmacy over {n1} years",
                 "Translated intake paperwork for non-English-speaking families across {n1} shifts per week",
             ]},
            {"role": "Editor", "org": "High School Journal of Student Research",
             "bullets": [
                 "Founded a peer-reviewed student journal; edited {n2} submissions across {n1} issues",
                 "Recruited {n1} faculty advisors to serve as reviewers",
             ]},
        ],
        "awards": [
            "Regeneron Science Talent Search — Scholar ({year})",
            "State Science and Engineering Fair — {place} Place, Biochemistry ({year})",
            "National Merit {merit}",
            "AP Scholar with Distinction ({year})",
            "Science Olympiad State Medalist, {n1} events ({year})",
            "Regional Junior Academy of Science — Outstanding Paper ({year})",
        ],
        "skills": "Laboratory: PCR, gel electrophoresis, cell culture, spectrophotometry, titration\nComputational: Python (pandas, NumPy, SciPy, Matplotlib), R, ImageJ, LaTeX\nOther: Scientific writing, poster design, literature review",
    },
    "cs_builder": {
        "clubs": ["Computer Club", "Robotics Club", "Esports Team", "Technology Student Association chapter"],
        "majors": ["Computer Science", "Applied Mathematics", "Electrical Engineering",
                   "Statistics", "Computer Science and Economics"],
        "summary": [
            "Prospective {major} concentrator who ships: {n4} users on a self-built {topic}, plus {n2} merged pull requests to open source projects.",
            "Self-taught engineer building {topic}, with {n1} hackathon wins and sustained open source contribution.",
            "Aspiring {major} concentrator focused on {topic} and on getting other students their first programming job.",
        ],
        "topics": ["a school bus tracking app", "an open-source scheduling tool for food banks",
                   "a computer vision model for wildfire smoke detection", "a text-to-speech reader for dyslexic students",
                   "a transit accessibility map", "a local-first note-taking app"],
        "activities": [
            {"role": "Founder and Lead Developer", "org": "{topic_title}",
             "bullets": [
                 "Built and shipped {topic} used by {n4} students and families across {n1} school districts",
                 "Wrote the full stack solo: React front end, Python/FastAPI back end, PostgreSQL, deployed on a {amt1}-dollar annual budget",
                 "Cut median page load from {n2}00ms to under {n1}00ms through query batching and caching",
             ]},
            {"role": "Captain", "org": "Competitive Programming Team",
             "bullets": [
                 "Placed top {n1} at the state ACSL finals; qualified {n1} consecutive years for USACO Gold",
                 "Ran weekly practice for {n2} members and wrote {n3} annotated editorial solutions",
             ]},
            {"role": "Open Source Contributor", "org": "Public repositories",
             "bullets": [
                 "{n2} merged pull requests across {n1} projects, including documentation, test coverage, and bug fixes",
                 "Maintain a utility library with {n4} weekly downloads and {n2} outside contributors",
             ]},
            {"role": "Instructor", "org": "{city} Public Library Code Club",
             "bullets": [
                 "Taught free Saturday Python workshops to {n3} middle schoolers over {n1} years",
                 "Wrote a {n2}-lesson curriculum now reused by {n1} other branches",
             ]},
            {"role": "Intern", "org": "{stem} Data Systems (local startup)",
             "bullets": [
                 "Built internal dashboards in TypeScript; automated a report that saved staff {n2} hours per month",
                 "Wrote the first integration test suite for a service handling {n5} daily requests",
             ]},
        ],
        "awards": [
            "USACO Gold Division qualifier ({year})",
            "{stem} Hackathon — {place} Place overall, {n2} teams ({year})",
            "National Merit {merit}",
            "AP Scholar with Distinction ({year})",
            "Congressional App Challenge — District Winner ({year})",
            "American Mathematics Competition — AIME qualifier ({year})",
        ],
        "skills": "Languages: Python, TypeScript/JavaScript, Java, C++, SQL\nFrameworks: React, Node.js, FastAPI, PostgreSQL, Docker\nTools: Git, GitHub Actions, Linux, Figma\nOther: Technical writing, teaching, API design",
    },
    "humanities_debate": {
        "clubs": ["Debate Club", "Model UN", "School Newspaper", "History Club"],
        "majors": ["Government", "History", "Social Studies", "Philosophy",
                   "History and Literature", "Economics"],
        "summary": [
            "Prospective {major} concentrator and nationally ranked debater whose research on {topic} became a {n2}-page independent thesis.",
            "Editor-in-chief and policy debater focused on {topic}, with {n1} years of sustained investigative student journalism.",
            "Aspiring {major} concentrator organizing around {topic} at the municipal level.",
        ],
        "topics": ["local eviction policy", "school board redistricting", "municipal water rights",
                   "juvenile sentencing reform", "rural broadband access", "state textbook adoption"],
        "activities": [
            {"role": "Editor-in-Chief", "org": "The {stem} Review (student newspaper)",
             "bullets": [
                 "Lead a masthead of {n2} writers publishing {n1} issues per year to a readership of {n4}",
                 "Reported a {n1}-part investigation into {topic} that prompted a formal district response",
                 "Rebuilt the paper's web presence, growing online readership {pct1}% in one year",
             ]},
            {"role": "Varsity Captain", "org": "Policy Debate",
             "bullets": [
                 "Qualified for the national tournament {n1} consecutive years; career record {n3}-{n2}",
                 "Wrote and maintained a {n4}-page evidence file shared across the squad",
                 "Coached {n2} novices, {n1} of whom broke to elimination rounds in their first season",
             ]},
            {"role": "Founder", "org": "{city} Youth Policy Forum",
             "bullets": [
                 "Convened {n3} students and {n2} local officials for quarterly public forums on {topic}",
                 "Drafted a policy memo cited during {n1} city council sessions",
             ]},
            {"role": "Intern", "org": "Office of State Representative (district office)",
             "bullets": [
                 "Handled {n3} constituent casework intakes across {n1} semesters",
                 "Researched and summarized {n2} bills for staff briefings",
             ]},
            {"role": "President", "org": "Model United Nations",
             "bullets": [
                 "Directed a conference hosting {n4} delegates from {n2} schools",
                 "Earned {n1} Best Delegate awards across {n2} conferences",
             ]},
        ],
        "awards": [
            "National Speech and Debate Association — {place} Place, National Tournament ({year})",
            "Columbia Scholastic Press Association — Gold Circle Award ({year})",
            "National Merit {merit}",
            "State History Day — {place} Place, Individual Documentary ({year})",
            "AP Scholar with Distinction ({year})",
            "Harvard Book Award ({year})",
        ],
        "skills": "Research: Archival research, FOIA requests, statistical sourcing, interview technique\nWriting: Long-form journalism, policy memos, argumentative essays, copy editing\nLanguages: Spanish (conversational), Latin (reading)\nTools: InDesign, WordPress, Google Data Studio, Zotero",
    },
    "arts_performance": {
        "clubs": ["Concert Band", "Drama Club", "Art Club", "School Choir"],
        "majors": ["Music", "Visual and Environmental Studies", "English",
                   "Theater, Dance, and Media", "Art, Film, and Visual Studies"],
        "summary": [
            "Prospective {major} concentrator and {instrument} player with {n1} years of conservatory-track training and {n2} public performances.",
            "Visual artist working in {topic}, with a {n2}-piece portfolio shown in {n1} juried exhibitions.",
            "Aspiring {major} concentrator directing student theater and teaching arts access to younger students.",
        ],
        "topics": ["large-format documentary photography", "ceramic sculpture", "screenprinting and zine-making",
                   "stop-motion animation", "mixed-media collage", "analog darkroom portraiture"],
        "instruments": ["violin", "cello", "classical guitar", "jazz trumpet", "piano", "double bass", "clarinet"],
        "activities": [
            {"role": "Principal {instrument_title}", "org": "{city} Youth Symphony",
             "bullets": [
                 "Hold the principal chair after {n1} years in the ensemble; perform {n2} concerts annually",
                 "Selected for the All-State orchestra {n1} consecutive years",
                 "Practice {n2} hours weekly alongside a full academic course load",
             ]},
            {"role": "Founder and Director", "org": "Free Arts Saturdays",
             "bullets": [
                 "Started a free weekend arts program serving {n3} elementary students in under-resourced neighborhoods",
                 "Raised {amt2} dollars in grants and recruited {n2} volunteer teaching artists",
             ]},
            {"role": "Stage Manager and Director", "org": "{stem} Student Theater",
             "bullets": [
                 "Directed {n1} full productions and stage-managed {n2} others across {n1} seasons",
                 "Managed a {n2}-person crew and a production budget of {amt2} dollars",
             ]},
            {"role": "Exhibiting Artist", "org": "Regional juried exhibitions",
             "bullets": [
                 "Work in {topic} accepted into {n1} juried shows; {n1} pieces sold to benefit the school arts fund",
                 "Built a {n2}-piece portfolio across {n1} years of sustained studio practice",
             ]},
            {"role": "Private Instructor", "org": "Self-employed",
             "bullets": [
                 "Teach {n1} weekly {instrument} students, contributing earnings to household expenses",
             ]},
        ],
        "awards": [
            "All-State Orchestra — Principal chair ({year})",
            "Scholastic Art and Writing Awards — Gold Key, {n1} entries ({year})",
            "{city} Young Artists Competition — {place} Place ({year})",
            "National Merit {merit}",
            "State Thespian Festival — Superior rating ({year})",
            "AP Scholar with Honor ({year})",
        ],
        "skills": "Performance: {instrument_title} (advanced), music theory, sight-reading, ensemble leadership\nStudio: {topic_title}, Adobe Creative Suite, darkroom processing, portfolio curation\nProduction: Stage management, lighting design, QLab, budget management",
    },
    "athlete_leader": {
        "clubs": ["Junior Varsity {sport_title}", "Intramural Sports", "Student Athletic Committee", "Weight Room Crew"],
        "majors": ["Economics", "Human Evolutionary Biology", "Psychology",
                   "Sociology", "Government"],
        "summary": [
            "Prospective {major} concentrator and {n1}-year varsity {sport} captain balancing {n2} weekly training hours with a full honors course load.",
            "Recruited {sport} athlete and student body officer with a record of turning around team culture.",
            "Aspiring {major} concentrator whose {sport} team reached the state final under their captaincy.",
        ],
        "sports": ["cross country", "rowing", "soccer", "swimming", "track and field",
                   "wrestling", "basketball", "fencing", "volleyball"],
        "topics": ["youth athletics access", "concussion protocol reform", "Title IX compliance in school athletics"],
        "activities": [
            {"role": "Varsity Captain", "org": "{sport_title}",
             "bullets": [
                 "Captain for {n1} seasons; led the team to a {place}-place state finish and its first conference title in {n2} years",
                 "Train {n2} hours weekly year-round, including {n1} off-season strength blocks",
                 "All-Conference selection {n1} years; team academic GPA rose from {gpa_a} to {gpa_b} under a study-hall system I started",
             ]},
            {"role": "Student Body Vice President", "org": "Student Government",
             "bullets": [
                 "Elected by a student body of {n4}; ran on and delivered a later-start pilot for athletes in first-period classes",
                 "Managed a {amt2}-dollar activities budget across {n2} clubs",
             ]},
            {"role": "Founder", "org": "Youth Sports Equipment Drive",
             "bullets": [
                 "Collected and redistributed {n3} pieces of used equipment to {n1} under-funded middle school programs",
                 "Raised {amt2} dollars and recruited {n2} volunteers over {n1} years",
             ]},
            {"role": "Coach and Referee", "org": "{city} Parks and Recreation",
             "bullets": [
                 "Coach a youth {sport} squad of {n2}; officiate {n3} games per season as paid work",
             ]},
            {"role": "Peer Tutor", "org": "Athletic Department Study Hall",
             "bullets": [
                 "Tutor {n2} teammates weekly in algebra and chemistry; program eligibility rate rose {pct1}%",
             ]},
        ],
        "awards": [
            "All-State {sport_title} selection ({year})",
            "Conference Athlete of the Year ({year})",
            "National Football Foundation Scholar-Athlete ({year})",
            "National Merit {merit}",
            "AP Scholar with Honor ({year})",
            "State Championship — {place} Place, team ({year})",
        ],
        "skills": "Leadership: Team captaincy, conflict mediation, public speaking, event logistics\nAcademic: Statistics, data analysis in Excel and R, research writing\nCertifications: USA {sport_title} Level 1 official, CPR/AED certified, Lifeguard certified",
    },
    "service_entrepreneur": {
        "clubs": ["Key Club", "Interact Club", "Community Service Club", "Future Business Leaders of America chapter"],
        "majors": ["Economics", "Sociology", "Social Studies", "Applied Mathematics",
                   "Environmental Science and Public Policy"],
        "summary": [
            "Prospective {major} concentrator who founded {topic} while working {n2} paid hours weekly to help support the household.",
            "Student organizer and small-business operator focused on {topic}, with {n4} people served to date.",
            "Aspiring {major} concentrator turning {topic} into a self-sustaining nonprofit run entirely by students.",
        ],
        "topics": ["a student-run food pantry", "a bilingual tax-prep clinic", "a bike repair co-op",
                   "a free tutoring network for English learners", "a neighborhood composting service",
                   "a senior-center technology help desk"],
        "activities": [
            {"role": "Founder and Executive Director", "org": "{topic_title}",
             "bullets": [
                 "Built {topic} from nothing into an operation serving {n4} community members annually",
                 "Raised {amt2} dollars across {n1} grant cycles and recruited a volunteer staff of {n2} students",
                 "Wrote the bylaws, budget, and volunteer handbook; secured 501(c)(3) fiscal sponsorship",
             ]},
            {"role": "Shift Lead", "org": "{stem} Grocery",
             "bullets": [
                 "Work {n2} hours weekly during the school year and {n2} hours in summer, contributing to household expenses",
                 "Promoted to shift lead after {n1} months; train new cashiers and close the store {n1} nights weekly",
             ]},
            {"role": "Interpreter and Caregiver", "org": "Family responsibilities",
             "bullets": [
                 "Serve as primary interpreter for parents at medical, legal, and school appointments",
                 "Provide after-school care for {n1} younger siblings, {n2} hours weekly",
             ]},
            {"role": "Youth Commissioner", "org": "{city} Mayor's Youth Council",
             "bullets": [
                 "One of {n2} students appointed citywide; authored a recommendation on {topic} adopted into the council's annual report",
             ]},
            {"role": "Treasurer", "org": "First-Generation Students Union",
             "bullets": [
                 "Manage a {amt1}-dollar budget and run a college application fee-waiver workshop for {n3} students",
             ]},
        ],
        "awards": [
            "Prudential Spirit of Community Award — State Honoree ({year})",
            "Coca-Cola Scholars Program — Semifinalist ({year})",
            "QuestBridge College Prep Scholar ({year})",
            "National Merit {merit}",
            "{city} Chamber of Commerce Young Entrepreneur Award ({year})",
            "AP Scholar ({year})",
        ],
        "skills": "Operations: Grant writing, budgeting, volunteer management, QuickBooks, inventory\nLanguages: Spanish (native/bilingual), English (fluent)\nTechnical: Excel, Google Workspace, Canva, Square POS\nOther: Public speaking, community outreach, conflict resolution",
    },
}

# --------------------------------------------------------------------------
# Applicant strength. Drawn independently of income, so the pool spans the
# rubric's range instead of clustering at the top. Each tier sets the GPA
# band, the SAT center, the AP load, how many activities and awards appear,
# and how often those come from the modest pools below rather than the
# archetype's own (which are written at a national-competitor level).
# --------------------------------------------------------------------------

STRENGTH_TIERS = [
    ("limited", 0.12),
    ("developing", 0.18),
    ("solid", 0.25),
    ("strong", 0.26),
    ("elite", 0.19),
]

STRENGTH_PROFILES = {
    "limited": {"gpa": (2.30, 2.95), "sat": 1080, "ap": (0, 1), "activities": (1, 2),
                "awards": (0, 1), "rank_pct": (0.55, 0.95), "modest": 1.00, "dual": 0.00},
    "developing": {"gpa": (2.90, 3.30), "sat": 1190, "ap": (1, 3), "activities": (2, 3),
                   "awards": (0, 2), "rank_pct": (0.35, 0.70), "modest": 0.85, "dual": 0.03},
    "solid": {"gpa": (3.25, 3.62), "sat": 1300, "ap": (3, 6), "activities": (2, 4),
              "awards": (1, 3), "rank_pct": (0.15, 0.45), "modest": 0.50, "dual": 0.12},
    "strong": {"gpa": (3.58, 3.88), "sat": 1410, "ap": (5, 9), "activities": (3, 4),
               "awards": (2, 4), "rank_pct": (0.04, 0.20), "modest": 0.18, "dual": 0.32},
    "elite": {"gpa": (3.86, 4.00), "sat": 1500, "ap": (7, 13), "activities": (3, 5),
              "awards": (3, 5), "rank_pct": (0.01, 0.05), "modest": 0.00, "dual": 0.55},
}

# Participation-level entries for applicants who are not national competitors.
# {club} is filled from the archetype's own club list plus the generic ones.
GENERIC_CLUBS = [
    "School Yearbook", "Student Council", "{city} Public Library Teen Volunteers",
    "Intramural Sports", "Spirit Committee",
]

MODEST_ACTIVITIES = [
    {"modest": True, "role": "Member", "org": "{club}",
     "bullets": [
         "Attended weekly meetings across {n1} school years; no officer position held",
         "Helped set up and staff the club's annual showcase",
     ]},
    {"modest": True, "role": "Participant", "org": "{club}",
     "bullets": [
         "Took part in {n1} school-year sessions and one regional event",
         "Contributed to group projects as one of {n2} members",
     ]},
    {"modest": True, "role": "Volunteer", "org": "{city} Community Center",
     "bullets": [
         "Logged {n3} service hours across {n1} years, mostly weekend events",
         "Helped run a seasonal food and coat drive",
     ]},
    {"modest": True, "role": "Team Member", "org": "{club}",
     "bullets": [
         "Practiced {n1} afternoons weekly through the season; started {n1} games",
         "Named to the squad {n1} years running without earning a varsity letter",
     ]},
    {"modest": True, "role": "Assistant", "org": "{city} Youth Program",
     "bullets": [
         "Supervised activities for younger students {n1} afternoons per week",
         "Covered shifts through {n1} summer sessions",
     ]},
    {"modest": True, "role": "Helper", "org": "{stem} Animal Shelter",
     "bullets": [
         "Walked and fed animals on weekend shifts over {n1} years",
         "Helped staff {n1} adoption events",
     ]},
]

MODEST_AWARDS = [
    "Honor Roll, {n1} semesters ({year})",
    "Perfect Attendance ({year})",
    "{club} Most Improved Member ({year})",
    "School Citizenship Award ({year})",
    "AP Scholar ({year})",
    "Coach's Award, junior season ({year})",
]

MODEST_SUMMARIES = [
    "Prospective {major} concentrator with a steady classroom record and consistent participation in {club}.",
    "Student interested in {major}. Strongest work is coursework rather than outside competition.",
    "Applicant to {major} who has improved year over year and holds a part-time job alongside school.",
    "Prospective {major} concentrator, active in {club}, looking for a college that will let them explore broadly.",
]

MODEST_SKILLS = [
    "Coursework: standard college-preparatory sequence with {major}-track electives\nTechnical: Microsoft Office, Google Workspace, basic spreadsheet work\nOther: Teamwork, time management, reliability",
    "Academic: Essay writing, note-taking, group presentations\nTechnical: Google Workspace, Canva, basic HTML\nOther: Customer service, punctuality, coachability",
    "Coursework: Introductory {major} electives\nTechnical: Excel, Google Docs, basic troubleshooting\nOther: Communication, teamwork, asking for help early",
]

WORK_EXPERIENCE = [
    ("Barista", "{stem} Coffee", "Work {n2} hours weekly year-round; trained {n1} new hires on bar workflow"),
    ("Lifeguard", "{city} Municipal Pool", "Certified lifeguard working {n2} summer hours weekly; logged {n1} assists"),
    ("Cashier", "{stem} Market", "Balance {n2} weekly work hours against a full AP course load"),
    ("Tutor", "Self-employed", "Tutor {n1} students weekly in math and chemistry at {n2} dollars per hour"),
    ("Camp Counselor", "{city} Summer Program", "Supervise {n2} campers daily across a {n1}-week summer session"),
    ("Line Cook", "{stem} Diner", "Work {n2} hours weekly, including closing shifts, contributing to household income"),
    ("Kennel Assistant", "{stem} Veterinary Clinic", "Care for {n2} animals per shift; {n1} shifts weekly after school"),
    ("Data Entry Assistant", "{city} Public Library", "Digitized {n4} archival records over {n1} semesters"),
]

RECOMMENDER_NOTES = [
    "Counselor notes this applicant takes the most demanding schedule available at the school.",
    "School offers {ap_offered} AP courses; applicant has taken {ap_taken} of them.",
    "Applicant is a first-generation college applicant.",
    "Applicant commutes {n1} hours daily to attend this school.",
    "Applicant's school does not rank students.",
    "Applicant has attended {n1} high schools due to family relocation.",
]

PLAIN_RECOMMENDER_NOTES = [
    "School offers {ap_offered} AP courses; applicant has taken {ap_taken} of them.",
    "Counselor notes grades improved in junior year after a difficult sophomore year.",
    "Applicant repeated one core course and has kept pace with the standard track since.",
    "Applicant missed {n2} school days in sophomore year due to a family illness.",
    "Applicant is a first-generation college applicant.",
    "Counselor describes the applicant as a quiet, dependable presence in the classroom.",
]


def numbers(rng: random.Random) -> dict:
    """Random fillers shared by every bullet template."""
    return {
        "n1": rng.randint(2, 4),
        "n2": rng.randint(10, 45),
        "n3": rng.randint(50, 180),
        "n4": rng.randint(200, 900),
        "n5": rng.randint(1_000, 9_000),
        "pct1": rng.randint(12, 60),
        "pct2": rng.randint(55, 95),
        "amt1": rng.randrange(400, 5_000, 100),
        "amt2": rng.randrange(5_000, 45_000, 500),
        "gpa_a": f"{rng.uniform(2.6, 3.0):.2f}",
        "gpa_b": f"{rng.uniform(3.2, 3.7):.2f}",
        "place": rng.choice(["First", "Second", "Third", "Fourth", "Fifth"]),
        "merit": rng.choice(["Finalist", "Semifinalist", "Commended Scholar"]),
        "year": rng.choice([2024, 2025, 2026]),
    }


def pick_strength(rng: random.Random) -> tuple[str, dict]:
    """Draw an applicant strength tier, independent of income."""
    names = [t[0] for t in STRENGTH_TIERS]
    weights = [t[1] for t in STRENGTH_TIERS]
    tier = rng.choices(names, weights=weights, k=1)[0]
    return tier, STRENGTH_PROFILES[tier]


def pick_income(rng: random.Random):
    names = [t[0] for t in INCOME_TIERS]
    weights = [t[1] for t in INCOME_TIERS]
    tier = rng.choices(names, weights=weights, k=1)[0]
    _, _, lo, hi, score_shift, school_band = next(t for t in INCOME_TIERS if t[0] == tier)
    # Skew within the band toward its lower end, then round to a tidy figure.
    raw = lo + (hi - lo) * (rng.random() ** 1.7)
    step = 500 if raw < 200_000 else 5_000
    income = int(round(raw / step) * step)
    return tier, income, score_shift, school_band


def make_education(rng: random.Random, city: str, state: str, band: str,
                   score_shift: int, profile: dict):
    stem = rng.choice(SCHOOL_STEMS)
    school = rng.choice(SCHOOL_TYPES_BY_TIER[band]).format(stem=stem, city=city)
    grad_year = 2026

    sat = min(1600, max(780, int(rng.gauss(profile["sat"] + score_shift, 70) / 10) * 10))
    math = min(800, max(340, int(round((sat * rng.uniform(0.49, 0.53)) / 10) * 10)))
    ebrw = min(800, max(340, sat - math))
    sat = math + ebrw
    act = min(36, max(13, round(sat / 45.2)))

    gpa_lo, gpa_hi = profile["gpa"]
    unweighted = min(gpa_hi, max(gpa_lo, rng.gauss((gpa_lo + gpa_hi) / 2, (gpa_hi - gpa_lo) / 4)))

    # AP load comes from the strength tier; income band nudges it, the way the
    # school's own offerings would.
    ap_lo, ap_hi = profile["ap"]
    ap_count = rng.randint(ap_lo, ap_hi) + {"low": -1, "mid": 0, "high": 2}[band]
    ap_count = max(0, min(len(AP_COURSES), ap_count))
    aps = rng.sample(AP_COURSES, ap_count)
    weighted = min(5.0, unweighted + min(0.85, 0.06 * ap_count + rng.uniform(0.0, 0.12)))

    lines = [
        "EDUCATION",
        "",
        f"{school} | {city}, {state} | Expected graduation: June {grad_year}",
        f"- GPA: {weighted:.2f} weighted / {unweighted:.2f} unweighted",
    ]
    if rng.random() < 0.72:
        size = rng.randint(90, 720)
        rank_lo, rank_hi = profile["rank_pct"]
        rank = max(1, min(size, round(size * rng.uniform(rank_lo, rank_hi))))
        lines.append(f"- Class rank: {rank} of {size}")
    else:
        lines.append("- Class rank: School does not rank")
    if rng.random() < 0.88:
        lines.append(f"- SAT: {sat} (Math {math}, EBRW {ebrw}) | ACT: {act}")
    else:
        lines.append("- Standardized tests: Not submitted (test-optional)")
    if aps:
        lines.append(f"- AP coursework ({len(aps)}): " + ", ".join(sorted(aps)))
    else:
        lines.append("- AP coursework: None; standard college-preparatory track")
    if band != "high" and rng.random() < profile["dual"]:
        lines.append("- Additional coursework: " + rng.choice(DUAL_ENROLLMENT).format(city=city))
    offered = len(aps) + rng.randint(2, 10)
    return "\n".join(lines), len(aps), offered


def make_activities(rng: random.Random, arch: dict, nums: dict, ctx: dict, profile: dict) -> str:
    low, high = profile["activities"]
    count = rng.randint(low, high)
    n_modest = sum(1 for _ in range(count) if rng.random() < profile["modest"])
    entries = rng.sample(arch["activities"], min(count - n_modest, len(arch["activities"])))
    entries += rng.sample(MODEST_ACTIVITIES, min(n_modest, len(MODEST_ACTIVITIES)))
    rng.shuffle(entries)

    # One club per slot, drawn without replacement, so no applicant lists the
    # same club twice under two different roles.
    pool = arch["clubs"] + GENERIC_CLUBS
    clubs = [c.format(**ctx) for c in rng.sample(pool, min(len(entries), len(pool)))]

    blocks = []
    for slot, entry in enumerate(entries):
        modest = entry.get("modest", False)
        local = dict(ctx, club=clubs[slot % len(clubs)])
        start_year = rng.choice([2022, 2023, 2024])
        kind = rng.choice(["ongoing", "ongoing", "past", "summer"])
        if kind == "summer":
            span = f"Jun {start_year} - Aug {start_year}"
            hours, weeks = rng.randint(20, 45), rng.randint(6, 12)
        elif kind == "ongoing":
            span = f"Sep {start_year} - Present"
            hours, weeks = rng.randint(3, 22), rng.randint(28, 44)
        else:
            # Nothing runs past the June 2026 graduation date.
            span = f"Sep {start_year} - Jun {min(2026, start_year + rng.randint(1, 3))}"
            hours, weeks = rng.randint(3, 22), rng.randint(28, 40)
        if modest:
            hours = min(hours, rng.randint(2, 6))
        role = entry["role"].format(**local)
        org = entry["org"].format(**local, **nums)
        bullets = rng.sample(entry["bullets"], rng.randint(2, len(entry["bullets"]))) \
            if len(entry["bullets"]) > 2 else entry["bullets"]
        body = "\n".join("- " + b.format(**numbers(rng), **local) for b in bullets)
        blocks.append(f"{role} | {org} | {span} | {hours} hrs/week, {weeks} weeks/year\n{body}")
    return "ACTIVITIES AND LEADERSHIP\n\n" + "\n\n".join(blocks)


def pick_club(rng: random.Random, arch: dict, ctx: dict) -> str:
    return rng.choice(arch["clubs"] + GENERIC_CLUBS).format(**ctx)


def make_awards(rng: random.Random, arch: dict, nums: dict, ctx: dict, profile: dict) -> str:
    low, high = profile["awards"]
    count = rng.randint(low, high)
    if count == 0:
        return ""
    n_full = sum(1 for _ in range(count) if rng.random() > profile["modest"])
    picks = rng.sample(arch["awards"], min(n_full, len(arch["awards"])))
    picks += rng.sample(MODEST_AWARDS, min(count - len(picks), len(MODEST_AWARDS)))
    rng.shuffle(picks)

    lines = []
    for award in picks:
        local = dict(nums)
        local["year"] = rng.choice([2023, 2024, 2025, 2026])
        local["place"] = rng.choice(["First", "Second", "Third", "Fourth"])
        lines.append("- " + award.format(**local, **dict(ctx, club=pick_club(rng, arch, ctx))))
    return "AWARDS AND HONORS\n\n" + "\n".join(lines)


def make_work(rng: random.Random, nums: dict, ctx: dict, tier: str) -> str:
    count = 2 if tier in ("low", "lower_mid", "mid") else rng.randint(0, 2)
    if count == 0:
        return ""
    picks = rng.sample(WORK_EXPERIENCE, count)
    lines = []
    for role, org, bullet in picks:
        start_year = rng.choice([2023, 2024, 2025])
        lines.append(
            f"{role} | {org.format(**ctx)} | {rng.choice(['Jun', 'Sep', 'Jan'])} {start_year} - "
            f"{rng.choice(['Present', f'Aug {start_year}', f'Jun {start_year + 1}'])}\n"
            f"- {bullet.format(**nums, **ctx)}"
        )
    return "WORK AND VOLUNTEER EXPERIENCE\n\n" + "\n\n".join(lines)


def make_resume(rng: random.Random) -> tuple[str, int, str, str]:
    tier, income, score_shift, band = pick_income(rng)
    strength, profile = pick_strength(rng)
    arch_name = rng.choice(list(ARCHETYPES))
    arch = ARCHETYPES[arch_name]
    # One draw decides whether the prose framing matches the weaker record, so
    # summary, skills, and counselor note stay consistent with each other.
    plain = rng.random() < profile["modest"]

    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    city, state = rng.choice(CITIES)
    nums = numbers(rng)

    topic = rng.choice(arch["topics"])
    ctx = {
        "major": rng.choice(arch["majors"]),
        "topic": topic,
        "topic_title": topic[0].upper() + topic[1:],
        "city": city,
        "stem": rng.choice(SCHOOL_STEMS),
    }
    if "instruments" in arch:
        instrument = rng.choice(arch["instruments"])
        ctx["instrument"] = instrument
        ctx["instrument_title"] = instrument.title()
    if "sports" in arch:
        sport = rng.choice(arch["sports"])
        ctx["sport"] = sport
        ctx["sport_title"] = sport.title()
    ctx["club"] = pick_club(rng, arch, ctx)

    handle = f"{first}.{last}".lower().replace("'", "").replace("ó", "o").replace("é", "e").replace("á", "a")
    contact = f"{city}, {state} | {handle}@email.com"
    if arch_name == "cs_builder":
        contact += f" | github.com/{handle.replace('.', '')}"
    elif arch_name == "arts_performance":
        contact += f" | portfolio: {handle.replace('.', '')}.myportfolio.com"

    education, ap_taken, ap_offered = make_education(rng, city, state, band, score_shift, profile)
    nums["ap_taken"] = ap_taken
    nums["ap_offered"] = ap_offered

    sections = [
        f"{first.upper()} {last.upper()}",
        contact,
        "",
        "APPLICANT SUMMARY",
        "",
        rng.choice(MODEST_SUMMARIES if plain else arch["summary"]).format(**nums, **ctx),
        "",
        education,
        "",
        make_activities(rng, arch, nums, ctx, profile),
    ]

    awards = make_awards(rng, arch, nums, ctx, profile)
    if awards:
        sections += ["", awards]

    secondary = rng.choice([m for m in arch["majors"] if m != ctx["major"]])

    work = make_work(rng, nums, ctx, tier)
    if work:
        sections += ["", work]

    sections += [
        "",
        "SKILLS",
        "",
        (rng.choice(MODEST_SKILLS) if plain else arch["skills"]).format(**ctx),
        "",
        "INTENDED CONCENTRATION",
        "",
        f"{ctx['major']} (secondary interest: {secondary})",
        "",
        "COUNSELOR CONTEXT",
        "",
        "- " + rng.choice(PLAIN_RECOMMENDER_NOTES if plain else RECOMMENDER_NOTES).format(**nums),
    ]
    return "\n".join(sections), income, arch_name, strength


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260917)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    records = []
    for i in range(args.count):
        resume, income, _arch, strength = make_resume(rng)
        records.append({
            "applicant_id": f"HC-2026-{i + 1:05d}",
            "resume": resume,
            "family_annual_income": income,
            "strength_tier": strength,
        })

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "applications.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (args.out / "applications.jsonl").open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    incomes = sorted(r["family_annual_income"] for r in records)
    print(f"Wrote {len(records)} synthetic applications to {args.out}")
    print(f"  income min/median/max: {incomes[0]:,} / {incomes[len(incomes)//2]:,} / {incomes[-1]:,}")
    counts = Counter(r["strength_tier"] for r in records)
    spread = ", ".join(f"{name} {counts[name]}" for name, _ in STRENGTH_TIERS)
    print(f"  strength spread: {spread}")


if __name__ == "__main__":
    main()
