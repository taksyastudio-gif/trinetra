import React from "react";
import { ConnectionStatus, CameraOperationalState, PerceptionHealthTelemetry } from "../types/api";

interface StatusIndicatorProps {
  connectionStatus: ConnectionStatus;
  cameraState: CameraOperationalState;
  errorMessage: string | null;
  framesCaptured: number;
  perceptionHealth?: PerceptionHealthTelemetry | null;
  wearableActive?: boolean;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  connectionStatus,
  cameraState,
  errorMessage,
  framesCaptured,
  perceptionHealth,
  wearableActive = false,
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
              {connectionStatus === "starting" && "Starting vision engine (initializing models)..."}
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
              className={`status-dot ${cameraState === "reconnecting" ? "status-dot-starting" : `status-dot-${cameraState}`}`}
              aria-hidden="true"
            />
            <span className="status-text">
              {cameraState === "active" && `Active (${framesCaptured} frames captured)`}
              {cameraState === "starting" && "Initializing camera hardware..."}
              {cameraState === "reconnecting" && "Reconnecting hardware (attempting recovery)..."}
              {cameraState === "stopping" && "Releasing camera..."}
              {cameraState === "stopped" && "Stopped (Privacy protected)"}
              {cameraState === "error" && "Camera Error"}
            </span>
          </div>
        </div>

        {/* Perception Health Quality Gatekeeper Card */}
        <div className="status-card" role="status" aria-live="polite">
          <span className="status-label">Perception Health:</span>
          <div className="status-value-wrapper">
            <span
              className={`status-dot status-dot-${
                cameraState !== "active"
                  ? "stopped"
                  : !perceptionHealth || perceptionHealth.state === "VALID_OBSERVATION"
                  ? "active"
                  : perceptionHealth.state === "TEMPORARILY_DEGRADED" || perceptionHealth.state === "RECOVERY_TRANSITION"
                  ? "starting"
                  : "error"
              }`}
              aria-hidden="true"
            />
            <span className="status-text">
              {cameraState !== "active" && "Standby (Camera inactive)"}
              {cameraState === "active" && (!perceptionHealth || perceptionHealth.state === "VALID_OBSERVATION") && "Optimal (Clear view)"}
              {cameraState === "active" && perceptionHealth?.state === "TEMPORARILY_DEGRADED" && `Degraded (${perceptionHealth.reasons.join(", ") || "Lighting/blur"})`}
              {cameraState === "active" && perceptionHealth?.state === "RECOVERY_TRANSITION" && "Recovering view..."}
              {cameraState === "active" && (perceptionHealth?.state === "SENSOR_UNAVAILABLE" || perceptionHealth?.state === "STALE_TERMINATED") && `Unavailable (${perceptionHealth.reasons.join(", ") || "Obstructed"})`}
            </span>
          </div>
          <span className="status-disclaimer" style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "2px" }}>
            Diagnostics only — not safety certified
          </span>
        </div>

        {/* Wearable Hardware Rig Card */}
        <div className="status-card" role="status" aria-live="polite">
          <span className="status-label">Wearable Rig:</span>
          <div className="status-value-wrapper">
            <span
              className={`status-dot ${wearableActive ? "status-dot-active" : "status-dot-stopped"}`}
              aria-hidden="true"
            />
            <span className="status-text">
              {wearableActive ? "Smart Glasses Connected" : "Ready (ESP32-CAM / Cane / Web)"}
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
