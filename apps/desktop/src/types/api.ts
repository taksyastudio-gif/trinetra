/**
 * Trinetra Vision Engine API Contracts & Frontend State Types
 */

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface CameraStatusResponse {
  active: boolean;
  adapter: string;
  camera_index?: number | null;
  resolution?: string | null;
  frames_captured: number;
  uptime_seconds: number;
}

export interface CameraActionResponse {
  status: string;
  active: boolean;
  message: string;
}

export type ConnectionStatus = "checking" | "connected" | "disconnected" | "error";

export type CameraOperationalState = "stopped" | "starting" | "active" | "stopping" | "error";

export interface CameraApiError {
  status: number;
  message: string;
}
