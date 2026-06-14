"""Job matching result models."""

from typing import Any, List

from pydantic import BaseModel, Field, field_validator


def _coerce_experience_item(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        title = str(item.get("title") or item.get("role") or "").strip()
        company = str(item.get("company") or "").strip()
        description = str(item.get("description") or "").strip()
        if title and company:
            return f"{title} at {company}" + (f": {description}" if description else "")
        return description or company or title or str(item)
    return str(item).strip()


class JobMatchResult(BaseModel):
    """Structured output from AI job matching."""

    match_score: int = Field(..., ge=0, le=100)
    missing_skills: List[str] = Field(default_factory=list)
    relevant_skills: List[str] = Field(default_factory=list)
    relevant_experience: List[str] = Field(default_factory=list)
    reasoning: str = Field(default="")
    recommendation: str = Field(default="")

    @field_validator("relevant_experience", mode="before")
    @classmethod
    def coerce_relevant_experience(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            return [_coerce_experience_item(value)]
        return [_coerce_experience_item(item) for item in value if item]
