"""Create deterministic, session-isolated dataset splits from verified metadata."""
import argparse, hashlib, json
from pathlib import Path

def bucket(session: str) -> str:
    value = int(hashlib.sha256(session.encode()).hexdigest()[:8], 16) % 100
    return "test" if value < 15 else "validation" if value < 30 else "train"

def main():
    p = argparse.ArgumentParser(); p.add_argument("dataset", choices=["currency", "ocr"]); args = p.parse_args()
    root = Path("datasets") / args.dataset; source = root / "metadata" / "samples.jsonl"
    rows = [json.loads(x) for x in source.read_text(encoding="utf-8").splitlines() if x.strip()]
    if any(not r.get("verified_by_human") for r in rows): raise SystemExit("Refusing unverified labels")
    splits = {"train": [], "validation": [], "test": []}
    for row in rows: splits[bucket(str(row.get("session", "unknown")))].append(row)
    output = root / "splits"; output.mkdir(parents=True, exist_ok=True)
    for name, records in splits.items(): (output / f"{name}.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print({name: len(records) for name, records in splits.items()})

if __name__ == "__main__": main()
