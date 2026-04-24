from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ner.recognize import extract_entities


def load_annotations(path: Path) -> set[tuple[str, str, int, int]]:
    items: set[tuple[str, str, int, int]] = set()
    if not path.exists():
        return items
    for row_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        row_id = row.get("chunk_id", f"row:{row_no}")
        for ent in row.get("entities", []):
            items.add((row_id, ent["label"], int(ent["start"]), int(ent["end"])))
    return items


def evaluate(gold_path: Path, pred_path: Path) -> dict:
    gold = load_annotations(gold_path)
    pred = load_annotations(pred_path)
    true_positive = len(gold & pred)
    precision = true_positive / len(pred) if pred else 0.0
    recall = true_positive / len(gold) if gold else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {
        "gold_entities": len(gold),
        "predicted_entities": len(pred),
        "true_positive": true_positive,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def evaluate_gold_text_dataset(gold_path: Path) -> dict:
    gold_items: set[tuple[str, str, int, int]] = set()
    pred_items: set[tuple[str, str, int, int]] = set()
    if not gold_path.exists():
        return _score(gold_items, pred_items)

    for row_no, line in enumerate(gold_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        row_id = row.get("chunk_id", f"row:{row_no}")
        for ent in row.get("entities", []):
            gold_items.add((row_id, ent["label"], int(ent["start"]), int(ent["end"])))
        if "text" in row:
            for ent in extract_entities(row["text"]):
                pred_items.add((row_id, ent["label"], int(ent["start"]), int(ent["end"])))

    return _score(gold_items, pred_items)


def _score(gold: set[tuple[str, str, int, int]], pred: set[tuple[str, str, int, int]]) -> dict:
    true_positive = len(gold & pred)
    precision = true_positive / len(pred) if pred else 0.0
    recall = true_positive / len(gold) if gold else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {
        "gold_entities": len(gold),
        "predicted_entities": len(pred),
        "true_positive": true_positive,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default="data/gold_ner.jsonl")
    parser.add_argument("--pred", default="ner/annotations.jsonl")
    parser.add_argument("--gold-text-mode", action="store_true", help="Run NER directly on gold rows that contain text.")
    args = parser.parse_args()
    metrics = evaluate_gold_text_dataset(Path(args.gold)) if args.gold_text_mode else evaluate(Path(args.gold), Path(args.pred))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
