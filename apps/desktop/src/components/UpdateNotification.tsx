import React, { useEffect, useState, useCallback } from "react";
import { check, Update } from "@tauri-apps/plugin-updater";
import { cameraApi } from "../services/cameraApi";
import { SupportedLanguage } from "../types/api";

interface UpdateNotificationProps {
  language: SupportedLanguage;
  isCameraActive: boolean;
  isDetectionActive: boolean;
}

export const UpdateNotification: React.FC<UpdateNotificationProps> = ({
  language,
  isCameraActive,
  isDetectionActive,
}) => {
  const [availableUpdate, setAvailableUpdate] = useState<Update | null>(null);
  const [updateVersion, setUpdateVersion] = useState<string | null>(null);
  const [updateBody, setUpdateBody] = useState<string | null>(null);
  const [status, setStatus] = useState<"checking" | "idle" | "available" | "downloading" | "deferred" | "error">("checking");
  const [progress, setProgress] = useState<number>(0);
  const [liveAnnouncement, setLiveAnnouncement] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Announce update via voice and screen-reader live region
  const announceUpdate = useCallback((version: string) => {
    const isNe = language.startsWith("ne");
    const spoken = isNe
      ? `त्रिनेत्रको नयाँ संस्करण ${version} उपलब्ध छ।`
      : `Trinetra update version ${version} is available.`;
    
    setLiveAnnouncement(spoken);

    // Speak via vision-engine speech API with graceful fallback to browser speech
    cameraApi.announceSpeech(spoken, "informational", false).catch(() => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        try {
          const utter = new SpeechSynthesisUtterance(spoken);
          utter.lang = isNe ? "ne-NP" : "en-US";
          window.speechSynthesis.speak(utter);
        } catch (_) {}
      }
    });
  }, [language]);

  // Check on launch once
  useEffect(() => {
    let isMounted = true;

    async function checkForUpdates() {
      try {
        const update = await check({ timeout: 10000 });
        if (!isMounted) return;

        if (update) {
          setAvailableUpdate(update);
          setUpdateVersion(update.version);
          setUpdateBody(update.body || null);
          setStatus("available");
          announceUpdate(update.version);
        } else {
          setStatus("idle");
        }
      } catch (err: any) {
        if (!isMounted) return;
        // Non-fatal (e.g. running outside Tauri web preview or offline)
        setStatus("idle");
      }
    }

    // Delay slightly to let initial app and supervisor load cleanly
    const timer = setTimeout(() => {
      checkForUpdates();
    }, 2500);

    return () => {
      isMounted = false;
      clearTimeout(timer);
    };
  }, [announceUpdate]);

  const handleDefer = () => {
    if (availableUpdate) {
      availableUpdate.close().catch(() => {});
    }
    setStatus("deferred");
    const msg = language.startsWith("ne")
      ? "अद्यावधिक पछि सम्झाउन स्थगित गरियो।"
      : "Update deferred. You will be reminded on next launch.";
    setLiveAnnouncement(msg);
  };

  const isMidUse = isCameraActive || isDetectionActive;

  const handleInstall = async () => {
    if (!availableUpdate || isMidUse) return;

    try {
      setStatus("downloading");
      const startMsg = language.startsWith("ne")
        ? "अद्यावधिक डाउनलोड सुरु हुँदैछ।"
        : "Downloading update package.";
      setLiveAnnouncement(startMsg);

      let downloaded = 0;
      let total = 0;

      await availableUpdate.downloadAndInstall((event) => {
        if (event.event === "Started") {
          total = event.data.contentLength || 0;
        } else if (event.event === "Progress") {
          downloaded += event.data.chunkLength;
          if (total > 0) {
            setProgress(Math.round((downloaded / total) * 100));
          }
        } else if (event.event === "Finished") {
          setProgress(100);
        }
      });
    } catch (err: any) {
      setStatus("error");
      setErrorMessage(err?.message || "Failed to download update");
    }
  };

  if (status !== "available" && status !== "downloading" && status !== "error") {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        style={{ position: "absolute", width: "1px", height: "1px", padding: 0, margin: "-1px", overflow: "hidden", clip: "rect(0, 0, 0, 0)", border: 0 }}
      >
        {liveAnnouncement}
      </div>
    );
  }

  const isNe = language.startsWith("ne");

  return (
    <aside
      role="region"
      aria-label={isNe ? "सफ्टवेयर अद्यावधिक सूचना" : "Software Update Notification"}
      className="update-banner"
      style={{
        margin: "12px 16px",
        padding: "12px 16px",
        borderRadius: "8px",
        background: "rgba(124, 58, 237, 0.12)",
        border: "1px solid rgba(124, 58, 237, 0.4)",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        zIndex: 100,
      }}
    >
      {/* Screen-reader live region */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        style={{ position: "absolute", width: "1px", height: "1px", padding: 0, margin: "-1px", overflow: "hidden", clip: "rect(0, 0, 0, 0)", border: 0 }}
      >
        {liveAnnouncement}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
        <div>
          <strong style={{ color: "#a78bfa" }}>
            {isNe ? `✨ नयाँ त्रिनेत्र अद्यावधिक उपलब्ध: v${updateVersion}` : `✨ Trinetra Update Available: v${updateVersion}`}
          </strong>
          {updateBody && (
            <p style={{ margin: "4px 0 0", fontSize: "0.85rem", color: "var(--text-secondary, #94a3b8)" }}>
              {updateBody}
            </p>
          )}
          {isMidUse && (
            <p style={{ margin: "4px 0 0", fontSize: "0.8rem", color: "#f59e0b" }}>
              ⚠️ {isNe ? "सत्र सक्रिय छ। अद्यावधिक गर्न पहिले क्यामेरा रोक्नुहोस्।" : "Active vision session in progress. Stop camera/detection before installing."}
            </p>
          )}
        </div>

        <div style={{ display: "flex", gap: "8px" }}>
          <button
            type="button"
            onClick={handleDefer}
            disabled={status === "downloading"}
            style={{
              padding: "6px 14px",
              borderRadius: "6px",
              border: "1px solid rgba(255, 255, 255, 0.2)",
              background: "transparent",
              color: "#e2e8f0",
              cursor: "pointer",
              fontSize: "0.85rem",
            }}
          >
            {isNe ? "पछि सम्झाउनुहोस्" : "Remind Later"}
          </button>

          <button
            type="button"
            onClick={handleInstall}
            disabled={isMidUse || status === "downloading"}
            style={{
              padding: "6px 14px",
              borderRadius: "6px",
              border: "none",
              background: isMidUse ? "#475569" : "#7c3aed",
              color: "#ffffff",
              cursor: isMidUse || status === "downloading" ? "not-allowed" : "pointer",
              fontSize: "0.85rem",
              fontWeight: 600,
            }}
          >
            {status === "downloading"
              ? isNe ? `डाउनलोड हुँदैछ (${progress}%)...` : `Downloading (${progress}%)...`
              : isNe ? "अहिले स्थापना गर्नुहोस्" : "Install & Restart"}
          </button>
        </div>
      </div>

      {status === "error" && errorMessage && (
        <div style={{ color: "#ef4444", fontSize: "0.8rem" }}>
          {errorMessage}
        </div>
      )}
    </aside>
  );
};
