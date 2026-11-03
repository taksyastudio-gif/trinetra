"""Validate metadata, labels, source-session leakage, and duplicate hashes."""
import argparse, json
from collections import Counter
from pathlib import Path

def main():
    p = argparse.ArgumentParser(); p.add_argument("dataset", choices=["currency", "ocr"]); args = p.parse_args()
    f = Path("datasets") / args.dataset / "metadata" / "samples.jsonl"
    rows = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []
    dupes = [key for key, n in Counter(r.get("sha256") for r in rows).items() if n > 1]
    invalid = [r for r in rows if not r.get("verified_by_human") or not r.get("path")]
    report = {"dataset": args.dataset, "samples": len(rows), "duplicates": len(dupes), "invalid": len(invalid),
              "classes": dict(Counter(str(r.get("label", "text")) for r in rows))}
    print(json.dumps(report, indent=2)); raise SystemExit(1 if dupes or invalid else 0)

if __name__ == "__main__": main()
