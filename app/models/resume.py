"""Resume domain models with Pydantic validation."""

from __future__ import annotations

from datetime import date as DateType
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl


class Skill(BaseModel):
    """A skill entry on the resume."""

    name: str = Field(..., min_length=1)
    category: Optional[str] = None
    proficiency: Optional[str] = None
    years: Optional[float] = None


class Project(BaseModel):
    """A project entry on the resume."""

    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    technologies: List[str] = Field(default_factory=list)
    url: Optional[HttpUrl] = None
    start_date: Optional[DateType] = None
    end_date: Optional[DateType] = None
    highlights: List[str] = Field(default_factory=list)


class WorkExperience(BaseModel):
    """A work experience entry on the resume."""

    company: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    location: Optional[str] = None
    start_date: Optional[DateType] = None
    end_date: Optional[DateType] = None
    is_current: bool = False
    description: Optional[str] = None
    achievements: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)


class Education(BaseModel):
    """An education entry on the resume."""

    institution: str = Field(..., min_length=1)
    degree: str = Field(..., min_length=1)
    field_of_study: Optional[str] = None
    start_date: Optional[DateType] = None
    end_date: Optional[DateType] = None
    gpa: Optional[str] = None
    honors: List[str] = Field(default_factory=list)


class Certification(BaseModel):
    """A certification entry on the resume."""

    name: str = Field(..., min_length=1)
    issuer: Optional[str] = None
    issue_date: Optional[DateType] = None
    expiry_date: Optional[DateType] = None
    credential_id: Optional[str] = None
    url: Optional[HttpUrl] = None


class Achievement(BaseModel):
    """A standalone achievement entry."""

    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    achieved_date: Optional[DateType] = None


class MasterResume(BaseModel):
    """Complete master resume stored as JSON."""

    full_name: str = Field(..., min_length=1)
    email: EmailStr
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[HttpUrl] = None
    github_url: Optional[HttpUrl] = None
    portfolio_url: Optional[HttpUrl] = None
    summary: Optional[str] = None
    skills: List[Skill] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    work_experience: List[WorkExperience] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    certifications: List[Certification] = Field(default_factory=list)
    achievements: List[Achievement] = Field(default_factory=list)


class TailoredResume(MasterResume):
    """Tailored resume derived from master resume for a specific job."""

    job_id: Optional[int] = None
    tailored_summary: Optional[str] = None
    relevance_notes: Optional[str] = None
    skill_order: List[str] = Field(default_factory=list)
    project_order: List[str] = Field(default_factory=list)
    experience_order: List[str] = Field(default_factory=list)
