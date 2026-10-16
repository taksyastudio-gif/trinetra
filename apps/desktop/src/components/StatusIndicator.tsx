import React from "react";
import { ConnectionStatus, CameraOperationalState } from "../types/api";

interface StatusIndicatorProps {
  connectionStatus: ConnectionStatus;
  cameraState: CameraOperationalState;
  errorMessage: string | null;
  framesCaptured: number;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  connectionStatus,
  cameraState,
  errorMessage,
  framesCaptured,
}) => {
  return (
    <section
      className="status-section"
      aria-label="System Operational Status"
      role="region"
    >
      <div className="status-grid">
        {/* Vision Engine Connection Card */}
        <div className="status-card" role="status" aria-live="polite">
          <span className="status-label">Vision Engine Service:</span>
          <div className="status-value-wrapper">
            <span
              className={`status-dot status-dot-${connectionStatus}`}
              aria-hidden="true"
            />
            <span className="status-text">
              {connectionStatus === "connected" && "Online (127.0.0.1:8000)"}
              {connectionStatus === "checking" && "Checking connection..."}
              {connectionStatus === "disconnected" && "Offline — Please start Python service"}
              {connectionStatus === "error" && "Connection Error"}
            </span>
          </div>
        </div>

        {/* Camera Hardware State Card */}
        <div className="status-card" role="status" aria-live="polite">
          <span className="status-label">Webcam Hardware:</span>
          <div className="status-value-wrapper">
            <span
              className={`status-dot status-dot-${cameraState}`}
              aria-hidden="true"
            />
            <span className="status-text">
              {cameraState === "active" && `Active (${framesCaptured} frames captured)`}
              {cameraState === "starting" && "Initializing camera hardware..."}
              {cameraState === "stopping" && "Releasing camera..."}
              {cameraState === "stopped" && "Stopped (Privacy protected)"}
              {cameraState === "error" && "Camera Error"}
            </span>
          </div>
        </div>
      </div>

      {/* Accessible Error Announcement Banner */}
      {errorMessage && (
        <div
          className="error-alert"
          role="alert"
          aria-live="assertive"
          aria-atomic="true"
        >
          <strong className="error-prefix">Alert: </strong>
          <span className="error-message">{errorMessage}</span>
        </div>
      )}
    </section>
  );
};
