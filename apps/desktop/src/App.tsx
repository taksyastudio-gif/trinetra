import React, { useEffect, useRef, useState, useCallback } from "react";
import { Header } from "./components/Header";
import { LanguageSelector } from "./components/LanguageSelector";
import { StatusIndicator } from "./components/StatusIndicator";
import { CameraPreview } from "./components/CameraPreview";
import { DeviceSelector } from "./components/DeviceSelector";
import { DetectionPanel } from "./components/DetectionPanel";
import { PrivacyNotice } from "./components/PrivacyNotice";
import { AssistiveActions } from "./components/AssistiveActions";
import { NonVerbalAAC } from "./components/NonVerbalAAC";
import { SignLanguageTranslator } from "./components/SignLanguageTranslator";
import { InstallModal } from "./components/InstallModal";
import { UpdateNotification } from "./components/UpdateNotification";
import { triggerHaptic } from "./services/voiceCommands";
import { cameraApi, ApiError } from "./services/cameraApi";
import { spatialAudioRadar } from "./services/spatialAudioRadar";
import {
  ConnectionStatus,
  CameraOperationalState,
  CameraDeviceInfo,
  DetectionItem,
  GroundHazardInfo,
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
  const [audioRadarActive, setAudioRadarActive] = useState<boolean>(false);
  const [groundHazard, setGroundHazard] = useState<GroundHazardInfo | null>(null);
  const [autoCurrency, setAutoCurrency] = useState<any | null>(null);
  const [signGesture, setSignGesture] = useState<any | null>(null);
  const [featureTab, setFeatureTab] = useState<"vision" | "deaf" | "actions">("vision");
  const [hearingReplyInput, setHearingReplyInput] = useState<string>("");
  const [displayedHearingReply, setDisplayedHearingReply] = useState<string | null>(null);
  const [isInstallModalOpen, setIsInstallModalOpen] = useState<boolean>(false);
  const [targetFps, setTargetFps] = useState<number>(30);
  const [inferenceTimeMs, setInferenceTimeMs] = useState<number>(0);
  const [e2eLatencyMs, setE2eLatencyMs] = useState<number>(0);
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [language, setLanguage] = useState<SupportedLanguage>("ne");
  const [isLanguageUpdating, setIsLanguageUpdating] = useState<boolean>(false);
  const [mirrorMode, setMirrorMode] = useState<boolean>(true);
  const targetFpsRef = useRef<number>(30);

  // Caretaker Safety Protocol: 10-Second Countdown Pre-Alert
  const [preAlertActive, setPreAlertActive] = useState<boolean>(false);
  const [preAlertSeconds, setPreAlertSeconds] = useState<number>(10);

  const handleTriggerEmergencyPrealert = useCallback(async () => {
    try {
      const res = await cameraApi.startIncidentPrealert("Emergency Triggered by User");
      setPreAlertActive(true);
      setPreAlertSeconds(res.countdown_seconds || 10);
      triggerHaptic("command");
    } catch {
      // Non-blocking fallback
    }
  }, []);

  const handleCancelEmergencyPrealert = useCallback(async () => {
    try {
      await cameraApi.cancelIncidentPrealert();
      setPreAlertActive(false);
      triggerHaptic("success");
    } catch {
      setPreAlertActive(false);
    }
  }, []);

  useEffect(() => {
    if (!preAlertActive) return;
    const interval = window.setInterval(() => {
      setPreAlertSeconds((prev) => {
        if (prev <= 1) {
          setPreAlertActive(false);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [preAlertActive]);

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

      // Check mirror mode
      try {
        const mirrorRes = await cameraApi.getMirrorMode();
        setMirrorMode(mirrorRes.mirror_mode);
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
    spatialAudioRadar.stop();
    setGroundHazard(null);
    setAutoCurrency(null);
    setSignGesture(null);
    setE2eLatencyMs(0);
  }, [updateFrameUrl]);

  const pollNextFrame = useCallback(async () => {
    if (!isPollingRef.current) return;

    try {
      const fetchStart = performance.now();
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

      // Schedule next frame poll at high frame rate without blocking on AI inference
      if (isPollingRef.current) {
        const fetchDuration = performance.now() - fetchStart;
        let delay = 0;
        if (targetFpsRef.current > 0) {
          const targetInterval = 1000 / targetFpsRef.current;
          delay = Math.max(0, Math.round(targetInterval - fetchDuration));
        }
        pollTimerRef.current = window.setTimeout(pollNextFrame, delay);
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

  // Decoupled asynchronous detection and metadata polling loop (~10-15 Hz)
  useEffect(() => {
    if (!detectionActive || cameraState !== "active") return;
    let cancelled = false;

    const pollDetections = async () => {
      try {
        const detResult = await cameraApi.getLatestDetections();
        if (!cancelled && detResult) {
          setDetections(detResult.detections || []);
          if (audioRadarActive) {
            spatialAudioRadar.updateDetections(detResult.detections || []);
          }
          setGroundHazard(detResult.ground_hazard || null);
          setAutoCurrency(detResult.auto_currency || null);
          setSignGesture(detResult.sign_gesture || null);
          setInferenceTimeMs(Math.round(detResult.inference_time_ms));
          if (detResult.e2e_latency_ms !== undefined) {
            setE2eLatencyMs(Math.round(detResult.e2e_latency_ms));
          }
        }
      } catch {
        // Tolerated non-blocking detection error
      }
    };

    const intervalTimer = window.setInterval(pollDetections, 100);
    pollDetections();

    return () => {
      cancelled = true;
      window.clearInterval(intervalTimer);
    };
  }, [detectionActive, cameraState]);

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
          setGroundHazard(null);
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

  // Toggle Camera Horizontal Mirror Mode
  const handleToggleMirror = async () => {
    const nextMode = !mirrorMode;
    try {
      const res = await cameraApi.setMirrorMode(nextMode);
      setMirrorMode(res.mirror_mode);
    } catch (err) {
      console.error("Failed to toggle mirror mode:", err);
    }
  };

  // Toggle Object Detection Pipeline
  const handleToggleDetection = async () => {
    try {
      if (detectionActive) {
        await cameraApi.stopDetection();
        setDetectionActive(false);
        setDetections([]);
        setGroundHazard(null);
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

  // Fullscreen Accessibility Double-Tap Gesture Handler
  const handleDoubleTap = useCallback(async () => {
    if (cameraState !== "active") return;
    triggerHaptic("command");
    try {
      // First try to read text / OCR if there is any visible text
      const ocrRes = await cameraApi.readText();
      if (ocrRes && ocrRes.text && ocrRes.text.trim().length > 3) {
        await cameraApi.announceSpeech(`पढिएको अक्षर: ${ocrRes.text.trim()}`, "critical_hazard", true);
        return;
      }
      // Otherwise describe the overall scene
      const sceneRes = await cameraApi.queryScene("वरिपरि के छ?");
      if (sceneRes && sceneRes.text) {
        await cameraApi.announceSpeech(sceneRes.text, "spatial_navigation", true);
      }
    } catch {
      // Non-blocking fallback
    }
  }, [cameraState]);

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

  // Spoken voice guidance onboarding and instructions
  const triggerVoiceHelp = useCallback(async () => {
    try {
      const guidance =
        language === "ne"
          ? "त्रिनेत्र सहायकमा स्वागत छ। नोट पहिचान गर्न क्यामेरा अगाडि नोट समात्नुहोस्। सांकेतिक भाषामा नमस्ते, हात उठाएर रोक्नुहोस्, वा थम्ब्स-अप गर्नुहोस्। स्क्रिनमा दुई पटक थिचेर वरिपरिको विवरण सुन्न सक्नुहुन्छ।"
          : "Welcome to Trinetra Assistant. Hold banknotes in front of the camera to detect currency. Use sign gestures like Namaste, Palm Stop, or Thumbs Up. Double tap anywhere on screen to hear a scene description.";
      await cameraApi.announceSpeech(guidance, "critical_hazard", true);
    } catch {
      // Non-blocking fallback
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
        if (cameraState === "active") {
          handleDoubleTap();
        }
      } else if (e.code === "KeyR" && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        setAudioRadarActive((prev) => {
          const next = !prev;
          spatialAudioRadar.setEnabled(next);
          triggerHaptic("command");
          return next;
        });
      } else if (e.code === "Digit1" && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        setFeatureTab("vision");
      } else if (e.code === "Digit2" && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        setFeatureTab("deaf");
      } else if (e.code === "Digit3" && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        setFeatureTab("actions");
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
  }, [
    handleStopSpeech,
    handleDoubleTap,
    cameraState,
    handleToggleDetection,
    handleToggleMute,
    handleLanguageChange,
    language,
    verifyHealth,
  ]);

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
          targetFps={targetFps}
          onChangeFps={(val) => {
            setTargetFps(val);
            targetFpsRef.current = val;
          }}
          onOpenInstallModal={() => setIsInstallModalOpen(true)}
          onTriggerVoiceHelp={triggerVoiceHelp}
          rightSlot={
            <LanguageSelector
              language={language}
              onLanguageChange={handleLanguageChange}
              disabled={connectionStatus !== "connected"}
              isUpdating={isLanguageUpdating}
            />
          }
        />

        <UpdateNotification
          language={language}
          isCameraActive={cameraState === "active" || cameraState === "starting"}
          isDetectionActive={detectionActive}
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

        {/* Mode Navigation: 3 Clear Purpose-Driven Modes */}
        <nav
          className="feature-tabs-bar"
          role="tablist"
          aria-label="Application Mode Selector"
          style={{
            display: "flex",
            gap: "10px",
            flexWrap: "wrap",
            backgroundColor: "var(--bg-surface)",
            padding: "8px 12px",
            borderRadius: "10px",
            border: "2px solid var(--border-color)",
            marginTop: "4px",
            marginBottom: "8px",
          }}
        >
          {[
            { id: "vision", label: "👁️ Vision & Road Safety (दृष्टि र बाटो निर्देशन)" },
            { id: "deaf", label: "🤝 Deaf & Hearing Two-Way Bridge (बहिरा तथा सुस्त श्रवण संवाद)" },
            { id: "actions", label: "⚡ Essential Tools & SOS (उपकरण तथा आपतकालीन)" },
          ].map((tab) => {
            const isActive = featureTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setFeatureTab(tab.id as any)}
                style={{
                  minHeight: "46px",
                  padding: "10px 20px",
                  fontSize: "1rem",
                  fontWeight: isActive ? 800 : 600,
                  backgroundColor: isActive ? "var(--border-focus)" : "var(--bg-surface-elevated)",
                  color: isActive ? "#041322" : "var(--text-primary)",
                  border: isActive ? "2px solid #ffffff" : "1px solid var(--border-color)",
                  borderRadius: "8px",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                  flex: "1 1 auto",
                  textAlign: "center",
                }}
              >
                {tab.label}
              </button>
            );
          })}
        </nav>

        {/* Caretaker Safety Protocol: Active Emergency Countdown Banner */}
        {preAlertActive && (
          <div
            role="alert"
            aria-live="assertive"
            style={{
              backgroundColor: "rgba(220, 38, 38, 0.95)",
              color: "#ffffff",
              padding: "16px 20px",
              borderRadius: "12px",
              marginBottom: "16px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "12px",
              border: "3px solid #fecaca",
              boxShadow: "0 8px 24px rgba(220, 38, 38, 0.5)",
              animation: "pulse 1s infinite",
            }}
          >
            <div>
              <div style={{ fontSize: "1.2rem", fontWeight: 800 }}>
                🚨 आपतकालीन सूचना सक्रिय हुँदैछ: {preAlertSeconds} सेकेन्ड बाँकी...
              </div>
              <div style={{ fontSize: "0.88rem", opacity: 0.9, marginTop: "2px" }}>
                यदि यो गल्तीले थिचिएको हो भने तुरुन्त रद्द गर्नुहोस् (Touch below to cancel if you are safe).
              </div>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleCancelEmergencyPrealert}
              style={{
                backgroundColor: "#ffffff",
                color: "#dc2626",
                fontWeight: 900,
                fontSize: "1.05rem",
                padding: "10px 24px",
                border: "none",
                borderRadius: "8px",
                cursor: "pointer",
              }}
            >
              ✅ म ठीक छु — रद्द गर्नुहोस् (Cancel)
            </button>
          </div>
        )}

        {/* Camera Preview is active for Vision Mode and Deaf Two-Way Sign Translation */}
        {(featureTab === "vision" || featureTab === "deaf") && (
          <>
            <CameraPreview
              cameraState={cameraState}
              frameUrl={frameUrl}
              fps={fps}
              detections={detections}
              groundHazard={groundHazard}
              autoCurrency={autoCurrency}
              signGesture={signGesture}
              onDoubleTap={handleDoubleTap}
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
                onClick={handleToggleMirror}
                title={mirrorMode ? "Laptop Mirror Mode Active: User Right = Screen Right" : "Wearable Forward Mode Active: For glasses / ESP32-CAM"}
                aria-label="Toggle camera mirror perspective mode"
              >
                {mirrorMode ? "🪞 Mirror Mode (Laptop)" : "👓 Wearable Mode (Forward)"}
              </button>

              <button
                type="button"
                className={`btn ${audioRadarActive ? "btn-primary" : "btn-outline"}`}
                onClick={() => {
                  setAudioRadarActive((prev) => {
                    const next = !prev;
                    spatialAudioRadar.setEnabled(next);
                    triggerHaptic("command");
                    return next;
                  });
                }}
                title="Directional binaural acoustic sonar radar for blind spatial orientation (Hotkey: R)"
                aria-label={`Toggle Spatial Audio Radar. Currently ${audioRadarActive ? "Active" : "Disabled"}`}
                style={{
                  backgroundColor: audioRadarActive ? "#38bdf8" : undefined,
                  color: audioRadarActive ? "#041322" : undefined,
                  fontWeight: 700,
                }}
              >
                {audioRadarActive ? "📡 Radar Sonar: ON" : "📡 Radar Sonar: OFF"}
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
          </>
        )}

        {/* MODE 1: Vision & Road Safety */}
        {featureTab === "vision" && (
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
        )}

        {/* MODE 2: Two-Way Deaf & Hearing Communication Bridge */}
        {featureTab === "deaf" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
            {/* Direction A: Deaf Person -> Hearing Person (Sign Language translation) */}
            <SignLanguageTranslator
              currentSign={signGesture}
              disabled={connectionStatus !== "connected"}
            />

            {/* Direction B: Hearing Person -> Deaf Person (Show text on screen) */}
            <div
              style={{
                backgroundColor: "var(--bg-surface)",
                border: "2px solid var(--border-color)",
                borderRadius: "12px",
                padding: "16px",
              }}
            >
              <h2 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "8px", color: "#facc15" }}>
                💬 Hearing Person Reply (सुन्ने व्यक्तिले बहिरा व्यक्तिलाई लेख्ने ठाउँ)
              </h2>
              <p style={{ fontSize: "0.88rem", color: "var(--text-muted)", marginBottom: "12px" }}>
                Type your message below. It will display in huge, clear visual letters on screen for the deaf person to read.
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (hearingReplyInput.trim()) {
                    setDisplayedHearingReply(hearingReplyInput.trim());
                    setHearingReplyInput("");
                  }
                }}
                style={{ display: "flex", gap: "10px" }}
              >
                <input
                  type="text"
                  value={hearingReplyInput}
                  onChange={(e) => setHearingReplyInput(e.target.value)}
                  placeholder="Type message to show on screen (उदा: कता जान लाग्नुभएको?)..."
                  style={{
                    flex: 1,
                    minHeight: "44px",
                    padding: "8px 14px",
                    fontSize: "1rem",
                    borderRadius: "8px",
                    backgroundColor: "var(--bg-surface-elevated)",
                    color: "var(--text-primary)",
                    border: "1px solid var(--border-color)",
                  }}
                />
                <button
                  type="submit"
                  className="btn btn-primary"
                  style={{ minHeight: "44px", padding: "8px 20px" }}
                >
                  Show on Screen
                </button>
              </form>

              {displayedHearingReply && (
                <div
                  style={{
                    marginTop: "16px",
                    backgroundColor: "#000000",
                    border: "3px solid #facc15",
                    borderRadius: "10px",
                    padding: "18px",
                    textAlign: "center",
                  }}
                >
                  <span style={{ fontSize: "0.85rem", color: "#94a3b8", display: "block", marginBottom: "4px" }}>
                    VISUAL SUBTITLE FOR DEAF USER:
                  </span>
                  <div style={{ color: "#facc15", fontSize: "1.7rem", fontWeight: 800, lineHeight: 1.3 }}>
                    💬 {displayedHearingReply}
                  </div>
                </div>
              )}
            </div>

            {/* Quick Non-Verbal Phrases (Deaf user taps -> speaks through speakers) */}
            <NonVerbalAAC disabled={connectionStatus !== "connected"} />
          </div>
        )}

        {/* MODE 3: Essential Tools & SOS */}
        {featureTab === "actions" && (
          <AssistiveActions
            disabled={cameraState !== "active" || connectionStatus !== "connected"}
            onTriggerSOS={handleTriggerEmergencyPrealert}
          />
        )}

        <PrivacyNotice />

        <InstallModal
          isOpen={isInstallModalOpen}
          onClose={() => setIsInstallModalOpen(false)}
        />
      </main>
    </div>
  );
};

export default App;
