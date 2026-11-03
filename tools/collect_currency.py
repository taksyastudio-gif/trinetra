"""Human-verified Nepalese banknote dataset importer/camera collector.

Examples (PowerShell):
  python tools/collect_currency.py import --label 100 --source C:\samples\100 --session note-a
  python tools/collect_currency.py camera --label 100 --session note-a
"""
import argparse, hashlib, json, shutil, time
from pathlib import Path

VALID = {5, 10, 20, 50, 100, 500, 1000}

def quality(path: Path):
    import cv2
    image = cv2.imread(str(path))
    if image is None: return {"valid": False, "reason": "unreadable"}
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return {"valid": True, "width": int(image.shape[1]), "height": int(image.shape[0]),
            "blur_variance": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2)}

def add_file(source: Path, label: int, root: Path, session: str):
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    meta_dir = root / "metadata"; raw_dir = root / "raw" / str(label)
    meta_dir.mkdir(parents=True, exist_ok=True); raw_dir.mkdir(parents=True, exist_ok=True)
    index_path = meta_dir / "samples.jsonl"
    known = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    if digest in known: return "duplicate"
    ext = source.suffix.lower() if source.suffix.lower() in {".jpg", ".jpeg", ".png"} else ".jpg"
    dest = raw_dir / f"{digest[:16]}{ext}"
    shutil.copy2(source, dest)
    record = {"path": str(dest.relative_to(root)).replace("\\", "/"), "label": label, "sha256": digest,
              "session": session, "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "quality": quality(dest), "verified_by_human": True, "source_type": "local"}
    with index_path.open("a", encoding="utf-8") as out: out.write(json.dumps(record) + "\n")
    return "added"

def main():
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    for name in ("import", "camera"):
        cmd = sub.add_parser(name); cmd.add_argument("--label", type=int, required=True); cmd.add_argument("--session", required=True)
        if name == "import": cmd.add_argument("--source", type=Path, required=True)
        else: cmd.add_argument("--camera", type=int, default=0); cmd.add_argument("--count", type=int, default=10)
    args = parser.parse_args()
    if args.label not in VALID: parser.error("label must be a supported NPR denomination")
    root = Path("datasets/currency")
    if args.command == "import":
        files = [p for p in args.source.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
        print({"added": sum(add_file(p, args.label, root, args.session) == "added" for p in files), "seen": len(files)})
        return
    import cv2, tempfile
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened(): raise SystemExit("Camera could not be opened")
    print("Press SPACE to save a human-confirmed sample; ESC to finish.")
    saved = 0
    with tempfile.TemporaryDirectory() as temp:
        while saved < args.count:
            ok, frame = cap.read()
            if not ok: break
            cv2.imshow("Trinetra currency collection", frame); key = cv2.waitKey(1) & 0xff
            if key == 27: break
            if key == 32:
                f = Path(temp) / f"sample-{saved}.jpg"; cv2.imwrite(str(f), frame)
                if add_file(f, args.label, root, args.session) == "added": saved += 1
    cap.release(); cv2.destroyAllWindows(); print({"added": saved})

if __name__ == "__main__": main()
