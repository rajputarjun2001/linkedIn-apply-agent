"""Tests for utility modules."""

import pytest

from app.services.ollama_service import OllamaService
from app.utils.retry import async_retry, sync_retry


def test_sync_retry_succeeds_after_failure():
    calls = {"n": 0}

    @sync_retry(max_attempts=3, delay=0.01, exceptions=(ValueError,))
    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ValueError("fail")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_async_retry_raises_after_exhausted():
    @async_retry(max_attempts=2, delay=0.01, exceptions=(RuntimeError,))
    async def always_fail():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        await always_fail()


def test_ollama_extract_json_direct():
    data = OllamaService._extract_json('{"match_score": 50}')
    assert data["match_score"] == 50


def test_ollama_extract_json_from_fence():
    data = OllamaService._extract_json('```json\n{"match_score": 60}\n```')
    assert data["match_score"] == 60
