"""AI-powered job matching agent."""

from loguru import logger

from app.models.job import Job
from app.models.match import JobMatchResult
from app.models.resume import MasterResume
from app.prompts import load_prompt, render_prompt
from app.services.ollama_service import OllamaService


class JobMatcher:
    """Matches jobs against master resume using local Ollama."""

    def __init__(self, ollama: OllamaService) -> None:
        self._ollama = ollama
        self._prompt_template = load_prompt("job_matching.txt")

    async def match(self, resume: MasterResume, job: Job) -> JobMatchResult:
        """Compute match score and analysis for a job."""
        prompt = render_prompt(
            self._prompt_template,
            resume_json=resume.model_dump_json(indent=2),
            job_title=job.title,
            company=job.company,
            job_description=job.description,
        )

        logger.bind(component="job_matcher").info(
            "Matching job {} at {}", job.title, job.company
        )

        result = await self._ollama.generate_structured(prompt, JobMatchResult)
        logger.bind(component="job_matcher").info(
            "Match score for {}: {}", job.title, result.match_score
        )
        return result
