import React, { useEffect, useRef, useState, useCallback } from "react";
import { Header } from "./components/Header";
import { StatusIndicator } from "./components/StatusIndicator";
import { CameraPreview } from "./components/CameraPreview";
import { PrivacyNotice } from "./components/PrivacyNotice";
import { cameraApi, ApiError } from "./services/cameraApi";
import {
  ConnectionStatus,
  CameraOperationalState,
} from "./types/api";
import "./index.css";

export const App: React.FC = () => {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("checking");
  const [cameraState, setCameraState] = useState<CameraOperationalState>("stopped");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [fps, setFps] = useState<number>(0);
  const [framesCaptured, setFramesCaptured] = useState<number>(0);

  // References for polling lifecycle and cleanup
  const activeFrameUrlRef = useRef<string | null>(null);
  const isPollingRef = useRef<boolean>(false);
  const pollTimerRef = useRef<number | null>(null);
  const frameCountWindowRef = useRef<number>(0);
  const lastFpsTimestampRef = useRef<number>(performance.now());

  // Revoke object URL helper to avoid memory leaks
  const updateFrameUrl = useCallback((newUrl: string | null) => {
    if (activeFrameUrlRef.current && activeFrameUrlRef.current !== newUrl) {
      URL.revokeObjectURL(activeFrameUrlRef.current);
    }
    activeFrameUrlRef.current = newUrl;
    setFrameUrl(newUrl);
  }, []);

  // Check backend engine health
  const verifyHealth = useCallback(async () => {
    try {
      await cameraApi.checkHealth();
      setConnectionStatus("connected");
      setErrorMessage(null);

      // Check current camera status on backend
      const status = await cameraApi.getStatus();
      if (status.active && cameraState !== "active") {
        setCameraState("active");
        setFramesCaptured(status.frames_captured);
      }
    } catch {
      setConnectionStatus("disconnected");
      if (cameraState === "active") {
        setCameraState("stopped");
        updateFrameUrl(null);
      }
    }
  }, [cameraState, updateFrameUrl]);

  // Initial health check on mount + periodic heartbeat
  useEffect(() => {
    verifyHealth();
    const heartbeat = window.setInterval(verifyHealth, 4000);
    return () => {
      window.clearInterval(heartbeat);
    };
  }, [verifyHealth]);

  // Frame polling loop
  const stopFramePolling = useCallback(() => {
    isPollingRef.current = false;
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    updateFrameUrl(null);
    setFps(0);
  }, [updateFrameUrl]);

  const pollNextFrame = useCallback(async () => {
    if (!isPollingRef.current) return;

    try {
      const blob = await cameraApi.fetchFrame();
      const newUrl = URL.createObjectURL(blob);
      updateFrameUrl(newUrl);

      // Calculate rolling FPS
      frameCountWindowRef.current += 1;
      setFramesCaptured((prev) => prev + 1);

      const now = performance.now();
      const elapsed = now - lastFpsTimestampRef.current;
      if (elapsed >= 1000) {
        setFps(Math.round((frameCountWindowRef.current * 1000) / elapsed));
        frameCountWindowRef.current = 0;
        lastFpsTimestampRef.current = now;
      }

      // Schedule next frame poll at ~20 FPS (50ms interval) to avoid CPU spikes
      if (isPollingRef.current) {
        pollTimerRef.current = window.setTimeout(pollNextFrame, 50);
      }
    } catch (err) {
      if (err instanceof ApiError && err.statusCode === 409) {
        // Camera was stopped remotely
        setCameraState("stopped");
        stopFramePolling();
      } else if (isPollingRef.current) {
        // Temporary read stall, brief backoff
        pollTimerRef.current = window.setTimeout(pollNextFrame, 150);
      }
    }
  }, [updateFrameUrl, stopFramePolling]);

  const startFramePolling = useCallback(() => {
    if (isPollingRef.current) return;
    isPollingRef.current = true;
    frameCountWindowRef.current = 0;
    lastFpsTimestampRef.current = performance.now();
    pollNextFrame();
  }, [pollNextFrame]);

  // Handle user starting camera
  const handleStartCamera = async () => {
    setErrorMessage(null);
    setCameraState("starting");

    try {
      await cameraApi.start();
      setCameraState("active");
      setConnectionStatus("connected");
      startFramePolling();
    } catch (err) {
      setCameraState("error");
      stopFramePolling();
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("An unexpected error occurred while starting the camera.");
      }
    }
  };

  // Handle user stopping camera
  const handleStopCamera = async () => {
    setErrorMessage(null);
    setCameraState("stopping");
    stopFramePolling();

    try {
      await cameraApi.stop();
      setCameraState("stopped");
    } catch (err) {
      setCameraState("stopped");
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      }
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopFramePolling();
    };
  }, [stopFramePolling]);

  const isStartDisabled =
    cameraState === "active" ||
    cameraState === "starting" ||
    connectionStatus === "disconnected";

  const isStopDisabled =
    cameraState === "stopped" ||
    cameraState === "stopping" ||
    cameraState === "error";

  return (
    <div className="trinetra-app-container">
      <main className="main-content-layout">
        <Header />

        <StatusIndicator
          connectionStatus={connectionStatus}
          cameraState={cameraState}
          errorMessage={errorMessage}
          framesCaptured={framesCaptured}
        />

        <CameraPreview
          cameraState={cameraState}
          frameUrl={frameUrl}
          fps={fps}
        />

        {/* Primary Accessible Controls */}
        <section
          className="controls-toolbar"
          aria-label="Camera Controls Toolbar"
          role="toolbar"
        >
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleStartCamera}
            disabled={isStartDisabled}
            aria-disabled={isStartDisabled}
            aria-label="Start Camera: Begin capturing video from the webcam"
          >
            ▶ Start Camera
          </button>

          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleStopCamera}
            disabled={isStopDisabled}
            aria-disabled={isStopDisabled}
            aria-label="Stop Camera: Release camera hardware and halt video ingestion"
          >
            ⏹ Stop Camera
          </button>

          <button
            type="button"
            className="btn btn-outline"
            onClick={verifyHealth}
            aria-label="Refresh Status: Check vision engine service connection"
          >
            🔄 Check Status
          </button>
        </section>

        <PrivacyNotice />
      </main>
    </div>
  );
};

export default App;
