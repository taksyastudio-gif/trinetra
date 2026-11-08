import React from "react";
import { CameraOperationalState, DetectionItem, GroundHazardInfo } from "../types/api";

interface CameraPreviewProps {
  cameraState: CameraOperationalState;
  frameUrl: string | null;
  fps: number;
  detections?: DetectionItem[];
  groundHazard?: GroundHazardInfo | null;
  autoCurrency?: {
    status: string;
    denomination?: number | null;
    confidence: number;
    message: string;
    spoken_text?: string;
  } | null;
  signGesture?: {
    detected: boolean;
    gesture_type: string;
    confidence: number;
    message: string;
    symbol: string;
    bounding_box?: number[] | null;
  } | null;
  showSectors?: boolean;
  onDoubleTap?: () => void;
}

const NEPALI_CLASS_LABELS: Record<string, string> = {
  person: "मान्छे (Person)",
  chair: "कुर्सी (Chair)",
  couch: "सोफा (Sofa)",
  bed: "खाट (Bed)",
  laptop: "ल्यापटप (Laptop)",
  "cell phone": "मोबाइल (Phone)",
  bottle: "बोतल (Bottle)",
  cup: "कप (Cup)",
  book: "किताब (Book)",
  backpack: "झोला (Backpack)",
  tv: "टिभी (TV)",
  dog: "कुकुर (Dog)",
  cat: "बिरालो (Cat)",
  cow: "गाई (Cow)",
  motorcycle: "मोटरसाइकल (Motorcycle)",
  bicycle: "साइकल (Bicycle)",
  car: "गाडी (Car)",
  bus: "बस (Bus)",
  truck: "ट्रक (Truck)",
  stairs: "भर्‍याङ (Stairs)",
  "traffic light": "ट्राफिक बत्ती (Traffic Light)",
  pothole: "खाल्डो (Pothole)",
  open_manhole: "खुल्ला ढल (Manhole)",
};

export const CameraPreview: React.FC<CameraPreviewProps> = ({
  cameraState,
  frameUrl,
  fps,
  detections = [],
  groundHazard = null,
  autoCurrency = null,
  signGesture = null,
  showSectors = true,
  onDoubleTap,
}) => {
  const isStreaming = cameraState === "active" && frameUrl !== null;

  const getLabel = (className: string, conf: number) => {
    const localized = NEPALI_CLASS_LABELS[className.toLowerCase()] || className.toUpperCase();
    return `${localized} ${Math.round(conf * 100)}%`;
  };

  return (
    <div
      className="camera-viewport-container"
      role="region"
      aria-label="Camera Video Viewport"
    >
      <div className="camera-viewport-header">
        <span className="viewport-title" id="preview-heading">
          Live Camera Stream {isStreaming && <small style={{ fontWeight: 400, opacity: 0.8, fontSize: "0.8rem", marginLeft: "8px" }}>(Double-tap anywhere to Read / Describe)</small>}
        </span>
        {isStreaming && (
          <span
            className="viewport-fps-tag"
            aria-label={`Current ingestion rate: ${fps} frames per second`}
          >
            ● LIVE ({fps} FPS)
          </span>
        )}
      </div>

      <div
        className="camera-viewport-frame"
        aria-labelledby="preview-heading"
        onDoubleClick={onDoubleTap}
        style={{ cursor: isStreaming ? "pointer" : "default" }}
        title={isStreaming ? "Double-tap to describe scene or read text" : ""}
      >
        {isStreaming ? (
          <>
            <img
              src={frameUrl}
              alt="Live camera feed showing immediate surroundings"
              className="camera-video-feed"
            />
            {/* Spatial overlay with sectors and detections */}
            <div className="spatial-overlay" aria-hidden="true">
              {showSectors && (
                <div className="sector-lines">
                  <div className="sector-column">
                    <span className="sector-badge">Left</span>
                  </div>
                  <div className="sector-column">
                    <span className="sector-badge">Center</span>
                  </div>
                  <div className="sector-column">
                    <span className="sector-badge">Right</span>
                  </div>
                </div>
              )}
              {detections.map((det, idx) => {
                const box = det.box;
                const left = `${box.x_min * 100}%`;
                const top = `${box.y_min * 100}%`;
                const width = `${Math.max(0, box.x_max - box.x_min) * 100}%`;
                const height = `${Math.max(0, box.y_max - box.y_min) * 100}%`;

                return (
                  <div
                    key={`${det.class_name}-${idx}`}
                    className={`detection-bounding-box sector-${det.sector}`}
                    style={{ left, top, width, height }}
                  >
                    <span className="detection-box-label">
                      {getLabel(det.class_name, det.confidence)}
                    </span>
                  </div>
                );
              })}
              {groundHazard && groundHazard.detected && (
                <div
                  className="ground-hazard-box"
                  style={{
                    position: "absolute",
                    left: groundHazard.bounding_box ? `${groundHazard.bounding_box[1] * 100}%` : "20%",
                    top: groundHazard.bounding_box ? `${groundHazard.bounding_box[0] * 100}%` : "60%",
                    width: groundHazard.bounding_box ? `${(groundHazard.bounding_box[3] - groundHazard.bounding_box[1]) * 100}%` : "60%",
                    height: groundHazard.bounding_box ? `${(groundHazard.bounding_box[2] - groundHazard.bounding_box[0]) * 100}%` : "38%",
                    border: "3px dashed #ef4444",
                    backgroundColor: "rgba(239, 68, 68, 0.25)",
                    borderRadius: "8px",
                    pointerEvents: "none",
                    boxShadow: "0 0 15px rgba(239, 68, 68, 0.6)",
                    zIndex: 20,
                  }}
                >
                  <span
                    style={{
                      position: "absolute",
                      bottom: "-28px",
                      left: "50%",
                      transform: "translateX(-50%)",
                      backgroundColor: "#ef4444",
                      color: "#ffffff",
                      fontSize: "0.8rem",
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: "4px",
                      whiteSpace: "nowrap",
                    }}
                  >
                    ⚠️ {groundHazard.message || "खतरा (Hazard)"}
                  </span>
                </div>
              )}
            </div>
            {groundHazard && groundHazard.detected && (
              <div
                style={{
                  position: "absolute",
                  top: "12px",
                  left: "12px",
                  right: "12px",
                  backgroundColor: "rgba(185, 28, 28, 0.95)",
                  color: "#ffffff",
                  padding: "10px 14px",
                  borderRadius: "8px",
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  fontWeight: 600,
                  fontSize: "0.95rem",
                  boxShadow: "0 4px 14px rgba(0, 0, 0, 0.4)",
                  zIndex: 30,
                  animation: "pulse 1.5s infinite",
                }}
                role="alert"
              >
                <span style={{ fontSize: "1.4rem" }}>⚠️</span>
                <span>{groundHazard.message}</span>
              </div>
            )}
            {autoCurrency && autoCurrency.status === "identified" && (
              <div
                style={{
                  position: "absolute",
                  bottom: "16px",
                  right: "16px",
                  backgroundColor: "rgba(16, 185, 129, 0.95)",
                  color: "#ffffff",
                  padding: "8px 16px",
                  borderRadius: "24px",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  fontWeight: 700,
                  fontSize: "1.05rem",
                  boxShadow: "0 4px 15px rgba(16, 185, 129, 0.5)",
                  zIndex: 25,
                  border: "2px solid #ffffff",
                }}
              >
                <span>💵</span>
                <span>{autoCurrency.message}</span>
              </div>
            )}
            {signGesture && signGesture.detected && (
              <div
                style={{
                  position: "absolute",
                  bottom: "16px",
                  left: "16px",
                  backgroundColor: "rgba(168, 85, 247, 0.95)",
                  color: "#ffffff",
                  padding: "8px 16px",
                  borderRadius: "24px",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  fontWeight: 700,
                  fontSize: "1.05rem",
                  boxShadow: "0 4px 15px rgba(168, 85, 247, 0.5)",
                  zIndex: 25,
                  border: "2px solid #ffffff",
                }}
              >
                <span style={{ fontSize: "1.3rem" }}>{signGesture.symbol}</span>
                <span>{signGesture.message}</span>
              </div>
            )}
          </>
        ) : (
          <div className="camera-inactive-placeholder" role="status">
            <div className="placeholder-icon" aria-hidden="true">
              📷
            </div>
            <p className="placeholder-title">
              {cameraState === "starting"
                ? "Connecting to camera hardware..."
                : cameraState === "stopping"
                ? "Releasing camera hardware..."
                : cameraState === "reconnecting"
                ? "Camera disconnected. Reconnecting automatically..."
                : cameraState === "error"
                ? "Camera connection error."
                : "Camera is currently inactive."}
            </p>
            <p className="placeholder-hint">
              {cameraState === "error"
                ? "Reconnection exhausted. Please verify camera connection and click Start Camera to retry."
                : cameraState === "reconnecting"
                ? "Attempting bounded reconnection with exponential backoff..."
                : "Press the Start Camera button below to begin video ingestion."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
