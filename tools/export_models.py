"""Version and checksum a manually approved ONNX inference artifact; never replaces production."""
import argparse, hashlib, json, shutil
from pathlib import Path

def main():
    p = argparse.ArgumentParser(); p.add_argument("--onnx", type=Path, required=True); p.add_argument("--version", required=True); args = p.parse_args()
    if not args.onnx.is_file() or args.onnx.suffix.lower() != ".onnx": raise SystemExit("A validated ONNX file is required")
    dest = Path("services/vision-engine/models/currency") / args.version; dest.mkdir(parents=True, exist_ok=False)
    model = dest / "currency_classifier.onnx"; shutil.copy2(args.onnx, model)
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    (dest / "metadata.json").write_text(json.dumps({"version": args.version, "sha256": digest,
      "promotion": "manual: set TRINETRA_CURRENCY_MODEL only after independent evaluation"}, indent=2), encoding="utf-8")
    print(dest)

if __name__ == "__main__": main()
