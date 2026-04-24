from __future__ import annotations

import json
import re
from pathlib import Path

from config import CHUNKS_DIR, ensure_output_dirs


# Assignment target: 400-800 tokens/chunk. We estimate tokens as words * 1.5
# (closer to tiktoken on English legal text than the old 1.3 multiplier).
# Word targets below therefore map to ~420-780 estimated tokens.
TARGET_MIN_WORDS = 280
TARGET_MAX_WORDS = 520
OVERLAP_WORDS = 70
TOKEN_PER_WORD = 1.5
# Navigation-only shells (OJS admin pages etc.) produce 20-word "chunks"
# that drag down average chunk size. Skip them here.
MIN_DOC_WORDS = 220


def create_chunks(normalized_index: Path, output_path: Path) -> list[dict]:
    ensure_output_dirs()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chunks: list[dict] = []
    for line in normalized_index.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        text_path = Path(record["path_to_text"])
        text = text_path.read_text(encoding="utf-8")
        chunks.extend(_chunk_document(record, text))

    with output_path.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    return chunks


def _chunk_document(record: dict, text: str) -> list[dict]:
    # Skip navigation-only shells so the overall chunk stats stay meaningful.
    if _word_count(text) < MIN_DOC_WORDS:
        return []
    blocks = _semantic_blocks(text)
    chunks: list[dict] = []
    current: list[dict] = []
    current_words = 0
    current_start = 0

    for block in blocks:
        words = _word_count(block["text"])
        if current and current_words + words > TARGET_MAX_WORDS:
            chunks.append(_make_chunk(record, chunks, current, current_start))
            overlap = _overlap_blocks(current)
            current = overlap
            current_words = sum(_word_count(item["text"]) for item in current)
            current_start = current[0]["start"] if current else block["start"]
        if not current:
            current_start = block["start"]
        current.append(block)
        current_words += words

        if current_words >= TARGET_MIN_WORDS and block["kind"] == "heading":
            chunks.append(_make_chunk(record, chunks, current, current_start))
            current = []
            current_words = 0

    if current:
        chunks.append(_make_chunk(record, chunks, current, current_start))
    return chunks


def _semantic_blocks(text: str) -> list[dict]:
    blocks: list[dict] = []
    position = 0
    section_path: list[str] = []
    page_no = None
    for raw in re.split(r"\n\s*\n", text):
        block = raw.strip()
        start = text.find(raw, position)
        position = start + len(raw) if start >= 0 else position
        if not block:
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", block)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            if title.lower().startswith("page "):
                page_match = re.search(r"\d+", title)
                page_no = int(page_match.group()) if page_match else page_no
            section_path = section_path[: level - 1] + [title]
            kind = "heading"
        else:
            kind = "paragraph"
        blocks.append({"text": block, "start": max(start, 0), "kind": kind, "section_path": list(section_path), "page_no": page_no})
    return blocks


def _make_chunk(record: dict, existing: list[dict], blocks: list[dict], char_start: int) -> dict:
    text = "\n\n".join(block["text"] for block in blocks).strip()
    char_end = char_start + len(text)
    return {
        "chunk_id": f"{record['url_hash']}:{len(existing) + 1:04d}",
        "url": record["url"],
        "title": record.get("title", ""),
        "section_path": blocks[-1].get("section_path", []),
        "page_no": blocks[-1].get("page_no"),
        "char_start": char_start,
        "char_end": char_end,
        "token_estimate": max(1, int(_word_count(text) * TOKEN_PER_WORD)),
        "text": text,
    }


def _overlap_blocks(blocks: list[dict]) -> list[dict]:
    selected: list[dict] = []
    total = 0
    for block in reversed(blocks):
        selected.append(block)
        total += _word_count(block["text"])
        if total >= OVERLAP_WORDS:
            break
    return list(reversed(selected))


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))
