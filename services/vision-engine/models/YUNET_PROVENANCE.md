# OpenCV YuNet Face Detection Model Provenance & License

## 1. Model Overview
- **Model Name:** YuNet (`face_detection_yunet_2023mar.onnx`)
- **Author/Upstream:** Shiqi Yu / OpenCV Zoo (OpenCV Foundation)
- **Upstream Repository:** https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
- **Direct Source URL:** https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
- **Architecture:** Light-weight convolution-based face detector with 5 facial landmark regression
- **File Size:** 232,589 bytes (227.1 KB)
- **SHA-256 Checksum:** `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`

## 2. License Terms
- **License:** Apache License 2.0 / 3-Clause BSD License
- **Copyright:** (c) OpenCV Foundation and Shiqi Yu (libfacedetection)
- **Commercial Use:** Permitted under Apache 2.0 / BSD-3.
- **Modification & Distribution:** Permitted with attribution notice.

## 3. Specifications for Trinetra
- **Input Format:** BGR `uint8` image or `float32`, dynamic input resolution (default: camera resolution e.g. 640x480 or 320x320)
- **Output:** Bounding box `[x, y, w, h]`, 5 facial landmarks (right eye, left eye, nose tip, right mouth corner, left mouth corner), and face detection confidence score.
- **Execution Engine:** `cv2.FaceDetectorYN` (built directly into OpenCV DNN with zero external Python dependencies).
