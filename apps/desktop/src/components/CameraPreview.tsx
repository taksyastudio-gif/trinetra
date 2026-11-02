import React from "react";
import { CameraOperationalState, DetectionItem } from "../types/api";

interface CameraPreviewProps {
  cameraState: CameraOperationalState;
  frameUrl: string | null;
  fps: number;
  detections?: DetectionItem[];
  showSectors?: boolean;
}

export const CameraPreview: React.FC<CameraPreviewProps> = ({
  cameraState,
  frameUrl,
  fps,
  detections = [],
  showSectors = true,
}) => {
  const isStreaming = cameraState === "active" && frameUrl !== null;

  return (
    <div
      className="camera-viewport-container"
      role="region"
      aria-label="Camera Video Viewport"
    >
      <div className="camera-viewport-header">
        <span className="viewport-title" id="preview-heading">
          Live Camera Stream
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

      <div className="camera-viewport-frame" aria-labelledby="preview-heading">
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
                      {det.class_name.toUpperCase()} {Math.round(det.confidence * 100)}%
                    </span>
                  </div>
                );
              })}
            </div>
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
