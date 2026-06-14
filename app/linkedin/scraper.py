"""LinkedIn job search and Easy Apply scraping."""

import asyncio
import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from loguru import logger
from playwright.async_api import TimeoutError as PlaywrightTimeout

from app.config.settings import Settings
from app.linkedin.browser import LinkedInBrowser
from app.models.job import JobCreate


class LinkedInScraper:
    """Scrapes LinkedIn for Easy Apply jobs matching configured keywords."""

    BASE_JOBS_URL = "https://www.linkedin.com/jobs/search/"

    JOB_CARD_SELECTORS = (
        "li.scaffold-layout__list-item",
        "ul.jobs-search__results-list li",
        "div.job-card-container",
        "div.base-card[data-entity-urn]",
    )
    TITLE_SELECTORS = (
        "a.job-card-container__link strong",
        "a.job-card-list__title-link",
        ".job-card-list__title",
        ".job-card-container__link",
        "h3",
        "a[data-tracking-control-name*='job-search-card']",
    )
    COMPANY_SELECTORS = (
        ".job-card-container__company-name",
        ".job-card-container__primary-description",
        "h4",
        ".artdeco-entity-lockup__subtitle",
    )
    LOCATION_SELECTORS = (
        ".job-card-container__metadata-item",
        ".job-search-card__location",
        ".artdeco-entity-lockup__caption",
    )
    EASY_APPLY_SELECTORS = (
        "button.jobs-apply-button",
        "button[aria-label*='Easy Apply']",
        "button:has-text('Easy Apply')",
        ".jobs-apply-button",
    )
    EASY_APPLY_CARD_SELECTORS = (
        ".job-card-container__footer-item",
        ".job-card-list__footer-item",
        "li.job-card-container__footer-item",
        "span.job-card-container__footer-item",
    )
    DESCRIPTION_SELECTORS = (
        ".jobs-description__content",
        ".jobs-box__html-content",
        "#job-details .jobs-description",
        "div.jobs-description-content__text",
        ".jobs-description__container",
    )
    DETAIL_PANEL_SELECTORS = (
        ".jobs-search__job-details",
        ".jobs-details",
        ".job-view-layout",
    )

    def __init__(self, settings: Settings, browser: LinkedInBrowser) -> None:
        self._settings = settings
        self._browser = browser
        self._sample_dir = settings.base_dir / "output" / "job_samples"
        self._sample_dir.mkdir(parents=True, exist_ok=True)

    def _build_search_url(self, keyword: str, location: str) -> str:
        """Build LinkedIn job search URL with Easy Apply filter."""
        params = {
            "keywords": keyword,
            "location": location,
            "f_AL": "true",
            "f_TPR": "r604800",
            "sortBy": "DD",
        }
        return self.BASE_JOBS_URL + "?" + urllib.parse.urlencode(params)

    def _save_job_samples(self, jobs: List[JobCreate], keyword: str, location: str) -> None:
        """Persist extracted job samples for verification."""
        if not jobs:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self._sample_dir / f"jobs_{keyword.replace(' ', '_')}_{location}_{stamp}.json"
        payload = [job.model_dump() for job in jobs[:5]]
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        logger.bind(component="linkedin_scraper").info(
            "Saved {} job samples to {}", len(payload), path
        )

    async def _first_match(self, root, selectors: tuple[str, ...]):
        """Return first element matching any selector."""
        for selector in selectors:
            element = await root.query_selector(selector)
            if element:
                return element
        return None

    async def _text_from(self, element) -> str:
        if not element:
            return ""
        return (await element.inner_text()).strip()

    async def _collect_job_cards(self, page) -> list:
        """Collect job cards that contain a LinkedIn job view link."""
        cards: list = []
        for selector in self.JOB_CARD_SELECTORS:
            elements = await page.query_selector_all(selector)
            if not elements:
                continue
            for element in elements:
                if await element.query_selector("a[href*='/jobs/view/']"):
                    cards.append(element)
            if cards:
                logger.bind(component="linkedin_scraper").info(
                    "Found {} job cards via selector '{}'", len(cards), selector
                )
                return cards

        links = await page.query_selector_all("a[href*='/jobs/view/']")
        logger.bind(component="linkedin_scraper").warning(
            "No standard cards found, falling back to {} job links", len(links)
        )
        return links

    async def _card_indicates_easy_apply(self, card) -> bool:
        """Detect Easy Apply badge on a search result card."""
        for selector in self.EASY_APPLY_CARD_SELECTORS:
            elements = await card.query_selector_all(selector)
            for element in elements:
                text = (await element.inner_text()).strip().lower()
                if "easy apply" in text:
                    return True

        card_text = (await card.inner_text()).strip().lower()
        return "easy apply" in card_text

    async def search_jobs(
        self,
        keyword: str,
        location: str,
        max_results: int = 25,
    ) -> List[JobCreate]:
        """Search LinkedIn for Easy Apply jobs."""
        if not self._browser.is_authenticated:
            await self._browser.ensure_authenticated()

        page = self._browser.page
        search_url = self._build_search_url(keyword, location)

        logger.bind(component="linkedin_scraper").info(
            "Searching: '{}' in '{}' (Easy Apply only)", keyword, location
        )

        await page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
        await asyncio.sleep(3)

        jobs: List[JobCreate] = []
        seen_urls: set[str] = set()
        skipped = 0

        for _ in range(4):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)

        job_cards = await self._collect_job_cards(page)

        for card in job_cards[: max_results * 3]:
            if len(jobs) >= max_results:
                break
            try:
                job = await self._parse_job_card(
                    card, keyword, location, page, easy_apply_search=True
                )
                if job and job.apply_url not in seen_urls:
                    seen_urls.add(job.apply_url)
                    jobs.append(job)
                elif job is None:
                    skipped += 1
            except Exception as exc:
                skipped += 1
                logger.bind(component="linkedin_scraper").warning(
                    "Failed to parse job card: {}", exc
                )

        logger.bind(component="linkedin_scraper").info(
            "Extracted {} Easy Apply jobs for '{}' (skipped {})",
            len(jobs),
            keyword,
            skipped,
        )
        self._save_job_samples(jobs, keyword, location)
        return jobs

    async def _has_easy_apply_button(self, page) -> bool:
        for selector in self.EASY_APPLY_SELECTORS:
            element = await page.query_selector(selector)
            if element:
                label = await element.get_attribute("aria-label") or ""
                text = (await element.inner_text()).strip().lower()
                if "easy apply" in label.lower() or "easy apply" in text:
                    return True
        return False

    async def _extract_card_fields(self, card) -> tuple[str, str, str, str, Optional[str]]:
        """Extract title, company, location, apply URL, and job id from a card."""
        link_el = await card.query_selector("a[href*='/jobs/view/']")
        if not link_el and await card.get_attribute("href"):
            link_el = card

        title_el = await self._first_match(card, self.TITLE_SELECTORS)
        company_el = await self._first_match(card, self.COMPANY_SELECTORS)
        location_el = await self._first_match(card, self.LOCATION_SELECTORS)

        title = await self._text_from(title_el)
        if not title and link_el:
            title = await self._text_from(link_el)
            aria = (await link_el.get_attribute("aria-label") or "").strip()
            if aria and not title:
                title = aria

        company = await self._text_from(company_el)
        job_location = await self._text_from(location_el)

        href = await link_el.get_attribute("href") if link_el else None
        if not href:
            return "", "", "", "", None

        apply_url = href if href.startswith("http") else f"https://www.linkedin.com{href}"
        apply_url = apply_url.split("?")[0]
        linkedin_job_id = self._extract_job_id(apply_url)
        return title, company, job_location, apply_url, linkedin_job_id

    async def _load_job_details(self, card, page, title: str) -> tuple[str, str, bool]:
        """Open job details panel and extract description, date, and Easy Apply state."""
        description = ""
        posting_date = ""
        is_easy_apply = await self._card_indicates_easy_apply(card)

        try:
            click_target = (
                await card.query_selector("a[href*='/jobs/view/']")
                or await self._first_match(card, self.TITLE_SELECTORS)
                or card
            )
            if click_target:
                await click_target.click()
                for selector in self.DETAIL_PANEL_SELECTORS:
                    try:
                        await page.wait_for_selector(selector, timeout=5000)
                        break
                    except Exception:
                        continue
                await asyncio.sleep(1.5)

            for selector in self.DESCRIPTION_SELECTORS:
                desc_el = await page.query_selector(selector)
                if desc_el:
                    description = (await desc_el.inner_text()).strip()
                    break

            date_el = await page.query_selector(
                ".jobs-unified-top-card__posted-date, "
                "span.jobs-unified-top-card__subtitle-primary-grouping, "
                ".job-details-jobs-unified-top-card__primary-description-container, "
                ".jobs-unified-top-card__subtitle-primary-grouping"
            )
            if date_el:
                posting_date = (await date_el.inner_text()).strip()

            if await self._has_easy_apply_button(page):
                is_easy_apply = True
        except Exception as exc:
            logger.bind(component="linkedin_scraper").warning(
                "Error loading job details for {}: {}", title, exc
            )

        return description, posting_date, is_easy_apply

    async def _parse_job_card(
        self,
        card,
        keyword: str,
        location: str,
        page,
        easy_apply_search: bool = True,
    ) -> Optional[JobCreate]:
        """Parse a single job listing card."""
        title, company, job_location, apply_url, linkedin_job_id = (
            await self._extract_card_fields(card)
        )

        if not title or not apply_url:
            logger.bind(component="linkedin_scraper").debug(
                "Skipping card without title/url (title={!r}, url={!r})",
                title,
                apply_url,
            )
            return None

        if not job_location:
            job_location = location

        description, posting_date, is_easy_apply = await self._load_job_details(
            card, page, title
        )

        if easy_apply_search and not is_easy_apply:
            # Search URL uses f_AL=true; trust filtered results if we have a valid job id.
            is_easy_apply = linkedin_job_id is not None

        if not is_easy_apply:
            logger.bind(component="linkedin_scraper").debug(
                "Skipping non-Easy Apply job: {} at {}", title, company
            )
            return None

        return JobCreate(
            title=title,
            company=company or "Unknown",
            location=job_location,
            description=description,
            apply_url=apply_url,
            posting_date=posting_date,
            keyword=keyword,
            search_location=location,
            is_easy_apply=True,
            linkedin_job_id=linkedin_job_id,
        )

    @staticmethod
    def _extract_job_id(url: str) -> Optional[str]:
        match = re.search(r"jobs/view/(\d+)", url)
        return match.group(1) if match else None

    async def search_all_configured(self, max_per_search: int = 15) -> List[JobCreate]:
        """Run searches for all configured keywords and locations."""
        all_jobs: List[JobCreate] = []
        seen: set[str] = set()

        for keyword in self._settings.job_keyword_list:
            for location in self._settings.location_list:
                try:
                    jobs = await self.search_jobs(keyword, location, max_per_search)
                    for job in jobs:
                        if job.apply_url not in seen:
                            seen.add(job.apply_url)
                            all_jobs.append(job)
                    await asyncio.sleep(2)
                except PlaywrightTimeout as exc:
                    logger.bind(component="linkedin_scraper").error(
                        "Timeout searching '{}' in '{}': {}", keyword, location, exc
                    )
                    await self._browser.recover_from_crash()
                except Exception as exc:
                    logger.bind(component="linkedin_scraper").error(
                        "Search failed for '{}' in '{}': {}", keyword, location, exc
                    )
                    try:
                        await self._browser.recover_from_crash()
                    except Exception as recover_exc:
                        logger.bind(component="linkedin_scraper").error(
                            "Browser recovery failed: {}", recover_exc
                        )

        return all_jobs

    async def get_application_form_fields(self, apply_url: str) -> dict[str, str]:
        """Inspect Easy Apply form fields for application preview."""
        page = self._browser.page
        await page.goto(apply_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)

        fields: dict[str, str] = {}
        inputs = await page.query_selector_all("input, textarea, select")
        for inp in inputs:
            label = await inp.get_attribute("aria-label") or await inp.get_attribute("name")
            if label:
                fields[label] = "[Requires manual input or approval]"

        return fields
