import json

from scripts.evaluate_ner import evaluate


def test_evaluate_exact_span_metrics(tmp_path):
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    row = {"chunk_id": "a:0001", "entities": [{"label": "DATE", "text": "01-01-2023", "start": 0, "end": 10}]}
    gold.write_text(json.dumps(row) + "\n", encoding="utf-8")
    pred.write_text(json.dumps(row) + "\n", encoding="utf-8")

    metrics = evaluate(gold, pred)

    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1"] == 1.0
