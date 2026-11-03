"""Import human-annotated Nepali/Devanagari OCR samples without auto-labelling."""
import argparse, csv, hashlib, json, shutil, time
from pathlib import Path

def main():
    p = argparse.ArgumentParser(); p.add_argument("--csv", type=Path, required=True, help="CSV columns: image,text,session")
    args = p.parse_args(); root = Path("datasets/ocr"); raw = root / "raw"; meta = root / "metadata"
    raw.mkdir(parents=True, exist_ok=True); meta.mkdir(parents=True, exist_ok=True)
    with args.csv.open(encoding="utf-8-sig", newline="") as f, (meta / "samples.jsonl").open("a", encoding="utf-8") as out:
        for row in csv.DictReader(f):
            src, text = Path(row["image"]), row["text"].strip()
            if not src.is_file() or not text: print("skipped", src); continue
            digest = hashlib.sha256(src.read_bytes()).hexdigest(); dest = raw / f"{digest[:16]}{src.suffix.lower()}"
            if not dest.exists(): shutil.copy2(src, dest)
            out.write(json.dumps({"path": str(dest.relative_to(root)).replace("\\", "/"), "text": text,
              "session": row.get("session", "unknown"), "sha256": digest, "verified_by_human": True,
              "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, ensure_ascii=False) + "\n")

if __name__ == "__main__": main()
