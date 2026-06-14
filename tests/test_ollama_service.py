"""Tests for Ollama service."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config.settings import Settings
from app.models.match import JobMatchResult
from app.services.ollama_service import OllamaService, OllamaUnavailableError


@pytest.fixture
def ollama_service():
    return OllamaService(Settings())


@pytest.mark.asyncio
async def test_health_check_false_when_unreachable(ollama_service):
    with patch.object(ollama_service, "_base_url", "http://127.0.0.1:59999"):
        assert await ollama_service.health_check() is False


@pytest.mark.asyncio
async def test_ensure_ready_raises_when_disconnected(ollama_service):
    with patch.object(ollama_service, "health_check", AsyncMock(return_value=False)):
        with pytest.raises(OllamaUnavailableError, match="not reachable"):
            await ollama_service.ensure_ready()


@pytest.mark.asyncio
async def test_ensure_ready_raises_when_model_missing(ollama_service):
    with patch.object(ollama_service, "health_check", AsyncMock(return_value=True)):
        with patch.object(ollama_service, "list_models", AsyncMock(return_value=["other"])):
            with pytest.raises(OllamaUnavailableError, match="not found"):
                await ollama_service.ensure_ready()


@pytest.mark.asyncio
async def test_generate_structured_parses_json(ollama_service):
    payload = JobMatchResult(
        match_score=80,
        missing_skills=["Go"],
        relevant_skills=["Python"],
        relevant_experience=["Built APIs"],
        reasoning="Good fit",
        recommendation="apply",
    )
    with patch.object(ollama_service, "generate", AsyncMock(return_value=payload.model_dump_json())):
        with patch.object(ollama_service, "ensure_ready", AsyncMock()):
            result = await ollama_service.generate_structured("prompt", JobMatchResult)
            assert result.match_score == 80


@pytest.mark.asyncio
async def test_status_structure(ollama_service):
    with patch.object(ollama_service, "health_check", AsyncMock(return_value=False)):
        status = await ollama_service.status()
        assert status["connected"] is False
        assert "model" in status
