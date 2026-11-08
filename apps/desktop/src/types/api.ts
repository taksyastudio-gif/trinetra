/**
 * Trinetra Vision Engine API Contracts & Frontend State Types
 */

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface PerceptionHealthTelemetry {
  state: "VALID_OBSERVATION" | "TEMPORARILY_DEGRADED" | "SENSOR_UNAVAILABLE" | "STALE_TERMINATED" | "RECOVERY_TRANSITION" | string;
  status: "NORMAL" | "DEGRADED" | "SEVERELY_DEGRADED" | string;
  is_degraded: boolean;
  reasons: string[];
  last_evaluated_timestamp: number | null;
  disclaimer: string;
}

export type CameraConnectionState = "disconnected" | "connecting" | "connected" | "reconnecting" | "error";

export interface CameraStatusResponse {
  active: boolean;
  adapter: string;
  camera_index?: number | string | null;
  source_type?: string | null;
  resolution?: string | null;
  frames_captured: number;
  dropped_frames?: number;
  uptime_seconds: number;
  session_id?: string | null;
  perception_health?: PerceptionHealthTelemetry | null;
  connection_state?: CameraConnectionState;
  reconnect_attempts?: number;
  max_reconnect_attempts?: number;
  last_error?: string | null;
}

export interface CameraActionResponse {
  status: string;
  active: boolean;
  message: string;
  session_id?: string | null;
}

export interface CameraDeviceInfo {
  index: number | string;
  name: string;
  is_available: boolean;
  status: string;
}

export interface FrameMetadata {
  frameId: number;
  capturedAt: number;
  droppedFrames: number;
  sessionId: string;
  latencyMs: number;
}

export interface FrameResponse {
  blob: Blob;
  metadata: FrameMetadata;
}

export type ConnectionStatus = "checking" | "starting" | "connected" | "disconnected" | "error";

export type CameraOperationalState = "stopped" | "starting" | "active" | "stopping" | "reconnecting" | "error";

export interface CameraApiError {
  status: number;
  message: string;
}

export type SupportedLanguage = "ne" | "en";

export interface SpeechLanguageResponse {
  language: SupportedLanguage;
  default_language: SupportedLanguage;
  supported_languages: SupportedLanguage[];
}

export interface SpeechLanguageUpdateRequest {
  language: SupportedLanguage;
}

export interface SpeechLanguageUpdateResponse {
  status: string;
  language: SupportedLanguage;
  previous_language: SupportedLanguage;
  supported_languages: SupportedLanguage[];
}

export interface SpeechStatusResponse {
  muted: boolean;
  paused: boolean;
  language?: SupportedLanguage;
  queue_size: number;
  backend: string;
}

export interface DetectionBox {
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}

export interface DetectionItem {
  class_name: string;
  confidence: number;
  box: DetectionBox;
  sector: "left" | "center" | "right";
}

export interface GroundHazardInfo {
  detected: boolean;
  hazard_type: string;
  severity: string;
  confidence: number;
  message: string;
  bounding_box?: number[] | null;
}

export interface DetectionResultResponse {
  frame_id: number;
  timestamp: number;
  detections: DetectionItem[];
  inference_time_ms: number;
  model_name: string;
  e2e_latency_ms?: number;
  ground_hazard?: GroundHazardInfo | null;
  auto_currency?: {
    status: string;
    denomination?: number | null;
    confidence: number;
    message: string;
    spoken_text?: string;
  } | null;
  sign_gesture?: {
    detected: boolean;
    gesture_type: string;
    confidence: number;
    message: string;
    symbol: string;
    bounding_box?: number[] | null;
  } | null;
}

export interface DetectionStatusResponse {
  active: boolean;
  model_name: string;
  is_ready: boolean;
  supported_classes: string[];
  runtime?: string;
  error?: string | null;
  error_type?: string | null;
}

export interface SupervisorServiceStatus {
  is_running: boolean;
  is_ready: boolean;
  host: string;
  port: number;
  pid: number | null;
  uptime_seconds: number;
  error: string | null;
}

export interface AssistiveResult {
  status: string;
  text?: string;
  message?: string | null;
  confidence: number;
  denomination?: number | null;
  identity?: string | null;
}

export interface SpeechTranscribeResponse {
  status: "recognized" | "silence" | "unrecognized" | "invalid_audio" | "error";
  transcript: string;
  command: string;
  confidence: number;
  message: string;
  duration_sec: number;
  is_offline: boolean;
}

export interface OfflineSttStatusResponse {
  status: string;
  engine: string;
  offline: boolean;
  supported_commands: string[];
}
