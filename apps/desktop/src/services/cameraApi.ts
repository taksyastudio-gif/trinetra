/**
 * Trinetra Camera API Service
 * Encapsulates all network communication with the local Python Vision Engine.
 * Binds exclusively to http://127.0.0.1:8000.
 */

import {
  HealthResponse,
  CameraStatusResponse,
  CameraActionResponse,
} from "../types/api";

const BASE_URL = "http://127.0.0.1:8000";

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
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options?.headers || {}),
      },
    });

    if (!res.ok) {
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
   * Retrieves operational status and frame telemetry.
   */
  async getStatus(): Promise<CameraStatusResponse> {
    return requestJson<CameraStatusResponse>("/api/camera/status");
  },

  /**
   * Starts camera hardware stream.
   */
  async start(): Promise<CameraActionResponse> {
    return requestJson<CameraActionResponse>("/api/camera/start", {
      method: "POST",
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
   * Fetches the latest JPEG video frame as an in-memory binary Blob.
   */
  async fetchFrame(): Promise<Blob> {
    const url = `${BASE_URL}/api/camera/frame`;
    try {
      const res = await fetch(url, {
        method: "GET",
        headers: {
          Accept: "image/jpeg",
        },
      });

      if (!res.ok) {
        let msg = `Frame request failed with code ${res.status}`;
        try {
          const errData = await res.json();
          if (errData.detail) msg = errData.detail;
        } catch {
          // Keep default message
        }
        throw new ApiError(msg, res.status);
      }

      return await res.blob();
    } catch (err) {
      if (err instanceof ApiError) throw err;
      throw new ApiError("Failed to fetch camera frame from vision service.", 0);
    }
  },
};
