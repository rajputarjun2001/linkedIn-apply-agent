"""Ollama LLM service for local AI inference."""

import json
import re
from typing import Any, Dict, List, Optional, Type, TypeVar

import httpx
from loguru import logger
from pydantic import BaseModel, ValidationError

from app.config.settings import Settings
from app.utils.retry import async_retry

T = TypeVar("T", bound=BaseModel)


class OllamaUnavailableError(RuntimeError):
    """Raised when Ollama is not reachable or model is missing."""


class OllamaService:
    """Client for Ollama generate API with structured JSON parsing."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        self._timeout = settings.ollama_timeout

    @async_retry(max_attempts=3, delay=1.0, exceptions=(httpx.HTTPError, json.JSONDecodeError))
    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Generate text completion from Ollama."""
        await self.ensure_ready()

        payload: Dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f"{self._base_url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """Extract JSON object from LLM response text."""
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            return json.loads(fence_match.group(1))

        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            return json.loads(brace_match.group(0))

        raise json.JSONDecodeError("No JSON found in response", text, 0)

    async def generate_structured(
        self,
        prompt: str,
        model_class: Type[T],
        system: Optional[str] = None,
        temperature: float = 0.1,
    ) -> T:
        """Generate and parse structured Pydantic model from Ollama."""
        system_prompt = system or (
            "You are a precise assistant that responds only with valid JSON. "
            "No markdown, no explanations outside JSON."
        )

        raw = await self.generate(prompt, system=system_prompt, temperature=temperature)
        logger.bind(component="ollama").debug("Raw LLM response length: {}", len(raw))

        try:
            parsed = self._extract_json(raw)
            return model_class.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.bind(component="ollama").error(
                "Failed to parse structured output: {} | raw={}", exc, raw[:500]
            )
            raise ValueError(f"Invalid structured response from Ollama: {exc}") from exc

    async def health_check(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def list_models(self) -> List[str]:
        """Return installed Ollama model names."""
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self._base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return [m.get("name", "") for m in data.get("models", [])]

    async def model_exists(self) -> bool:
        """Check configured model is available."""
        if not await self.health_check():
            return False
        models = await self.list_models()
        target = self._model
        return any(m == target or m.startswith(f"{target}:") for m in models)

    async def ensure_ready(self) -> None:
        """Verify Ollama connectivity and model availability."""
        if not await self.health_check():
            raise OllamaUnavailableError(
                f"Ollama is not reachable at {self._base_url}. "
                "Start Ollama with: ollama serve"
            )
        if not await self.model_exists():
            models = await self.list_models()
            raise OllamaUnavailableError(
                f"Model '{self._model}' not found. Installed: {models}. "
                f"Run: ollama pull {self._model}"
            )

    async def status(self) -> Dict[str, Any]:
        """Return detailed Ollama status."""
        connected = await self.health_check()
        models: List[str] = []
        model_ready = False
        if connected:
            models = await self.list_models()
            model_ready = any(
                m == self._model or m.startswith(f"{self._model}:")
                for m in models
            )
        return {
            "connected": connected,
            "model": self._model,
            "model_ready": model_ready,
            "installed_models": models,
            "base_url": self._base_url,
        }
