from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = PROJECT_ROOT / "raw"
NORMALIZED_DIR = PROJECT_ROOT / "normalized"
CHUNKS_DIR = PROJECT_ROOT / "chunks"
NER_DIR = PROJECT_ROOT / "ner"
REPORTS_DIR = PROJECT_ROOT / "reports"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 "
    "BharatLawPipeline/1.0 (+take-home-project; polite)"
)
MAX_DEPTH = 3
DEFAULT_MAX_PAGES = 8
REQUEST_TIMEOUT = 25


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_output_dirs() -> None:
    for path in (DATA_DIR, RAW_DIR, NORMALIZED_DIR, CHUNKS_DIR, NER_DIR, REPORTS_DIR):
        path.mkdir(parents=True, exist_ok=True)
