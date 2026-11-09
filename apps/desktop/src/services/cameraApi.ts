/**
 * Trinetra Camera API Service
 * Encapsulates all network communication with the local Python Vision Engine.
 * Binds exclusively to http://127.0.0.1:8000.
 */

import {
  HealthResponse,
  CameraStatusResponse,
  CameraActionResponse,
  CameraDeviceInfo,
  FrameResponse,
  SpeechStatusResponse,
  SpeechLanguageResponse,
  SpeechLanguageUpdateResponse,
  SupportedLanguage,
  DetectionResultResponse,
  DetectionStatusResponse,
  SupervisorServiceStatus,
  AssistiveResult,
  SpeechTranscribeResponse,
  OfflineSttStatusResponse,
  BusRouteMatchResponse,
  QRPaymentResponse,
  CultureDateResponse,
  WearableStatusResponse,
  DeviceHealthResponse,
} from "../types/api";

const BASE_URL =
  typeof window !== "undefined" &&
  window.location.hostname &&
  window.location.hostname !== "localhost" &&
  window.location.hostname !== "127.0.0.1" &&
  !window.location.hostname.includes("tauri")
    ? `http://${window.location.hostname}:8000`
    : "http://127.0.0.1:8000";

// Private in-memory token cache (never stored in localStorage, sessionStorage, or logs)
let inMemorySessionToken: string | null = null;

/**
 * Checks whether the current runtime environment is inside Tauri.
 */
function isTauriEnvironment(): boolean {
  return typeof window !== "undefined" && ("__TAURI_INTERNALS__" in window || "__TAURI__" in window);
}

/**
 * Retrieves the cryptographic session token from Tauri if running in the desktop container,
 * or returns the locally configured in-memory token.
 */
export async function getSessionToken(): Promise<string | null> {
  if (inMemorySessionToken) {
    return inMemorySessionToken;
  }

  if (isTauriEnvironment()) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const token = await invoke<string>("get_session_token");
      if (token && typeof token === "string" && token.trim().length > 0) {
        inMemorySessionToken = token.trim();
        return inMemorySessionToken;
      }
    } catch {
      // In development / mock mode, invoke might fail if supervisor is not yet running
    }
  }

  return null;
}

/**
 * Explicitly sets or resets the in-memory session token (useful for testing or custom dev setups).
 */
export function setSessionToken(token: string | null): void {
  inMemorySessionToken = token;
}

export class ApiError extends Error {
  public statusCode: number;
  constructor(message: string, statusCode: number = 500) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
  }
}

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const token = await getSessionToken();
  const authHeaders: Record<string, string> = token ? { "X-Trinetra-Session-Token": token } : {};

  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...authHeaders,
        ...(options?.headers || {}),
      },
    });

    if (!res.ok) {
      if (res.status === 401) {
        // Ephemeral token mismatch (e.g. service restarted with new token); evict cached token
        inMemorySessionToken = null;
      }
      let errorMsg = `Server error (${res.status})`;
      try {
        const errorJson = await res.json();
        if (errorJson.detail) {
          errorMsg = errorJson.detail;
        }
      } catch {
        // Fall back to HTTP status message
      }
      throw new ApiError(errorMsg, res.status);
    }

    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) {
      throw err;
    }
    // Network connectivity error (e.g. service not running)
    throw new ApiError(
      "Cannot connect to the Trinetra Vision Engine at 127.0.0.1:8000. Please ensure the Python service is running.",
      0
    );
  }
}

export const cameraApi = {
  /**
   * Checks if the vision engine is online.
   */
  async checkHealth(): Promise<HealthResponse> {
    return requestJson<HealthResponse>("/api/health");
  },

  /**
   * Discovers connected camera devices on the host.
   */
  async getDevices(): Promise<CameraDeviceInfo[]> {
    return requestJson<CameraDeviceInfo[]>("/api/camera/devices");
  },

  /**
   * Retrieves operational status and frame telemetry.
   */
  async getStatus(): Promise<CameraStatusResponse> {
    return requestJson<CameraStatusResponse>("/api/camera/status");
  },

  /**
   * Starts camera hardware stream. Optionally targets specific cameraIndex.
   */
  async start(cameraIndex?: number | string): Promise<CameraActionResponse> {
    const body = cameraIndex !== undefined ? JSON.stringify({ camera_index: cameraIndex }) : undefined;
    return requestJson<CameraActionResponse>("/api/camera/start", {
      method: "POST",
      body,
    });
  },

  /**
   * Stops camera hardware stream and releases hardware lock.
   */
  async stop(): Promise<CameraActionResponse> {
    return requestJson<CameraActionResponse>("/api/camera/stop", {
      method: "POST",
    });
  },

  /**
   * Retrieves current mirror mode state.
   */
  async getMirrorMode(): Promise<{ mirror_mode: boolean }> {
    return requestJson<{ mirror_mode: boolean }>("/api/camera/mirror");
  },

  /**
   * Sets horizontal mirror mode (e.g. for selfie testing vs forward-facing wearable mode).
   */
  async setMirrorMode(mirrorMode: boolean): Promise<{ status: string; mirror_mode: boolean }> {
    return requestJson<{ status: string; mirror_mode: boolean }>("/api/camera/mirror", {
      method: "POST",
      body: JSON.stringify({ mirror_mode: mirrorMode }),
    });
  },

  /**
   * Fetches the latest JPEG video frame as an in-memory binary Blob
   * accompanied by monotonic frame telemetry headers.
   */
  async fetchFrame(): Promise<FrameResponse> {
    const url = `${BASE_URL}/api/camera/frame`;
    const fetchStart = performance.now();
    const token = await getSessionToken();
    const authHeaders: Record<string, string> = token ? { "X-Trinetra-Session-Token": token } : {};

    try {
      const res = await fetch(url, {
        method: "GET",
        headers: {
          Accept: "image/jpeg",
          ...authHeaders,
        },
      });

      if (!res.ok) {
        if (res.status === 401) {
          inMemorySessionToken = null;
        }
        let msg = `Frame request failed with code ${res.status}`;
        try {
          const errData = await res.json();
          if (errData.detail) msg = errData.detail;
        } catch {
          // Keep default message
        }
        throw new ApiError(msg, res.status);
      }

      const frameIdHeader = res.headers.get("X-Frame-Id");
      const capturedAtHeader = res.headers.get("X-Captured-At");
      const droppedFramesHeader = res.headers.get("X-Frames-Dropped");
      const sessionIdHeader = res.headers.get("X-Session-Id");

      const blob = await res.blob();
      const latencyMs = Math.round(performance.now() - fetchStart);

      return {
        blob,
        metadata: {
          frameId: frameIdHeader ? parseInt(frameIdHeader, 10) : 0,
          capturedAt: capturedAtHeader ? parseFloat(capturedAtHeader) : 0,
          droppedFrames: droppedFramesHeader ? parseInt(droppedFramesHeader, 10) : 0,
          sessionId: sessionIdHeader || "",
          latencyMs,
        },
      };
    } catch (err) {
      if (err instanceof ApiError) throw err;
      throw new ApiError("Failed to fetch camera frame from vision service.", 0);
    }
  },

  /**
   * Dispatches a spoken announcement.
   */
  async announceSpeech(text: string, priority?: string, interrupt?: boolean): Promise<{ status: string; enqueued: boolean }> {
    return requestJson<{ status: string; enqueued: boolean }>("/api/speech/announce", {
      method: "POST",
      body: JSON.stringify({ text, priority, interrupt }),
    });
  },

  /**
   * Stops current speech and flushes audio queue.
   */
  async stopSpeech(): Promise<{ status: string }> {
    return requestJson<{ status: string }>("/api/speech/stop", {
      method: "POST",
    });
  },

  /**
   * Sets speech mute state.
   */
  async setSpeechMute(muted: boolean): Promise<{ status: string; muted: boolean }> {
    return requestJson<{ status: string; muted: boolean }>("/api/speech/mute", {
      method: "POST",
      body: JSON.stringify({ muted }),
    });
  },

  /**
   * Retrieves operational status of speech engine.
   */
  async getSpeechStatus(): Promise<SpeechStatusResponse> {
    return requestJson<SpeechStatusResponse>("/api/speech/status");
  },

  /**
   * Retrieves active spoken announcement language from vision engine.
   */
  async getSpeechLanguage(): Promise<SpeechLanguageResponse> {
    return requestJson<SpeechLanguageResponse>("/api/speech/language");
  },

  /**
   * Updates active spoken announcement language without restarting camera or service.
   */
  async setSpeechLanguage(language: SupportedLanguage): Promise<SpeechLanguageUpdateResponse> {
    return requestJson<SpeechLanguageUpdateResponse>("/api/speech/language", {
      method: "POST",
      body: JSON.stringify({ language }),
    });
  },

  /**
   * Retrieves detection model status.
   */
  async getDetectionStatus(): Promise<DetectionStatusResponse> {
    return requestJson<DetectionStatusResponse>("/api/detection/status");
  },

  /**
   * Starts local object detection pipeline.
   */
  async startDetection(): Promise<{ status: string; active: boolean }> {
    return requestJson<{ status: string; active: boolean }>("/api/detection/start", {
      method: "POST",
    });
  },

  /**
   * Stops local object detection pipeline.
   */
  async stopDetection(): Promise<{ status: string; active: boolean }> {
    return requestJson<{ status: string; active: boolean }>("/api/detection/stop", {
      method: "POST",
    });
  },

  /**
   * Retrieves latest inference detections.
   */
  async getLatestDetections(): Promise<DetectionResultResponse | null> {
    return requestJson<DetectionResultResponse | null>("/api/detection/latest");
  },

  async queryScene(question: string): Promise<AssistiveResult> {
    return requestJson<AssistiveResult>("/api/scene/query", { method: "POST", body: JSON.stringify({ question, speak: true }) });
  },

  async identifyCurrency(): Promise<AssistiveResult> {
    return requestJson<AssistiveResult>("/api/currency/identify", { method: "POST", body: JSON.stringify({ speak: true }) });
  },

  async getAutoCurrencyMode(): Promise<{ enabled: boolean; model_ready: boolean }> {
    return requestJson<{ enabled: boolean; model_ready: boolean }>("/api/currency/auto-mode");
  },

  async setAutoCurrencyMode(enabled: boolean): Promise<{ enabled: boolean }> {
    return requestJson<{ enabled: boolean }>("/api/currency/auto-mode", {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
  },

  async readText(): Promise<AssistiveResult> {
    return requestJson<AssistiveResult>("/api/ocr/read", { method: "POST", body: JSON.stringify({ speak: true }) });
  },

  async recognizeFace(): Promise<AssistiveResult> {
    return requestJson<AssistiveResult>("/api/faces/recognize", { method: "POST", body: JSON.stringify({ speak: true }) });
  },

  async saveLocationBookmark(label?: string): Promise<{ status: string; bookmark: any; message: string }> {
    return requestJson<{ status: string; bookmark: any; message: string }>("/api/location/bookmark", {
      method: "POST",
      body: JSON.stringify({ label: label || null }),
    });
  },

  async getLocationBookmarks(): Promise<any[]> {
    return requestJson<any[]>("/api/location/bookmarks");
  },

  /**
   * Submits audio base64 or text transcript to local offline speech recognition engine.
   */
  async transcribeSpeech(audioBase64?: string, transcript?: string): Promise<SpeechTranscribeResponse> {
    return requestJson<SpeechTranscribeResponse>("/api/speech/transcribe", {
      method: "POST",
      body: JSON.stringify({
        audio_base64: audioBase64 || null,
        transcript: transcript || null,
      }),
    });
  },

  /**
   * Retrieves offline speech-to-text status.
   */
  async getOfflineSttStatus(): Promise<OfflineSttStatusResponse> {
    return requestJson<OfflineSttStatusResponse>("/api/speech/stt/status");
  },

  /**
   * Captures an immediate incident snapshot with cryptographic tamper-evident SHA-256 digest.
   */
  async captureIncident(notes?: string): Promise<any> {
    return requestJson<any>("/api/incident/capture", {
      method: "POST",
      body: JSON.stringify({ notes: notes || "Manual incident trigger" }),
    });
  },

  /**
   * Initiates Caretaker Safety Protocol: 10-second audible countdown before recording.
   */
  async startIncidentPrealert(notes?: string): Promise<{ status: string; prealert_id: string; countdown_seconds: number }> {
    return requestJson<{ status: string; prealert_id: string; countdown_seconds: number }>("/api/incident/prealert", {
      method: "POST",
      body: JSON.stringify({ notes: notes || "Emergency Assistance Triggered" }),
    });
  },

  /**
   * Cancels active 10-second countdown (false alarm dismissal).
   */
  async cancelIncidentPrealert(): Promise<{ status: string; message: string }> {
    return requestJson<{ status: string; message: string }>("/api/incident/cancel", {
      method: "POST",
    });
  },

  /**
   * Retrieves status of active incident pre-alert countdown.
   */
  async getIncidentPrealertStatus(): Promise<{ active: boolean; remaining_seconds: number; prealert_id?: string; notes?: string }> {
    return requestJson<{ active: boolean; remaining_seconds: number; prealert_id?: string; notes?: string }>("/api/incident/prealert/status");
  },

  /**
   * Lists all tamper-evident local incident records.
   */
  async listIncidents(): Promise<any[]> {
    return requestJson<any[]>("/api/incident/list");
  },

  /**
   * Cryptographically verifies local image and metadata integrity.
   */
  async verifyIncident(incidentId: string): Promise<{ incident_id: string; verified: boolean; error?: string }> {
    return requestJson<{ incident_id: string; verified: boolean; error?: string }>(`/api/incident/${incidentId}/verify`, {
      method: "POST",
    });
  },

  /**
   * Retrieves the current lifecycle status of the supervised Python vision service from Tauri.
   */
  async getSupervisorStatus(): Promise<SupervisorServiceStatus | null> {
    if (!isTauriEnvironment()) return null;
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      return await invoke<SupervisorServiceStatus>("get_service_status");
    } catch {
      return null;
    }
  },

  /**
   * Requests Tauri to start the Python vision service process.
   */
  async startVisionService(): Promise<SupervisorServiceStatus | null> {
    if (!isTauriEnvironment()) return null;
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      return await invoke<SupervisorServiceStatus>("start_vision_service");
    } catch {
      return null;
    }
  },

  /**
   * Requests Tauri to stop the Python vision service process.
   */
  async stopVisionService(): Promise<SupervisorServiceStatus | null> {
    if (!isTauriEnvironment()) return null;
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      return await invoke<SupervisorServiceStatus>("stop_vision_service");
    } catch {
      return null;
    }
  },

  /**
   * Matches Kathmandu public transit bus route and number from camera frame or text.
   */
  async identifyBusRoute(text?: string, speak: boolean = true): Promise<BusRouteMatchResponse> {
    return requestJson<BusRouteMatchResponse>("/api/ocr/bus-route", {
      method: "POST",
      body: JSON.stringify({ text: text || null, speak }),
    });
  },

  /**
   * Scans camera frame for Fonepay, eSewa, Khalti, or NepalQR retail standee codes.
   */
  async identifyQrPayment(speak: boolean = true): Promise<QRPaymentResponse> {
    return requestJson<QRPaymentResponse>("/api/qr/identify", {
      method: "POST",
      body: JSON.stringify({ speak }),
    });
  },

  /**
   * Retrieves current Bikram Sambat (BS) date, day of week, and active festival.
   */
  async getCultureDate(): Promise<CultureDateResponse> {
    return requestJson<CultureDateResponse>("/api/culture/date");
  },

  /**
   * Retrieves status of connected wearable hardware (ESP32-CAM smart glasses / cane).
   */
  async getWearableStatus(): Promise<WearableStatusResponse> {
    return requestJson<WearableStatusResponse>("/api/wearable/status");
  },

  /**
   * Triggers directional tactile vibration pulse to wearable frame.
   */
  async triggerWearableHaptic(location: "left" | "right" | "dual" = "dual", pattern: string = "urgent_pulse"): Promise<{ status: string }> {
    return requestJson<{ status: string }>("/api/wearable/haptic", {
      method: "POST",
      body: JSON.stringify({ location, pattern }),
    });
  },

  /**
   * Gets the active speech synthesis rate factor.
   */
  async getSpeechRate(): Promise<{ rate: number }> {
    return requestJson<{ rate: number }>("/api/speech/rate");
  },

  /**
   * Sets the speech synthesis rate factor [0.5, 2.5].
   */
  async setSpeechRate(rate: number): Promise<{ status: string; rate: number }> {
    return requestJson<{ status: string; rate: number }>("/api/speech/rate", {
      method: "POST",
      body: JSON.stringify({ rate }),
    });
  },

  /**
   * Retrieves battery, thermal, and performance tier health report.
   */
  async getDeviceHealth(): Promise<DeviceHealthResponse> {
    return requestJson<DeviceHealthResponse>("/api/device/health");
  },
};

