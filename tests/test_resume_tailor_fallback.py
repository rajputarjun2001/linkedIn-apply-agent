"""Resume tailor fabrication fallback test."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.resume_tailor import ResumeFabricationError, ResumeTailor
from app.models.job import Job
from app.models.resume import MasterResume, Skill, TailoredResume
from app.services.ollama_service import OllamaService
from app.config.settings import Settings


@pytest.mark.asyncio
async def test_tailor_falls_back_on_fabrication():
    settings = Settings()
    tailor = ResumeTailor(OllamaService(settings))
    master = MasterResume(full_name="A", email="a@b.com", skills=[Skill(name="Python")])
    job = Job(
        id=1,
        title="Dev",
        company="Co",
        description="python",
        apply_url="https://linkedin.com/jobs/view/1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    fabricated = TailoredResume(
        full_name="A",
        email="a@b.com",
        skills=[Skill(name="FakeSkill")],
    )

    with patch.object(tailor._ollama, "generate_structured", AsyncMock(return_value=fabricated)):
        result = await tailor.tailor(master, job)
        assert result.skills[0].name == "Python"
