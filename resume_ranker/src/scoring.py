"""LLM-driven rubric scoring.

`score_candidate` is pure: it takes a JD and resume_data (both dicts) and
returns (total_score, criterion_breakdown).

The LLM produces per-criterion scores (1-5). The weighted total is computed
in Python from `WEIGHTS` below — keep weight logic out of the prompt so it
can be tuned without re-running the LLM.
"""

import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

from src.models import CriterionScores

load_dotenv()

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Did you copy .env.example to .env?"
            )
        _client = genai.Client(api_key=api_key)
    return _client


MODEL = "gemini-2.5-flash"

# Weights for combining criterion scores into a total. Tweak these to change
# how the system ranks without re-calling the LLM.
WEIGHTS: dict[str, float] = {
    "required_skills": 1.5,
    "experience_level": 1,
    "domain_fit": 1,
    "education": 0.5,
}  # Total should be a round figure,

# Identity fields stripped from the resume before sending to the LLM. The LLM
# doesn't need these to judge fit and excluding them reduces a bias surface.
IDENTITY_FIELDS = {"name", "email", "phone", "address", "photo_url"}


PROMPT_TEMPLATE = """You are scoring a candidate against a job description.

Job Description:
{jd}

Candidate:
{resume}

Score the candidate on each criterion from 1 to 5 using these anchors:

required_skills — how well the candidate's skills match the required skills.
  5 = matches all required skills with comparable depth
  4 = matches most required skills with strong depth
  3 = matches most required skills, gaps in depth or adjacent experience
  2 = matches some required skills, significant gaps
  1 = minimal overlap with required skills

experience_level — does years and seniority match what the role needs.
  5 = exceeds requirement meaningfully
  4 = matches requirement
  3 = slightly below
  2 = noticeably below
  1 = far below

domain_fit — relevance of industry/domain experience to the role's domain.
  5 = direct experience in the same domain
  4 = closely adjacent
  3 = somewhat related
  2 = unrelated but transferable
  1 = unrelated

education — does the candidate's education fit role expectations.
  5 = exceeds expectations
  4 = matches expectations
  3 = adjacent or slightly below
  2 = below expectations but compensated by experience
  1 = does not meet expectations

Score independently against the JD.
Return JSON only."""


def _build_prompt(jd: dict, resume_data: dict) -> str:
    safe_resume = {k: v for k, v in resume_data.items() if k not in IDENTITY_FIELDS}
    return PROMPT_TEMPLATE.format(
        jd=json.dumps(jd, indent=2),
        resume=json.dumps(safe_resume, indent=2),
    )


async def score_candidate(jd: dict, resume_data: dict) -> tuple[float, dict]:
    """Score one candidate. Returns (total_score, criterion_breakdown_dict).

    Raises on LLM error or schema validation failure — caller decides how to
    handle.
    """
    client = _get_client()
    prompt = _build_prompt(jd, resume_data)

    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=CriterionScores,
        ),
    )

    scores = CriterionScores.model_validate_json(response.text)
    breakdown = scores.model_dump()
    total = sum(breakdown[c] * w for c, w in WEIGHTS.items())
    return total, breakdown
