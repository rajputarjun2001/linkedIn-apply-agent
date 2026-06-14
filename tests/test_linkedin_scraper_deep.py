"""Deep scraper parse tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.settings import Settings
from app.linkedin.scraper import LinkedInScraper
from app.models.job import JobCreate


@pytest.fixture
def scraper(tmp_path):
    settings = Settings()
    settings.base_dir = tmp_path
    browser = MagicMock()
    browser.is_authenticated = True
    browser.page = AsyncMock()
    return LinkedInScraper(settings, browser)


@pytest.mark.asyncio
async def test_parse_job_card_easy_apply(scraper):
    card = AsyncMock()
    card.inner_text = AsyncMock(return_value="Software Engineer\nAcme\nEasy Apply")
    card.query_selector_all = AsyncMock(return_value=[])
    title_el = AsyncMock()
    title_el.inner_text = AsyncMock(return_value="Software Engineer")
    company_el = AsyncMock()
    company_el.inner_text = AsyncMock(return_value="Acme")
    location_el = AsyncMock()
    location_el.inner_text = AsyncMock(return_value="India")
    link_el = AsyncMock()
    link_el.get_attribute = AsyncMock(return_value="https://www.linkedin.com/jobs/view/12345")

    card.query_selector = AsyncMock(side_effect=lambda sel: {
        "h3": title_el,
        "h4": company_el,
    }.get(sel.split(",")[0].strip(), None))

    async def qs_side_effect(selector):
        if "h3" in selector or "title" in selector:
            return title_el
        if "h4" in selector or "company" in selector or "subtitle" in selector:
            return company_el
        if "location" in selector or "metadata" in selector or "caption" in selector:
            return location_el
        if "href" in selector:
            return link_el
        if "description" in selector:
            desc = AsyncMock()
            desc.inner_text = AsyncMock(return_value="Python developer role")
            return desc
        if "posted" in selector or "subtitle-primary" in selector:
            return None
        if "Easy Apply" in selector or "jobs-apply" in selector:
            btn = AsyncMock()
            btn.get_attribute = AsyncMock(return_value="Easy Apply")
            btn.inner_text = AsyncMock(return_value="Easy Apply")
            return btn
        return None

    page = scraper._browser.page
    page.query_selector = AsyncMock(side_effect=qs_side_effect)
    title_el.click = AsyncMock()

    card.query_selector = page.query_selector

    job = await scraper._parse_job_card(
        card, "Engineer", "India", page, easy_apply_search=True
    )
    assert job is not None
    assert job.is_easy_apply is True
    assert job.title == "Software Engineer"


@pytest.mark.asyncio
async def test_search_all_configured_handles_errors(scraper):
    scraper.search_jobs = AsyncMock(side_effect=RuntimeError("fail"))
    scraper._browser.recover_from_crash = AsyncMock()
    scraper._settings.job_keywords = "Engineer"
    scraper._settings.locations = "India"

    jobs = await scraper.search_all_configured(max_per_search=1)
    assert jobs == []
    scraper._browser.recover_from_crash.assert_awaited()
