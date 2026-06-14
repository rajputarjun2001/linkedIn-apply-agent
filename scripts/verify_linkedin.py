"""Runtime verification script for LinkedIn discovery (session-based auth)."""

import asyncio
import sys

from app.config.settings import get_settings
from app.container import Container
from app.linkedin.errors import LinkedInAuthError
from app.utils.logger import setup_logging


async def main() -> int:
    setup_logging()
    container = Container()
    await container.db.initialize()

    print("=== LinkedIn Discovery Verification ===")
    status = await container.linkedin_auth.status(verify=True)
    print(f"LinkedIn status: {status['label']}")
    if status["status"] != "connected":
        print("Connect LinkedIn from the dashboard (GET /linkedin/connect) first.")
        return 1

    try:
        await container.linkedin_browser.start(headless=True)
        await container.linkedin_browser.ensure_authenticated()
        jobs = await container.linkedin_scraper.search_jobs(
            "Software Engineer", "India", max_results=3
        )
        print(f"Jobs extracted: {len(jobs)}")
        for job in jobs:
            print(f"  - {job.title} @ {job.company} | EasyApply={job.is_easy_apply}")
            print(f"    URL: {job.apply_url}")

        sample_dir = get_settings().base_dir / "output" / "job_samples"
        samples = sorted(sample_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if samples:
            print(f"Sample file: {samples[0]}")

        return 0 if jobs else 2
    except LinkedInAuthError as exc:
        print(f"AUTH ERROR: {exc}")
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    finally:
        await container.linkedin_browser.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
