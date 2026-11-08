"""Evaluation-report gate for independently held-out model predictions.

Input is JSONL with `label` and `prediction` fields. This never reads training
data and therefore cannot accidentally report training accuracy as deployment
performance.
"""
import argparse, json
from collections import Counter
from pathlib import Path

def main():
    p = argparse.ArgumentParser(); p.add_argument("--predictions", type=Path, required=True); p.add_argument("--output", type=Path, required=True); args = p.parse_args()
    rows = [json.loads(x) for x in args.predictions.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not rows: raise SystemExit("No held-out predictions supplied")
    labels = sorted({str(r["label"]) for r in rows}); matrix = {label: Counter() for label in labels}
    for r in rows: matrix[str(r["label"])][str(r["prediction"])] += 1
    report = {"test_samples": len(rows), "accuracy": sum(r["label"] == r["prediction"] for r in rows) / len(rows),
      "confusion_matrix": {key: dict(value) for key, value in matrix.items()}, "note": "Independent held-out evaluation only."}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2), encoding="utf-8"); print(json.dumps(report, indent=2))

if __name__ == "__main__": main()
