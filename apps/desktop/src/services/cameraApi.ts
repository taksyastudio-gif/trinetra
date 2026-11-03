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
} from "../types/api";

const BASE_URL = "http://127.0.0.1:8000";

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

  async readText(): Promise<AssistiveResult> {
    return requestJson<AssistiveResult>("/api/ocr/read", { method: "POST", body: JSON.stringify({ speak: true }) });
  },

  async recognizeFace(): Promise<AssistiveResult> {
    return requestJson<AssistiveResult>("/api/faces/recognize", { method: "POST", body: JSON.stringify({ speak: true }) });
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
};

