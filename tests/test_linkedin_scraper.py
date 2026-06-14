"""Scraper tests with mocked Playwright page."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.settings import Settings
from app.linkedin.scraper import LinkedInScraper


@pytest.fixture
def scraper(tmp_path):
    settings = Settings()
    settings.base_dir = tmp_path
    browser = MagicMock()
    browser.is_authenticated = True
    browser.page = AsyncMock()
    browser.ensure_authenticated = AsyncMock()
    return LinkedInScraper(settings, browser)


@pytest.mark.asyncio
async def test_has_easy_apply_button_true(scraper):
    button = AsyncMock()
    button.get_attribute = AsyncMock(return_value="Easy Apply to job")
    button.inner_text = AsyncMock(return_value="Easy Apply")
    scraper._browser.page.query_selector = AsyncMock(return_value=button)
    assert await scraper._has_easy_apply_button(scraper._browser.page) is True


@pytest.mark.asyncio
async def test_has_easy_apply_button_false(scraper):
    scraper._browser.page.query_selector = AsyncMock(return_value=None)
    assert await scraper._has_easy_apply_button(scraper._browser.page) is False


@pytest.mark.asyncio
async def test_search_jobs_parses_cards(scraper):
    page = scraper._browser.page
    page.goto = AsyncMock()
    page.evaluate = AsyncMock()
    page.query_selector_all = AsyncMock(return_value=[])

    jobs = await scraper.search_jobs("Engineer", "India", max_results=5)
    assert jobs == []
    page.goto.assert_awaited_once()


@pytest.mark.asyncio
async def test_card_indicates_easy_apply_from_footer(scraper):
    footer = AsyncMock()
    footer.inner_text = AsyncMock(return_value="Easy Apply")
    card = AsyncMock()
    card.query_selector_all = AsyncMock(return_value=[footer])
    card.inner_text = AsyncMock(return_value="Software Engineer\nAcme\nEasy Apply")

    assert await scraper._card_indicates_easy_apply(card) is True


@pytest.mark.asyncio
async def test_extract_card_fields_from_link(scraper):
    link = AsyncMock()
    link.get_attribute = AsyncMock(return_value="https://www.linkedin.com/jobs/view/999")
    link.inner_text = AsyncMock(return_value="Backend Engineer")

    card = AsyncMock()

    async def card_qs(selector):
        if "jobs/view" in selector:
            return link
        if "title" in selector or "h3" in selector:
            return None
        return None

    card.query_selector = AsyncMock(side_effect=card_qs)
    scraper._first_match = AsyncMock(side_effect=lambda root, sels: None)

    title, company, location, url, job_id = await scraper._extract_card_fields(card)
    assert title == "Backend Engineer"
    assert url.endswith("/jobs/view/999")
    assert job_id == "999"


@pytest.mark.asyncio
async def test_collect_job_cards_filters_non_jobs(scraper):
    job_card = AsyncMock()
    job_card.query_selector = AsyncMock(return_value=AsyncMock())
    empty_card = AsyncMock()
    empty_card.query_selector = AsyncMock(return_value=None)

    page = scraper._browser.page
    page.query_selector_all = AsyncMock(
        side_effect=lambda sel: [job_card, empty_card] if "scaffold" in sel else []
    )

    cards = await scraper._collect_job_cards(page)
    assert len(cards) == 1


@pytest.mark.asyncio
async def test_get_application_form_fields(scraper):
    inp = AsyncMock()
    inp.get_attribute = AsyncMock(side_effect=["Email", None])
    scraper._browser.page.goto = AsyncMock()
    scraper._browser.page.query_selector_all = AsyncMock(return_value=[inp])

    fields = await scraper.get_application_form_fields("https://linkedin.com/jobs/view/1")
    assert "Email" in fields
