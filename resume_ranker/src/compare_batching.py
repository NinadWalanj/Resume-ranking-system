"""Compare solo vs batched LLM scoring.

Scores 10 candidates against one JD two ways:
  - Solo: each candidate in its own LLM call (run 2x).
  - Batched: all 10 in one prompt (run 3x with different orderings).

Then reports per-candidate score deltas, position bias, and ranking changes.

Usage:
    python -m src.compare_batching
"""

import asyncio
import json
import os
import random
from statistics import mean

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from src.scoring import score_candidate, WEIGHTS, MODEL

load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


# -----------------------------------------------------------------------------
# Test data: 10 candidates with deliberately varied profiles.
# -----------------------------------------------------------------------------

JD = {
    "title": "Senior Backend Engineer",
    "required_skills": ["Python", "PostgreSQL", "REST APIs", "AWS"],
    "nice_to_haves": ["Kubernetes", "Redis", "GraphQL"],
    "experience_level": "5+ years",
    "domain": "fintech",
}

CANDIDATES = [
    (
        "Strong fintech senior",
        {
            "skills": [
                "Python",
                "PostgreSQL",
                "REST APIs",
                "AWS",
                "Kubernetes",
                "Redis",
            ],
            "total_years": 7,
            "experience": [
                {"title": "Senior Backend Engineer", "domain": "fintech", "years": 7}
            ],
            "education": [{"degree": "BS CS"}],
        },
    ),
    (
        "Overqualified staff",
        {
            "skills": [
                "Python",
                "PostgreSQL",
                "REST APIs",
                "AWS",
                "GraphQL",
                "Redis",
                "Kubernetes",
            ],
            "total_years": 12,
            "experience": [
                {"title": "Staff Engineer", "domain": "fintech", "years": 12}
            ],
            "education": [{"degree": "MS CS"}],
        },
    ),
    (
        "Exact match at bar",
        {
            "skills": ["Python", "PostgreSQL", "AWS", "REST APIs"],
            "total_years": 5,
            "experience": [
                {"title": "Backend Engineer", "domain": "fintech", "years": 5}
            ],
            "education": [{"degree": "BS CS"}],
        },
    ),
    (
        "Right skills wrong domain",
        {
            "skills": ["Python", "PostgreSQL", "REST APIs", "AWS", "Docker"],
            "total_years": 5,
            "experience": [
                {"title": "Backend Engineer", "domain": "e-commerce", "years": 5}
            ],
            "education": [{"degree": "BS CS"}],
        },
    ),
    (
        "Junior fintech",
        {
            "skills": ["Python", "PostgreSQL", "REST APIs"],
            "total_years": 2,
            "experience": [
                {"title": "Backend Engineer", "domain": "fintech", "years": 2}
            ],
            "education": [{"degree": "BS CS"}],
        },
    ),
    (
        "Partial skills marketing",
        {
            "skills": ["Python", "Django", "MySQL", "REST APIs"],
            "total_years": 3,
            "experience": [
                {"title": "Full Stack Developer", "domain": "marketing", "years": 3}
            ],
            "education": [{"degree": "BS IS"}],
        },
    ),
    (
        "Wrong stack entirely",
        {
            "skills": ["JavaScript", "Node.js", "MongoDB", "React"],
            "total_years": 4,
            "experience": [
                {"title": "Frontend Engineer", "domain": "advertising", "years": 4}
            ],
            "education": [{"degree": "BS CS"}],
        },
    ),
    (
        "Backend + ML mix",
        {
            "skills": ["Python", "TensorFlow", "AWS", "PostgreSQL"],
            "total_years": 6,
            "experience": [{"title": "ML Engineer", "domain": "fintech", "years": 6}],
            "education": [{"degree": "MS CS"}],
        },
    ),
    (
        "Many years, weak skills",
        {
            "skills": ["Java", "Oracle", "SOAP"],
            "total_years": 15,
            "experience": [
                {"title": "Senior Engineer", "domain": "banking", "years": 15}
            ],
            "education": [{"degree": "BS CS"}],
        },
    ),
    (
        "Bootcamp fintech junior",
        {
            "skills": ["Python", "PostgreSQL", "REST APIs"],
            "total_years": 1,
            "experience": [
                {"title": "Junior Backend", "domain": "fintech", "years": 1}
            ],
            "education": [{"degree": "Bootcamp"}],
        },
    ),
]


# -----------------------------------------------------------------------------
# Batched scoring: same rubric anchors as scoring.py's solo prompt.
# Anchors are kept identical word-for-word so the test is fair.
# -----------------------------------------------------------------------------


class BatchedCandidateScore(BaseModel):
    candidate_id: int
    required_skills: int = Field(ge=1, le=5)
    experience_level: int = Field(ge=1, le=5)
    domain_fit: int = Field(ge=1, le=5)
    education: int = Field(ge=1, le=5)
    reasoning: str


class BatchedScores(BaseModel):
    scores: list[BatchedCandidateScore]


BATCH_PROMPT = """You are scoring multiple candidates against a single job description.

Job Description:
{jd}

Candidates:
{candidates_block}

Score each candidate on each criterion from 1 to 5 using these anchors:

required_skills - how well the candidate's skills match the required skills.
  5 = matches all required skills with comparable depth
  4 = matches most required skills with strong depth
  3 = matches most required skills, gaps in depth or adjacent experience
  2 = matches some required skills, significant gaps
  1 = minimal overlap with required skills

experience_level - does years and seniority match what the role needs.
  5 = exceeds requirement meaningfully
  4 = matches requirement
  3 = slightly below
  2 = noticeably below
  1 = far below

domain_fit - relevance of industry/domain experience to the role's domain.
  5 = direct experience in the same domain
  4 = closely adjacent
  3 = somewhat related
  2 = unrelated but transferable
  1 = unrelated

education - does the candidate's education fit role expectations.
  5 = exceeds expectations
  4 = matches expectations
  3 = adjacent or slightly below
  2 = below expectations but compensated by experience
  1 = does not meet expectations

CRITICAL: Score each candidate independently against the JD as if you were
only seeing that candidate. Do NOT compare candidates to each other.
Your reference point is the JD, never the other candidates in this batch.

Return JSON with one entry per candidate. Use the candidate_id field to
identify which candidate each score belongs to."""


async def score_batched(jd, candidates):
    """Score all candidates in one LLM call. Returns list in input order."""
    block = "\n\n".join(
        f"Candidate ID: {i+1}\n{json.dumps(r, indent=2)}"
        for i, (_, r) in enumerate(candidates)
    )
    prompt = BATCH_PROMPT.format(jd=json.dumps(jd, indent=2), candidates_block=block)

    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=BatchedScores,
        ),
    )
    parsed = BatchedScores.model_validate_json(response.text)

    # Validate: every candidate present exactly once.
    ids = [s.candidate_id for s in parsed.scores]
    expected = set(range(1, len(candidates) + 1))
    if set(ids) != expected:
        raise ValueError(
            f"batch returned ids {sorted(ids)}, expected {sorted(expected)}"
        )

    results = [None] * len(candidates)
    for s in parsed.scores:
        breakdown = s.model_dump()
        breakdown.pop("candidate_id")
        total = sum(breakdown[c] * w for c, w in WEIGHTS.items())
        results[s.candidate_id - 1] = {
            "name": candidates[s.candidate_id - 1][0],
            "total": total,
            "breakdown": breakdown,
        }
    return results


async def score_solo_all(jd, candidates):
    """Score each candidate in its own LLM call, concurrently."""

    async def one(name, resume):
        total, breakdown = await score_candidate(jd, resume)
        return {"name": name, "total": total, "breakdown": breakdown}

    return await asyncio.gather(*[one(n, r) for n, r in candidates])


# -----------------------------------------------------------------------------
# Reporting
# -----------------------------------------------------------------------------


def report_solo_vs_batched(solo_runs, batched_runs):
    print("\n" + "=" * 78)
    print("SOLO vs BATCHED  (mean score across runs)")
    print("=" * 78)
    print(f"{'Candidate':<30} {'Solo':>8} {'Batched':>10} {'Delta':>8}")
    print("-" * 78)
    deltas = []
    for i, (name, _) in enumerate(CANDIDATES):
        solo_mean = mean(r[i]["total"] for r in solo_runs)
        batch_mean = mean(r[i]["total"] for r in batched_runs)
        d = batch_mean - solo_mean
        deltas.append(d)
        print(f"{name:<30} {solo_mean:>8.2f} {batch_mean:>10.2f} {d:>+8.2f}")
    print("-" * 78)
    print(f"Mean absolute delta: {mean(abs(d) for d in deltas):.2f}")
    print(f"Max absolute delta:  {max(abs(d) for d in deltas):.2f}")


def report_position_bias(batched_runs):
    print("\n" + "=" * 78)
    print("POSITION BIAS  (same candidate, different positions in batch)")
    print("=" * 78)
    print(f"{'Candidate':<30} {'Scores by position in batch':<45}")
    print("-" * 78)
    for i, (name, _) in enumerate(CANDIDATES):
        pairs = sorted((r[i]["position"], r[i]["total"]) for r in batched_runs)
        line = "  ".join(f"pos{p:>2}: {s:>5.2f}" for p, s in pairs)
        print(f"{name:<30} {line}")


def report_ranking_changes(solo_runs, batched_runs):
    print("\n" + "=" * 78)
    print("RANKINGS  (ordered by mean score across runs)")
    print("=" * 78)
    solo_order = sorted(
        range(len(CANDIDATES)), key=lambda i: -mean(r[i]["total"] for r in solo_runs)
    )
    batch_order = sorted(
        range(len(CANDIDATES)), key=lambda i: -mean(r[i]["total"] for r in batched_runs)
    )
    print(f"{'Rank':<6} {'Solo':<30} {'Batched':<30}")
    print("-" * 78)
    for rank in range(len(CANDIDATES)):
        s = CANDIDATES[solo_order[rank]][0]
        b = CANDIDATES[batch_order[rank]][0]
        marker = "  " if s == b else " *"
        print(f"{rank+1:<6} {s:<30} {b:<30}{marker}")
    diffs = sum(1 for s, b in zip(solo_order, batch_order) if s != b)
    print(f"\nPositions that differ: {diffs}/{len(CANDIDATES)}  (* marks differences)")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

N_SOLO_RUNS = 2
N_BATCHED_RUNS = 3


async def main():
    print(f"Comparing solo vs batched LLM scoring on {len(CANDIDATES)} candidates.")
    print(
        f"Solo:    {N_SOLO_RUNS} runs x {len(CANDIDATES)} calls = "
        f"{N_SOLO_RUNS * len(CANDIDATES)} LLM calls."
    )
    print(f"Batched: {N_BATCHED_RUNS} runs x 1 call = {N_BATCHED_RUNS} LLM calls.\n")

    solo_runs = []
    for run in range(N_SOLO_RUNS):
        print(f"Solo run {run+1}...")
        solo_runs.append(await score_solo_all(JD, CANDIDATES))

    batched_runs = []
    for run in range(N_BATCHED_RUNS):
        print(f"Batched run {run+1}...")
        # Shuffle and record each candidate's position in the batch.
        indices = list(range(len(CANDIDATES)))
        random.seed(run)
        random.shuffle(indices)
        shuffled = [CANDIDATES[i] for i in indices]
        results = await score_batched(JD, shuffled)
        # Map results back to original order, tagging each with its position.
        ordered = [None] * len(CANDIDATES)
        for batch_pos, orig_idx in enumerate(indices):
            ordered[orig_idx] = {**results[batch_pos], "position": batch_pos + 1}
        batched_runs.append(ordered)

    report_solo_vs_batched(solo_runs, batched_runs)
    report_position_bias(batched_runs)
    report_ranking_changes(solo_runs, batched_runs)


if __name__ == "__main__":
    asyncio.run(main())
