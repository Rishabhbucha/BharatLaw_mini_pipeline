from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from config import NORMALIZED_DIR, ensure_output_dirs, url_hash


def normalize_from_crawl_index(crawl_index: Path, output_index: Path) -> list[dict]:
    ensure_output_dirs()
    records: list[dict] = []
    for line in crawl_index.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        crawl_record = json.loads(line)
        raw_path = Path(crawl_record.get("path_to_raw", ""))
        if not raw_path.exists():
            continue
        status = crawl_record.get("status")
        # Accept 200, or 404 when the server still returned a substantive HTML body
        # (incometaxindia.gov.in returns HTTP 404 but serves the real page content).
        try:
            size = raw_path.stat().st_size
        except OSError:
            continue
        if status == 200:
            pass
        elif status == 404 and raw_path.suffix.lower() == ".html" and size > 40000:
            pass
        else:
            continue

        source_type = "pdf" if raw_path.suffix.lower() == ".pdf" else "html"
        if source_type == "pdf":
            title, markdown = _pdf_to_markdown(raw_path)
        else:
            title, markdown = _html_to_markdown(raw_path)

        markdown = _clean_text(markdown)
        digest = url_hash(crawl_record["url"])
        out_path = NORMALIZED_DIR / f"{digest}.md"
        out_path.write_text(markdown, encoding="utf-8")
        records.append(
            {
                "url": crawl_record["url"],
                "url_hash": digest,
                "source_type": source_type,
                "title": title or crawl_record["url"],
                "detected_language": "en",
                "char_count": len(markdown),
                "path_to_text": str(out_path.relative_to(Path.cwd())),
            }
        )

    with output_index.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return records


def _html_to_markdown(path: Path) -> tuple[str, str]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    elif soup.find(["h1", "h2"]):
        title = soup.find(["h1", "h2"]).get_text(" ", strip=True)

    parts: list[str] = []
    for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "table"]):
        text = element.get_text(" ", strip=True)
        if not text:
            continue
        if element.name and element.name.startswith("h"):
            level = min(int(element.name[1]), 4)
            parts.append(f"{'#' * level} {text}")
        elif element.name == "li":
            parts.append(f"- {text}")
        elif element.name == "table":
            parts.append(_table_to_markdown(element))
        else:
            parts.append(text)
    return title, "\n\n".join(parts)


def _pdf_to_markdown(path: Path) -> tuple[str, str]:
    pages: list[str] = []
    try:
        import fitz

        doc = fitz.open(path)
        title = doc.metadata.get("title") or path.stem
        for i, page in enumerate(doc, start=1):
            pages.append(f"## Page {i}\n\n{page.get_text('text')}")
        return title, "\n\n".join(pages)
    except Exception:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        title = (reader.metadata.title if reader.metadata else None) or path.stem
        for i, page in enumerate(reader.pages, start=1):
            pages.append(f"## Page {i}\n\n{page.extract_text() or ''}")
        return title, "\n\n".join(pages)


def _table_to_markdown(table) -> str:
    rows = []
    for tr in table.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    header = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join(["---"] * width) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join([header, sep, *body])


def _clean_text(text: str) -> str:
    # Normalize exotic Unicode line separators (NEL \x85, LS \u2028, PS \u2029,
    # form feed \x0c) to plain newlines before JSON serialization.
    # splitlines() treats these as line breaks but json.dumps(ensure_ascii=False)
    # does NOT escape them, which breaks JSONL readers that use splitlines().
    text = re.sub(r"[\x85\x0c\u2028\u2029]", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"
