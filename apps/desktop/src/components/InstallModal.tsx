import React from "react";
import { triggerHaptic } from "../services/voiceCommands";

interface InstallModalProps {
  isOpen: boolean;
  onClose: () => void;
  deferredPrompt?: any;
}

export const InstallModal: React.FC<InstallModalProps> = ({
  isOpen,
  onClose,
  deferredPrompt,
}) => {
  if (!isOpen) return null;

  const currentHost = window.location.host;
  const isLocalhost = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
  const mobileUrl = `${window.location.protocol}//${currentHost}`;

  const handleInstallPWA = async () => {
    triggerHaptic("success");
    if (deferredPrompt) {
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
    } else {
      alert("तपाईंको ब्राउजर मेनुमा गएर 'Add to Home Screen' वा 'Install App' थिच्नुहोस्।");
    }
    onClose();
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.75)",
        backdropFilter: "blur(4px)",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        zIndex: 1000,
        padding: "16px",
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="install-modal-title"
    >
      <div
        style={{
          backgroundColor: "#1e293b",
          border: "2px solid #38bdf8",
          borderRadius: "16px",
          maxWidth: "520px",
          width: "100%",
          padding: "24px",
          boxShadow: "0 20px 40px rgba(0, 0, 0, 0.6)",
          color: "#ffffff",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <h2 id="install-modal-title" style={{ fontSize: "1.3rem", margin: 0, fontWeight: 800, color: "#38bdf8" }}>
            📲 मोबाइल तथा डेस्कटपमा १-क्लिक स्थापना
          </h2>
          <button
            type="button"
            className="btn btn-outline btn-sm"
            onClick={onClose}
            style={{ fontSize: "1.1rem", padding: "2px 8px" }}
            aria-label="Close modal"
          >
            ✕
          </button>
        </div>

        <p style={{ fontSize: "0.95rem", color: "#cbd5e1", lineHeight: 1.5, marginBottom: "16px" }}>
          त्रिनेत्रलाई कुनै पनि <strong>Android, iPhone वा ल्यापटपमा</strong> एपको रूपमा सिधै डाउनलोड तथा इन्स्टल गर्न सकिन्छ।
          कुनै प्लेस्टोर वा इन्टरनेट चाहिँदैन — १००% अफलाइन चल्छ!
        </p>

        {/* 1-Click PWA Install Button */}
        <div style={{ marginBottom: "20px" }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleInstallPWA}
            style={{
              width: "100%",
              padding: "14px",
              fontSize: "1.05rem",
              fontWeight: 800,
              backgroundColor: "#10b981",
              borderColor: "#10b981",
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              gap: "10px",
              boxShadow: "0 4px 15px rgba(16, 185, 129, 0.4)",
            }}
          >
            <span>📥</span>
            <span>अहिले नै १-क्लिकमा इन्स्टल गर्नुहोस् (Install App)</span>
          </button>
        </div>

        {/* Mobile Hotspot / Phone QR Connection */}
        <div
          style={{
            backgroundColor: "#0f172a",
            borderRadius: "10px",
            padding: "14px",
            border: "1px solid #334155",
            marginBottom: "16px",
          }}
        >
          <div style={{ fontWeight: 700, fontSize: "0.95rem", color: "#facc15", marginBottom: "6px" }}>
            📶 मोबाइल फोनमा कसरी खोल्ने? (Phone Access)
          </div>
          <ol style={{ paddingLeft: "20px", fontSize: "0.85rem", color: "#94a3b8", lineHeight: 1.6 }}>
            <li>ल्यापटप वा फोनको <strong>Wi-Fi / Hotspot</strong> अन गर्नुहोस्।</li>
            <li>मोबाइलको Chrome ब्राउजरमा यो ठेगाना खोल्नुहोस्:
              <br />
              <code style={{ color: "#38bdf8", fontWeight: "bold", fontSize: "0.95rem" }}>
                {isLocalhost ? `http://<laptop-wifi-ip>:${window.location.port || "3000"}` : mobileUrl}
              </code>
            </li>
            <li>ब्राउजरको मेनुमा गएर <strong>"Add to Home Screen"</strong> वा <strong>"Install App"</strong> थिच्नुहोस्।</li>
          </ol>
        </div>

        <div style={{ textAlign: "right" }}>
          <button type="button" className="btn btn-outline" onClick={onClose}>
            बन्द गर्नुहोस् (Close)
          </button>
        </div>
      </div>
    </div>
  );
};
