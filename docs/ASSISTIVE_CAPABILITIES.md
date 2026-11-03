# Assistive capability milestone

The on-demand capabilities use the already active authoritative camera. They never start a camera, persist routine frames, or create a second stream. All endpoints are protected by the existing local session token when it is enabled.

## API

- `POST /api/scene/query` with `{"question":"के छ?", "speak":true}` returns a grounded Nepali summary from the local detector. It does not claim a route is safe.
- `POST /api/currency/identify` and `POST /api/ocr/read` capture one current frame. Currency is deliberately unavailable until a validated local ONNX classifier is deployed with `TRINETRA_CURRENCY_MODEL`; it never represents authenticity verification.
- `POST /api/faces/recognize` is local-only and deliberately makes no identity assertion until a verified local embedding model is configured. `GET /api/faces` and `DELETE /api/faces/{id}` support registry inspection/deletion without exposing templates.
- `GET /api/capabilities/status` reports optional model availability.

## ESP32-CAM

Enter an HTTP MJPEG URL such as `http://192.168.4.1/stream` in the existing Network Stream control. The new `MJPEGStreamCameraAdapter` validates JPEG frames, caps buffered data, reconnects with bounded attempts, and returns normal `FramePacket` objects to the established pipeline. Use an isolated local Wi-Fi network; do not expose the ESP32 camera to the public Internet.

## Dataset workflow

```powershell
python tools/collect_currency.py import --label 100 --source C:\samples\npr100 --session note-001
python tools/validate_dataset.py currency
python tools/prepare_datasets.py currency
python tools/train_currency.py
python tools/evaluate_models.py --predictions C:\results\held_out.jsonl --output C:\results\currency_metrics.json
python tools/export_models.py --onnx C:\results\currency.onnx --version 2026-11-03
python tools/collect_ocr.py --csv C:\samples\nepali_labels.csv
python tools/validate_dataset.py ocr
python tools/prepare_datasets.py ocr
```

Labels are explicitly human-verified. Splits are assigned by capture session, preventing the same physical note/capture session from leaking across train, validation, and test. The training gate does not train or promote a model automatically; record per-denomination precision/recall, F1, confusion matrix, latency, and independent test size before deployment.

Face enrolment requires informed consent. Keep face templates local, never send them to cloud providers, and delete them when consent is withdrawn. No cloud scene provider is enabled in this milestone: this avoids unreviewed transmission of camera frames.
