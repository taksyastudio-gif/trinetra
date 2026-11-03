"""Training gate. Keeps production models untouched and requires an isolated test split."""
import argparse, json
from pathlib import Path

def main():
    p = argparse.ArgumentParser(); p.add_argument("--config", type=Path, default=Path("datasets/currency/training_config.json")); args = p.parse_args()
    required = [Path("datasets/currency/splits") / f"{n}.json" for n in ("train", "validation", "test")]
    missing = [str(x) for x in required if not x.is_file()]
    if missing: raise SystemExit("Run prepare_datasets.py first; missing: " + ", ".join(missing))
    counts = {p.stem: len(json.loads(p.read_text(encoding="utf-8"))) for p in required}
    if not counts["train"] or not counts["validation"] or not counts["test"]: raise SystemExit("All isolated splits need samples")
    args.config.parent.mkdir(parents=True, exist_ok=True)
    args.config.write_text(json.dumps({"architecture": "mobilenetv3-small", "input_size": 224, "epochs": 30,
      "seed": 42, "splits": counts, "export": "versioned ONNX only; never overwrite production model"}, indent=2), encoding="utf-8")
    print("Training manifest written. Install the selected trainer separately and record evaluation before deployment.")

if __name__ == "__main__": main()
