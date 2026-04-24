from __future__ import annotations

import json
import re
from pathlib import Path

from config import DATA_DIR

SECTION_RE = re.compile(
    r"\b(?:section|sections|sec\.?|article|articles|rule|rules|order)\s+"
    r"(?:[IVXLCDM]+|[A-Z]?\d+[A-Z]?)(?:\s*\([^)]+\))*",
    re.IGNORECASE,
)
ORDER_RULE_RE = re.compile(r"\bOrder\s+[IVXLCDM\d]+\s+Rule\s+\d+[A-Z]?\b", re.IGNORECASE)
SUB_SECTION_RE = re.compile(r"\bSub-section\s+\([^)]+\)\s+of\s+Section\s+\d+[A-Z]?\b", re.IGNORECASE)
CLAUSE_RE = re.compile(r"\bClause\s+\([^)]+\)\s+of\s+Sub-section\s+\([^)]+\)\s+of\s+Section\s+\d+[A-Z]?\b", re.IGNORECASE)
DATE_RE = re.compile(
    r"\b(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}\s+"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4})\b",
    re.IGNORECASE,
)
MONEY_RE = re.compile(r"(?:₹|Rs\.?|INR|USD|\$)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:crore|lakh|million|billion))?", re.IGNORECASE)
ACT_RE = re.compile(r"\b[A-Z][A-Za-z-]*(?:\s+(?:of|and|the|[A-Z][A-Za-z-]*)){0,8}\s+Act(?:,?\s+\d{4})?\b")
NOTIFICATION_RE = re.compile(r"\b(?:S\.O\.|G\.S\.R\.|Notification\s+(?:No\.?|Number)?)\s*[:\-]?\s*[A-Z0-9/.-]+(?:\([A-Z]\))?", re.IGNORECASE)
ORG_SUFFIX_RE = re.compile(
    r"\b[A-Z][A-Za-z&.'-]*(?:\s+[A-Z][A-Za-z&.'-]*){0,8}\s+"
    r"(?:Court|Tribunal|Board|Department|Ministry|Commission|Authority|Council|University|Government|Bank|Ltd\.?|Limited)\b"
)


def annotate_chunks(chunks_path: Path, output_path: Path) -> list[dict]:
    docs: list[dict] = []
    nlp = _load_spacy()
    gazetteer = _load_gazetteer()
    for line in chunks_path.read_text(encoding="utf-8").split("\n"):
        if not line.strip():
            continue
        chunk = json.loads(line)
        entities = extract_entities(chunk["text"], nlp=nlp, gazetteer=gazetteer)
        docs.append({"chunk_id": chunk["chunk_id"], "entities": entities})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for doc in docs:
            fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
    return docs


def extract_entities(text: str, nlp=None, gazetteer: dict[str, list[str]] | None = None) -> list[dict]:
    candidates: list[dict] = []
    for label, pattern in [
        ("SECTION_REF", ORDER_RULE_RE),
        ("SECTION_REF", CLAUSE_RE),
        ("SECTION_REF", SUB_SECTION_RE),
        ("SECTION_REF", SECTION_RE),
        ("DATE", DATE_RE),
        ("MONEY", MONEY_RE),
        ("ACT_NAME", ACT_RE),
        ("NOTIFICATION", NOTIFICATION_RE),
        ("ORG", ORG_SUFFIX_RE),
    ]:
        for match in pattern.finditer(text):
            candidates.append({"label": label, "text": match.group().strip(), "start": match.start(), "end": match.end()})

    if nlp is not None:
        doc = nlp(text[:100000])
        for ent in doc.ents:
            if ent.label_ == "ORG":
                candidates.append({"label": "ORG", "text": ent.text.strip(), "start": ent.start_char, "end": ent.end_char})

    for label, terms in (gazetteer or _load_gazetteer()).items():
        for term in terms:
            for match in re.finditer(re.escape(term), text, flags=re.IGNORECASE):
                candidates.append({"label": label, "text": match.group(), "start": match.start(), "end": match.end()})

    return _dedupe_entities(candidates)


def _load_spacy():
    try:
        import spacy

        try:
            return spacy.load("en_core_web_sm")
        except OSError:
            return spacy.blank("en")
    except Exception:
        return None


def _load_gazetteer() -> dict[str, list[str]]:
    path = DATA_DIR / "legal_gazetteer.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _dedupe_entities(entities: list[dict]) -> list[dict]:
    cleaned = [ent for ent in entities if ent["text"] and len(ent["text"]) > 1]
    cleaned.sort(key=lambda ent: (ent["start"], -(ent["end"] - ent["start"])))
    selected: list[dict] = []
    for ent in cleaned:
        overlap = any(not (ent["end"] <= old["start"] or ent["start"] >= old["end"]) and ent["label"] == old["label"] for old in selected)
        if not overlap:
            selected.append(ent)
    return selected
