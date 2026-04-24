from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chunker.chunk import create_chunks
from config import CHUNKS_DIR, DATA_DIR, DEFAULT_MAX_PAGES, PROJECT_ROOT, ensure_output_dirs
from crawler.crawl import PoliteCrawler, load_seed_urls
from ner.recognize import annotate_chunks
from parsers.normalize import normalize_from_crawl_index
from scripts.evaluate_ner import evaluate, evaluate_gold_text_dataset
from scripts.report import write_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the mini legal data pipeline.")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--skip-crawl", action="store_true", help="Reuse an existing crawl_index.jsonl.")
    args = parser.parse_args()

    ensure_output_dirs()
    seed_path = DATA_DIR / "seed_urls.json"
    crawl_index = PROJECT_ROOT / "crawl_index.jsonl"
    normalized_index = PROJECT_ROOT / "normalized_index.jsonl"
    chunks_path = CHUNKS_DIR / "chunks.jsonl"
    annotations_path = PROJECT_ROOT / "ner" / "annotations.jsonl"
    gold_path = DATA_DIR / "gold_ner.jsonl"

    if not args.skip_crawl:
        crawler = PoliteCrawler(delay_seconds=args.delay, max_pages=args.max_pages)
        crawl_records = crawler.crawl(load_seed_urls(seed_path), crawl_index)
    else:
        crawl_records = _read_jsonl(crawl_index)

    # Register any locally bundled PDFs under data/sample_docs/ as crawl entries.
    # This exercises the PDF parsing path without depending on flaky remote PDF URLs.
    crawl_records = _register_local_docs(DATA_DIR / "sample_docs", crawl_index, crawl_records)

    normalized_records = normalize_from_crawl_index(crawl_index, normalized_index)
    chunks = create_chunks(normalized_index, chunks_path)
    annotations = annotate_chunks(chunks_path, annotations_path)
    metrics = evaluate_gold_text_dataset(gold_path) if _gold_has_text_rows(gold_path) else evaluate(gold_path, annotations_path)

    avg_tokens = round(sum(chunk["token_estimate"] for chunk in chunks) / len(chunks), 2) if chunks else 0
    summary = {
        "Pages crawled": len([row for row in crawl_records if row.get("status") in (200, 404) and row.get("path_to_raw")]),
        "Documents normalized": len(normalized_records),
        "Chunks created": len(chunks),
        "Avg tokens/chunk": avg_tokens,
        "NER annotations": sum(len(row["entities"]) for row in annotations),
        "NER precision": round(metrics["precision"], 4),
        "NER recall": round(metrics["recall"], 4),
        "NER F1-score": round(metrics["f1"], 4),
    }
    write_report(PROJECT_ROOT / "reports" / "metrics.html", summary)

    for key, value in summary.items():
        print(f"{key}: {value}")


def _register_local_docs(local_dir: Path, crawl_index: Path, existing: list[dict]) -> list[dict]:
    """Copy any PDFs/HTML in `local_dir` into raw/ and append crawl_index rows."""
    import json
    import shutil

    from config import RAW_DIR, url_hash, utc_now_iso

    if not local_dir.exists():
        return existing

    known = {row.get("url") for row in existing}
    new_rows: list[dict] = []
    for path in sorted(local_dir.iterdir()):
        if path.suffix.lower() not in {".pdf", ".html", ".htm"}:
            continue
        url = f"local://{path.name}"
        if url in known:
            continue
        digest = url_hash(url)
        dest = RAW_DIR / f"{digest}{path.suffix.lower()}"
        shutil.copy2(path, dest)
        new_rows.append(
            {
                "url": url,
                "status": 200,
                "content_type": "application/pdf" if path.suffix.lower() == ".pdf" else "text/html",
                "used_js": False,
                "timestamp": utc_now_iso(),
                "path_to_raw": str(dest.relative_to(Path.cwd())),
            }
        )

    if new_rows:
        with crawl_index.open("a", encoding="utf-8") as fh:
            for row in new_rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return existing + new_rows


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    import json

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _gold_has_text_rows(path: Path) -> bool:
    if not path.exists():
        return False
    import json

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            return "text" in json.loads(line)
    return False


if __name__ == "__main__":
    main()
