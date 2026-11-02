import React, { useEffect, useRef, useState, useCallback } from "react";
import { Header } from "./components/Header";
import { LanguageSelector } from "./components/LanguageSelector";
import { StatusIndicator } from "./components/StatusIndicator";
import { CameraPreview } from "./components/CameraPreview";
import { DeviceSelector } from "./components/DeviceSelector";
import { DetectionPanel } from "./components/DetectionPanel";
import { PrivacyNotice } from "./components/PrivacyNotice";
import { cameraApi, ApiError } from "./services/cameraApi";
import {
  ConnectionStatus,
  CameraOperationalState,
  CameraDeviceInfo,
  DetectionItem,
  SupportedLanguage,
  PerceptionHealthTelemetry,
} from "./types/api";
import "./index.css";

export const App: React.FC = () => {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("checking");
  const [cameraState, setCameraState] = useState<CameraOperationalState>("stopped");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [fps, setFps] = useState<number>(0);
  const [framesCaptured, setFramesCaptured] = useState<number>(0);
  const [perceptionHealth, setPerceptionHealth] = useState<PerceptionHealthTelemetry | null>(null);

  // Devices & Enumeration
  const [devices, setDevices] = useState<CameraDeviceInfo[]>([]);
  const [selectedDeviceIndex, setSelectedDeviceIndex] = useState<number | string>(0);

  // Detection & Speech States
  const [detectionActive, setDetectionActive] = useState<boolean>(false);
  const [modelName, setModelName] = useState<string>("FakeDetectionEngine-v1");
  const [isModelReady, setIsModelReady] = useState<boolean>(true);
  const [modelError, setModelError] = useState<string | null>(null);
  const [detections, setDetections] = useState<DetectionItem[]>([]);
  const [inferenceTimeMs, setInferenceTimeMs] = useState<number>(0);
  const [e2eLatencyMs, setE2eLatencyMs] = useState<number>(0);
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [language, setLanguage] = useState<SupportedLanguage>("ne");
  const [isLanguageUpdating, setIsLanguageUpdating] = useState<boolean>(false);

  // References for polling lifecycle and cleanup
  const activeFrameUrlRef = useRef<string | null>(null);
  const isPollingRef = useRef<boolean>(false);
  const pollTimerRef = useRef<number | null>(null);
  const frameCountWindowRef = useRef<number>(0);
  const lastFpsTimestampRef = useRef<number>(performance.now());
  const isDetectionActiveRef = useRef<boolean>(false);
  const autoStartAttemptedRef = useRef<boolean>(false);

  // Sync ref with state for polling loop
  useEffect(() => {
    isDetectionActiveRef.current = detectionActive;
  }, [detectionActive]);

  // Revoke object URL helper to avoid memory leaks while protecting in-flight paints
  const updateFrameUrl = useCallback((newUrl: string | null) => {
    const prevUrl = activeFrameUrlRef.current;
    activeFrameUrlRef.current = newUrl;
    setFrameUrl(newUrl);

    if (prevUrl && prevUrl !== newUrl) {
      window.setTimeout(() => {
        URL.revokeObjectURL(prevUrl);
      }, 100);
    }
  }, []);

  // Fetch camera devices list
  const fetchDevices = useCallback(async () => {
    try {
      const devList = await cameraApi.getDevices();
      setDevices(devList);
    } catch {
      // Keep default device 0 if endpoint unreachable
    }
  }, []);

  // Check backend engine health and initial status
  const verifyHealth = useCallback(async () => {
    try {
      // 1. Check supervisor status if running in desktop container
      const supStatus = await cameraApi.getSupervisorStatus();
      if (supStatus) {
        if (supStatus.error) {
          setConnectionStatus("error");
          setErrorMessage(supStatus.error);
          return;
        }
        if (supStatus.is_running && !supStatus.is_ready) {
          setConnectionStatus("starting");
          setErrorMessage(null);
          return;
        }
      }

      await cameraApi.checkHealth();
      setConnectionStatus("connected");
      setErrorMessage(null);

      // Check current camera status on backend
      const status = await cameraApi.getStatus();
      if (status.perception_health) {
        setPerceptionHealth(status.perception_health);
      }
      if (status.active && cameraState !== "active") {
        setCameraState("active");
        setFramesCaptured(status.frames_captured);
      }

      // Check detection model status
      try {
        const detStatus = await cameraApi.getDetectionStatus();
        setModelName(detStatus.model_name);
        setIsModelReady(detStatus.is_ready);
        setModelError(detStatus.error || null);
        setDetectionActive(detStatus.active);
      } catch {
        // Silently tolerate if detection model is not yet ready
      }

      // Check speech status & language (synchronized with authoritative backend)
      try {
        const spStatus = await cameraApi.getSpeechStatus();
        setIsMuted(spStatus.muted);
        if (spStatus.language === "ne" || spStatus.language === "en") {
          setLanguage(spStatus.language);
        } else {
          const langRes = await cameraApi.getSpeechLanguage();
          if (langRes.language === "ne" || langRes.language === "en") {
            setLanguage(langRes.language);
          }
        }
      } catch {
        // Tolerated
      }
    } catch {
      // Check supervisor to distinguish starting vs error vs disconnected
      const supStatus = await cameraApi.getSupervisorStatus();
      if (supStatus) {
        if (supStatus.error) {
          setConnectionStatus("error");
          setErrorMessage(supStatus.error);
          return;
        }
        if (supStatus.is_running && !supStatus.is_ready) {
          setConnectionStatus("starting");
          setErrorMessage(null);
          return;
        }
      }

      setConnectionStatus("disconnected");
      if (cameraState === "active") {
        setCameraState("stopped");
        updateFrameUrl(null);
      }
      // If running inside desktop container and service not yet active, attempt graceful supervisor startup
      if (!autoStartAttemptedRef.current) {
        autoStartAttemptedRef.current = true;
        setConnectionStatus("starting");
        try {
          await cameraApi.startVisionService();
          await cameraApi.checkHealth();
          setConnectionStatus("connected");
          setErrorMessage(null);
        } catch {
          // Gracefully retain starting/disconnected state
        }
      }
    }
  }, [cameraState, updateFrameUrl]);

  // Initial health check & device enumeration on mount
  useEffect(() => {
    verifyHealth();
    fetchDevices();
    const heartbeat = window.setInterval(verifyHealth, 4000);
    return () => {
      window.clearInterval(heartbeat);
    };
  }, [verifyHealth, fetchDevices]);

  // Frame polling loop
  const stopFramePolling = useCallback(() => {
    isPollingRef.current = false;
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    updateFrameUrl(null);
    setFps(0);
    setDetections([]);
    setE2eLatencyMs(0);
  }, [updateFrameUrl]);

  const pollNextFrame = useCallback(async () => {
    if (!isPollingRef.current) return;

    try {
      const { blob, metadata } = await cameraApi.fetchFrame();
      const newUrl = URL.createObjectURL(blob);
      updateFrameUrl(newUrl);
      setCameraState("active");

      // Calculate rolling FPS and track monotonic frame sequence
      frameCountWindowRef.current += 1;
      setFramesCaptured(metadata.frameId > 0 ? metadata.frameId : (prev) => prev + 1);

      const now = performance.now();
      const elapsed = now - lastFpsTimestampRef.current;
      if (elapsed >= 1000) {
        setFps(Math.round((frameCountWindowRef.current * 1000) / elapsed));
        frameCountWindowRef.current = 0;
        lastFpsTimestampRef.current = now;
      }

      // If detection is active, query latest detections periodically
      if (isDetectionActiveRef.current) {
        try {
          const detResult = await cameraApi.getLatestDetections();
          if (detResult) {
            setDetections(detResult.detections);
            setInferenceTimeMs(Math.round(detResult.inference_time_ms));
            if (detResult.e2e_latency_ms !== undefined) {
              setE2eLatencyMs(Math.round(detResult.e2e_latency_ms));
            }
          }
        } catch {
          // Non-blocking detection fetch failure
        }
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
      } else if (err instanceof ApiError && err.statusCode === 503) {
        // Check if camera reconnection attempts have been exhausted
        const isExhausted =
          err.message.toLowerCase().includes("exhausted") ||
          err.message.toLowerCase().includes("manual intervention");

        if (isExhausted) {
          setCameraState("error");
          setErrorMessage(
            "Camera reconnection exhausted after maximum attempts. Please check physical cable or network stream, then click Start Camera to retry."
          );
          stopFramePolling();
        } else {
          // Temporary camera disconnection / reconnection in progress
          setCameraState("reconnecting");
          // Back off polling interval to 1000ms to prevent HTTP 500/503 retry storms
          if (isPollingRef.current) {
            pollTimerRef.current = window.setTimeout(pollNextFrame, 1000);
          }
        }
      } else if (isPollingRef.current) {
        // Temporary read stall, brief backoff
        pollTimerRef.current = window.setTimeout(pollNextFrame, 250);
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
      await cameraApi.start(selectedDeviceIndex);
      setCameraState("active");
      setConnectionStatus("connected");
      startFramePolling();
      fetchDevices();

      // Automatically engage object detection if model is ready
      if (isModelReady && !detectionActive) {
        try {
          await cameraApi.startDetection();
          setDetectionActive(true);
        } catch {
          // Non-blocking detection startup failure
        }
      }
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
      if (detectionActive) {
        try {
          await cameraApi.stopDetection();
          setDetectionActive(false);
          setDetections([]);
        } catch {
          // Non-blocking detection halt failure
        }
      }
      fetchDevices();
    } catch (err) {
      setCameraState("stopped");
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      }
    }
  };

  // Toggle Object Detection Pipeline
  const handleToggleDetection = async () => {
    try {
      if (detectionActive) {
        await cameraApi.stopDetection();
        setDetectionActive(false);
        setDetections([]);
      } else {
        if (!isModelReady) {
          setErrorMessage(
            modelError
              ? `Cannot start detection: ${modelError}`
              : "Cannot start detection: Model is not ready or unavailable."
          );
          return;
        }
        await cameraApi.startDetection();
        setDetectionActive(true);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMessage(`Detection toggle failed: ${err.message}`);
      }
    }
  };

  // Toggle Speech Mute
  const handleToggleMute = async () => {
    try {
      const res = await cameraApi.setSpeechMute(!isMuted);
      setIsMuted(res.muted);
    } catch {
      setIsMuted((prev) => !prev);
    }
  };

  // Stop ongoing speech
  const handleStopSpeech = async () => {
    try {
      await cameraApi.stopSpeech();
    } catch {
      // Ignored
    }
  };

  // Change Speech Language dynamically (without restart)
  const handleLanguageChange = useCallback(async (newLang: SupportedLanguage) => {
    if (newLang === language) return;
    setIsLanguageUpdating(true);
    try {
      const res = await cameraApi.setSpeechLanguage(newLang);
      setLanguage(res.language);
      setErrorMessage(null);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMessage(`Language switch failed: ${err.message}`);
      } else {
        setErrorMessage("Failed to switch speech language.");
      }
    } finally {
      setIsLanguageUpdating(false);
    }
  }, [language]);

  // Global Keyboard Shortcuts for Accessible Operation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Avoid intercepting input fields or selects
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) {
        return;
      }

      if (e.code === "Space") {
        e.preventDefault();
        handleStopSpeech();
      } else if (e.code === "KeyD" && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        handleToggleDetection();
      } else if (e.code === "KeyM" && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        handleToggleMute();
      } else if (e.code === "KeyL" && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        const nextLang: SupportedLanguage = language === "ne" ? "en" : "ne";
        handleLanguageChange(nextLang);
      } else if (e.code === "KeyC" && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        verifyHealth();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleStopSpeech, handleToggleDetection, handleToggleMute, handleLanguageChange, language, verifyHealth]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopFramePolling();
      if (activeFrameUrlRef.current) {
        URL.revokeObjectURL(activeFrameUrlRef.current);
        activeFrameUrlRef.current = null;
      }
    };
  }, [stopFramePolling]);

  const isStartDisabled =
    cameraState === "active" ||
    cameraState === "starting" ||
    connectionStatus === "starting" ||
    connectionStatus === "checking" ||
    connectionStatus === "disconnected" ||
    connectionStatus === "error";

  const isStopDisabled =
    cameraState === "stopped" ||
    cameraState === "stopping" ||
    cameraState === "error";

  return (
    <div className="trinetra-app-container">
      <main className="main-content-layout">
        <Header
          rightSlot={
            <LanguageSelector
              language={language}
              onLanguageChange={handleLanguageChange}
              disabled={connectionStatus !== "connected"}
              isUpdating={isLanguageUpdating}
            />
          }
        />

        <StatusIndicator
          connectionStatus={connectionStatus}
          cameraState={cameraState}
          errorMessage={errorMessage}
          framesCaptured={framesCaptured}
          perceptionHealth={perceptionHealth}
        />

        <DeviceSelector
          devices={devices}
          selectedDeviceIndex={selectedDeviceIndex}
          cameraActive={cameraState === "active" || cameraState === "starting"}
          onSelectDevice={setSelectedDeviceIndex}
          onRefreshDevices={fetchDevices}
        />

        <CameraPreview
          cameraState={cameraState}
          frameUrl={frameUrl}
          fps={fps}
          detections={detections}
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
            aria-label="Start Camera: Begin capturing video from the selected webcam"
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
            aria-label="Refresh Status: Check vision engine service connection (Hotkey: C)"
          >
            🔄 Check Status
          </button>
        </section>

        <DetectionPanel
          detectionActive={detectionActive}
          modelName={modelName}
          isReady={isModelReady}
          modelError={modelError}
          detections={detections}
          inferenceTimeMs={inferenceTimeMs}
          e2eLatencyMs={e2eLatencyMs}
          isMuted={isMuted}
          language={language}
          onToggleDetection={handleToggleDetection}
          onToggleMute={handleToggleMute}
          onStopSpeech={handleStopSpeech}
        />

        <PrivacyNotice />
      </main>
    </div>
  );
};

export default App;
