"""Pydantic models for the LLM scoring response.

Each criterion is scored 1-5 with anchors defined in the prompt. The model
both constrains what the LLM is allowed to return (via Gemini's
response_schema) and validates the response when parsed.
"""

from pydantic import BaseModel, Field


class CriterionScores(BaseModel):
    required_skills: int = Field(ge=1, le=5)
    experience_level: int = Field(ge=1, le=5)
    domain_fit: int = Field(ge=1, le=5)
    education: int = Field(ge=1, le=5)
    reasoning: str
