import React from "react";
import { DetectionItem, SupportedLanguage } from "../types/api";

interface DetectionPanelProps {
  detectionActive: boolean;
  modelName: string;
  isReady: boolean;
  modelError?: string | null;
  detections: DetectionItem[];
  inferenceTimeMs: number;
  e2eLatencyMs?: number;
  isMuted: boolean;
  language?: SupportedLanguage;
  onToggleDetection: () => void;
  onToggleMute: () => void;
  onStopSpeech: () => void;
}

export const DetectionPanel: React.FC<DetectionPanelProps> = ({
  detectionActive,
  modelName,
  isReady,
  modelError,
  detections,
  inferenceTimeMs,
  e2eLatencyMs,
  isMuted,
  language = "ne",
  onToggleDetection,
  onToggleMute,
  onStopSpeech,
}) => {
  const isStartDisabled = !isReady && !detectionActive;

  return (
    <section
      className="detection-panel-container"
      role="region"
      aria-label="Object Detection and Spatial Awareness"
    >
      <div className="detection-panel-header">
        <div>
          <h2 className="detection-title" id="detection-heading">
            Perception & Spatial Awareness
          </h2>
          <p className="detection-subtitle">
            Model: <strong>{modelName}</strong> — Voice:{" "}
            <strong>{language === "ne" ? "नेपाली (ne)" : "English (en)"}</strong> —{" "}
            {!isReady ? (
              <span className="detection-status-unavailable">Model Unavailable</span>
            ) : detectionActive ? (
              <span className="detection-status-active">
                Active (Inference: {inferenceTimeMs}ms
                {e2eLatencyMs !== undefined && e2eLatencyMs > 0 ? `, E2E: ${e2eLatencyMs}ms` : ""})
              </span>
            ) : (
              <span className="detection-status-inactive">Inactive (Ready)</span>
            )}
          </p>
        </div>

        <div className="detection-toolbar" role="toolbar" aria-label="Detection and Speech Controls">
          <button
            type="button"
            className={`btn ${detectionActive ? "btn-secondary" : "btn-primary"}`}
            onClick={onToggleDetection}
            disabled={isStartDisabled}
            aria-disabled={isStartDisabled}
            aria-label={
              isStartDisabled
                ? "Start Detection disabled: Detection model unavailable"
                : detectionActive
                ? "Stop object detection"
                : "Start object detection"
            }
            title={isStartDisabled ? "Detection model is unavailable" : undefined}
          >
            {detectionActive ? "⏹ Stop Detection" : "▶ Start Detection"}
          </button>

          <button
            type="button"
            className="btn btn-outline"
            onClick={onToggleMute}
            aria-label={isMuted ? "Unmute spoken alerts" : "Mute spoken alerts"}
            aria-pressed={isMuted}
          >
            {isMuted ? "🔇 Unmute Audio" : "🔊 Mute Audio"}
          </button>

          <button
            type="button"
            className="btn btn-outline"
            onClick={onStopSpeech}
            aria-label="Silence ongoing speech announcement"
          >
            ⏹ Silence Speech
          </button>
        </div>
      </div>

      {!isReady && (
        <div
          className="detection-error-banner"
          role="alert"
          aria-live="assertive"
        >
          <strong>Model Unavailable: </strong>
          {modelError || "Detection model is missing or corrupt. Run 'python services/vision-engine/scripts/setup_models.py' to download verified weights."}
        </div>
      )}

      {/* Accessible Detection List with Live Region */}
      <div
        className="detection-list-wrapper"
        aria-labelledby="detection-heading"
        role="region"
        aria-live="polite"
        aria-atomic="true"
      >
        <h3 className="detection-list-title">Detected Obstacles & Objects</h3>

        {!detectionActive ? (
          <p className="detection-empty-state">
            Object detection is currently inactive. Press <strong>Start Detection</strong> to begin spatial awareness.
          </p>
        ) : detections.length === 0 ? (
          <p className="detection-empty-state">
            No obstacles detected in the immediate field of view.
          </p>
        ) : (
          <ul className="detection-items-grid" role="list">
            {detections.map((item, idx) => (
              <li
                key={`${item.class_name}-${idx}`}
                className={`detection-card sector-${item.sector}`}
                role="listitem"
              >
                <div className="detection-card-header">
                  <span className="detection-class-name">
                    {item.class_name.toUpperCase()}
                  </span>
                  <span className="detection-confidence">
                    {Math.round(item.confidence * 100)}% confidence
                  </span>
                </div>
                <div className="detection-sector-tag">
                  Position: <strong>{item.sector.toUpperCase()}</strong>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
};
