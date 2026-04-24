from __future__ import annotations

import json
import mimetypes
import time
from collections import deque
from pathlib import Path
from typing import Iterable
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from config import DEFAULT_MAX_PAGES, MAX_DEPTH, RAW_DIR, REQUEST_TIMEOUT, USER_AGENT, ensure_output_dirs, url_hash, utc_now_iso


class PoliteCrawler:
    def __init__(self, delay_seconds: float = 1.0, max_depth: int = MAX_DEPTH, max_pages: int = DEFAULT_MAX_PAGES):
        self.delay_seconds = delay_seconds
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.7",
                "Accept-Language": "en-IN,en;q=0.9",
            }
        )
        self._robots: dict[str, RobotFileParser] = {}

    def crawl(self, seeds: dict[str, str] | Iterable[str], index_path: Path) -> list[dict]:
        ensure_output_dirs()
        seed_urls = list(seeds.values() if isinstance(seeds, dict) else seeds)
        queue: deque[tuple[str, int]] = deque((url, 0) for url in seed_urls)
        seen: set[str] = set()
        records: list[dict] = []

        while queue and len(records) < self.max_pages:
            url, depth = queue.popleft()
            normalized_url = self._normalize_url(url)
            if normalized_url in seen or depth > self.max_depth:
                continue
            seen.add(normalized_url)

            if not self._allowed(normalized_url):
                records.append(self._blocked_record(normalized_url))
                continue

            record, links = self._fetch_and_store(normalized_url)
            records.append(record)
            status = record.get("status")
            # Some sites (e.g. incometaxindia.gov.in) return HTTP 404 but serve the real
            # page body. Follow links from those too so crawling isn't stuck.
            followable = status == 200 or (
                status == 404 and record.get("path_to_raw")
                and Path(record["path_to_raw"]).suffix.lower() == ".html"
            )
            if followable and record.get("content_type", "").startswith("text/html"):
                for link in links:
                    if len(seen) + len(queue) >= self.max_pages * 4:
                        break
                    if self._same_site_or_seed(link, seed_urls):
                        queue.append((link, depth + 1))
            time.sleep(self.delay_seconds)

        with index_path.open("w", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return records

    def _fetch_and_store(self, url: str) -> tuple[dict, list[str]]:
        last_error = None
        response = None
        for attempt in range(3):
            try:
                response = self.session.get(url, timeout=REQUEST_TIMEOUT)
                if response.status_code < 500:
                    break
            except requests.RequestException as exc:
                last_error = str(exc)
            time.sleep(2**attempt)

        if response is None:
            return self._error_record(url, last_error or "request failed"), []

        content_type = response.headers.get("Content-Type", mimetypes.guess_type(url)[0] or "application/octet-stream").split(";")[0].strip()
        extension = ".pdf" if "pdf" in content_type or url.lower().endswith(".pdf") else ".html"
        raw_path = RAW_DIR / f"{url_hash(url)}{extension}"
        raw_path.write_bytes(response.content)

        links: list[str] = []
        used_js = False
        if response.ok and extension == ".html":
            text = response.text
            if self._looks_js_empty(text):
                rendered = self._try_render_with_playwright(url)
                if rendered:
                    raw_path.write_text(rendered, encoding="utf-8")
                    text = rendered
                    used_js = True
            links = self._extract_links(url, text)

        return {
            "url": url,
            "status": response.status_code,
            "content_type": content_type,
            "used_js": used_js,
            "timestamp": utc_now_iso(),
            "path_to_raw": str(raw_path.relative_to(Path.cwd())),
        }, links

    def _allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._robots:
            parser = RobotFileParser()
            parser.set_url(urljoin(base, "/robots.txt"))
            try:
                parser.read()
            except Exception:
                return True
            self._robots[base] = parser
        return self._robots[base].can_fetch(USER_AGENT, url)

    def _blocked_record(self, url: str) -> dict:
        return {
            "url": url,
            "status": "blocked_by_robots",
            "content_type": "",
            "used_js": False,
            "timestamp": utc_now_iso(),
            "path_to_raw": "",
        }

    def _error_record(self, url: str, error: str) -> dict:
        return {
            "url": url,
            "status": "error",
            "error": error,
            "content_type": "",
            "used_js": False,
            "timestamp": utc_now_iso(),
            "path_to_raw": "",
        }

    @staticmethod
    def _normalize_url(url: str) -> str:
        return urldefrag(url)[0].strip()

    @staticmethod
    def _same_site_or_seed(url: str, seeds: list[str]) -> bool:
        host = urlparse(url).netloc.lower()
        return any(host == urlparse(seed).netloc.lower() for seed in seeds)

    @staticmethod
    def _extract_links(base_url: str, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for tag in soup.select("a[href]"):
            href = tag.get("href")
            if href:
                full_url = urldefrag(urljoin(base_url, href))[0]
                if full_url.startswith(("http://", "https://")):
                    links.append(full_url)
        return list(dict.fromkeys(links))

    @staticmethod
    def _looks_js_empty(html: str) -> bool:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        script_count = len(soup.find_all("script"))
        return len(text) < 250 and script_count >= 3

    @staticmethod
    def _try_render_with_playwright(url: str) -> str | None:
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=USER_AGENT)
                page.goto(url, wait_until="networkidle", timeout=REQUEST_TIMEOUT * 1000)
                html = page.content()
                browser.close()
                return html
        except Exception:
            return None


def load_seed_urls(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))
