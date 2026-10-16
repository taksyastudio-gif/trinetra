import React from "react";
import { CameraOperationalState } from "../types/api";

interface CameraPreviewProps {
  cameraState: CameraOperationalState;
  frameUrl: string | null;
  fps: number;
}

export const CameraPreview: React.FC<CameraPreviewProps> = ({
  cameraState,
  frameUrl,
  fps,
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
          <img
            src={frameUrl}
            alt="Live camera feed showing immediate surroundings"
            className="camera-video-feed"
          />
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
                : "Camera is currently inactive."}
            </p>
            <p className="placeholder-hint">
              Press the <strong>Start Camera</strong> button below to begin video ingestion.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
