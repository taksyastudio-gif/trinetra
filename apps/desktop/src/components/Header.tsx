import React, { useState, useEffect } from "react";

interface HeaderProps {
  rightSlot?: React.ReactNode;
  onOpenInstallModal?: () => void;
  onTriggerVoiceHelp?: () => void;
  targetFps?: number;
  onChangeFps?: (fps: number) => void;
}

export const Header: React.FC<HeaderProps> = ({
  rightSlot,
  onOpenInstallModal,
  onTriggerVoiceHelp,
  targetFps = 30,
  onChangeFps,
}) => {
  const [deferredPrompt, setDeferredPrompt] = useState<any>(null);
  const [isInstalled, setIsInstalled] = useState(false);

  useEffect(() => {
    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e);
    };

    window.addEventListener("beforeinstallprompt", handleBeforeInstall);
    window.addEventListener("appinstalled", () => {
      setIsInstalled(true);
      setDeferredPrompt(null);
    });

    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstall);
    };
  }, []);

  const handleInstallClick = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === "accepted") {
      setIsInstalled(true);
    }
    setDeferredPrompt(null);
  };

  return (
    <header className="app-header" role="banner">
      <div className="header-top-row">
        <div className="header-brand">
          <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            <h1 className="header-title" style={{ margin: 0 }}>TRINETRA (त्रिनेत्र)</h1>
            <span
              style={{
                backgroundColor: "#0284c7",
                color: "#ffffff",
                padding: "3px 10px",
                borderRadius: "14px",
                fontSize: "0.78rem",
                fontWeight: 700,
                letterSpacing: "0.5px",
              }}
              aria-label="Release Version"
            >
              v0.2.0
            </span>
          </div>
        </div>
        <div className="header-actions" style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
          {onChangeFps && (
            <div style={{ display: "inline-flex", alignItems: "center", gap: "4px", backgroundColor: "#1e293b", padding: "4px 8px", borderRadius: "8px", border: "1px solid #334155" }}>
              <span style={{ fontSize: "0.75rem", color: "#94a3b8" }}>⚡ FPS:</span>
              <select
                value={targetFps}
                onChange={(e) => onChangeFps(Number(e.target.value))}
                style={{
                  backgroundColor: "transparent",
                  color: "#38bdf8",
                  border: "none",
                  fontSize: "0.82rem",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
                aria-label="Select Target Frame Rate"
              >
                <option value={15} style={{ backgroundColor: "#1e293b", color: "#fff" }}>15 FPS (Eco)</option>
                <option value={30} style={{ backgroundColor: "#1e293b", color: "#fff" }}>30 FPS (Smooth)</option>
                <option value={60} style={{ backgroundColor: "#1e293b", color: "#fff" }}>60 FPS (Ultra)</option>
                <option value={0} style={{ backgroundColor: "#1e293b", color: "#fff" }}>Max (144Hz Sync)</option>
              </select>
            </div>
          )}

          {onTriggerVoiceHelp && (
            <button
              type="button"
              className="btn btn-outline"
              onClick={onTriggerVoiceHelp}
              style={{ fontSize: "0.82rem", padding: "6px 10px" }}
              aria-label="Listen to voice usage guide"
            >
              🔊 गाइड (Voice Help)
            </button>
          )}

          <button
            type="button"
            className="btn btn-primary"
            onClick={onOpenInstallModal || handleInstallClick}
            style={{
              fontSize: "0.82rem",
              padding: "6px 12px",
              display: "flex",
              alignItems: "center",
              gap: "5px",
              backgroundColor: isInstalled ? "#059669" : "#10b981",
              borderColor: isInstalled ? "#059669" : "#10b981",
              color: "#ffffff",
              fontWeight: "bold",
            }}
            aria-label="Install Trinetra app on mobile or desktop"
          >
            {isInstalled ? "✅ स्थापित भयो (Installed)" : "📲 डाउनलोड / स्थापना (Install)"}
          </button>
          {rightSlot}
        </div>
      </div>
      <p className="header-subtitle" style={{ marginTop: "8px", fontSize: "0.92rem", color: "var(--text-secondary)" }}>
        नेपालको आफ्नै अफलाइन दृष्टि तथा संवाद सहायक — 100% Offline Edge Vision, Devanagari OCR, Currency Counter & Non-Verbal AAC for Nepal.
      </p>
    </header>
  );
};
