const API_BASE = "http://127.0.0.1:8765/api";

export type CameraStatus = {
  running: boolean;
  camera_index: number | null;
  message: string;
};

export type CameraFrame = {
  content_type: "image/jpeg";
  image_base64: string;
  captured_at: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof body.detail === "string" ? body.detail : `Vision service returned HTTP ${response.status}`);
  }
  return body as T;
}

export const visionApi = {
  health: () => request<{ status: string; service: string }>("/health"),
  status: () => request<CameraStatus>("/camera/status"),
  startCamera: () => request<CameraStatus>("/camera/start", { method: "POST" }),
  stopCamera: () => request<CameraStatus>("/camera/stop", { method: "POST" }),
  frame: () => request<CameraFrame>("/camera/frame"),
};
