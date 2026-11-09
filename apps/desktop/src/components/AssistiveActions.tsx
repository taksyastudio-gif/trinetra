import React, { useState, useEffect, useCallback } from "react";
import { cameraApi, ApiError } from "../services/cameraApi";
import { voiceCommandService, VoiceCommandMatch, triggerHaptic } from "../services/voiceCommands";

interface Props {
  disabled: boolean;
  onTriggerSOS?: () => void;
}

export const AssistiveActions: React.FC<Props> = ({ disabled, onTriggerSOS }) => {
  const [result, setResult] = useState("क्यामेरा सुरु गरेर विकल्प छान्नुहोस् वा आवाज दिनुहोस्।");
  const [busy, setBusy] = useState(false);
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const [isAutoCurrency, setIsAutoCurrency] = useState(true);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  useEffect(() => {
    cameraApi.getAutoCurrencyMode()
      .then((res) => setIsAutoCurrency(res.enabled))
      .catch(() => {});
  }, []);

  const toggleAutoCurrency = async () => {
    const next = !isAutoCurrency;
    setIsAutoCurrency(next);
    try {
      await cameraApi.setAutoCurrencyMode(next);
      setResult(next ? "स्वतः नोट पहिचान सक्रिय भयो।" : "स्वतः नोट पहिचान बन्द गरियो।");
      triggerHaptic("command");
    } catch {
      setIsAutoCurrency(!next);
    }
  };

  const run = useCallback(async (
    action: () => Promise<{ text?: string; message?: string | null; denomination?: number | null; identity?: string | null; bookmark?: any }>
  ) => {
    setBusy(true);
    try {
      const response = await action();
      const text =
        response.text ||
        response.message ||
        (response.denomination ? `रु ${response.denomination}` : null) ||
        response.identity ||
        (response.bookmark ? `सुरक्षित गरियो: ${response.bookmark.label}` : null) ||
        "निश्चित परिणाम आएन।";
      setResult(text);
      triggerHaptic("success");
    } catch (error) {
      setResult(error instanceof ApiError ? error.message : "अनुरोध पूरा हुन सकेन।");
    } finally {
      setBusy(false);
    }
  }, []);

  // Voice Command Dispatcher
  const handleVoiceCommand = useCallback((match: VoiceCommandMatch) => {
    if (disabled || busy) return;

    if (match.type === "navigation") {
      cameraApi.announceSpeech("बाटो नेभिगेसन मोड सक्रिय छ।", "spatial_navigation", true);
      setResult("बाटो नेभिगेसन मोड सक्रिय छ।");
    } else if (match.type === "sign_language") {
      cameraApi.announceSpeech("सांकेतिक भाषा अनुवादक सक्रिय छ।", "spatial_navigation", true);
      setResult("सांकेतिक भाषा अनुवादक सक्रिय छ।");
    } else if (match.type === "currency") {
      run(() => cameraApi.identifyCurrency());
    } else if (match.type === "bookmark") {
      run(() => cameraApi.saveLocationBookmark());
    } else if (match.type === "scene") {
      run(() => cameraApi.queryScene("के छ?"));
    } else if (match.type === "ocr") {
      run(() => cameraApi.readText());
    } else if (match.type === "bus_route") {
      run(async () => {
        const res = await cameraApi.identifyBusRoute();
        return { message: res.spoken_phrase_ne || (res.matched ? `बस: ${res.destination}` : "बसको बोर्ड फेला परेन।") };
      });
    } else if (match.type === "qr_payment") {
      run(async () => {
        const res = await cameraApi.identifyQrPayment();
        return { message: res.spoken_phrase_ne || (res.detected ? `क्युआर: ${res.merchant_name}` : "क्युआर कोड फेला परेन।") };
      });
    } else if (match.type === "date") {
      run(async () => {
        const res = await cameraApi.getCultureDate();
        if (res.spoken_ne) {
          cameraApi.announceSpeech(res.spoken_ne, "informational", true).catch(() => {});
        }
        return { message: res.spoken_ne || res.formatted_bs };
      });
    } else if (match.type === "mute") {
      cameraApi.stopSpeech().then(() => {
        setResult("अडियो बन्द गरियो।");
      });
    } else if (match.type === "help") {
      const helpMsg = "त्रिनेत्र सहायक: नोट पहिचान गर्न 'पैसा हेर', वरिपरि बुझ्न 'के छ', अक्षर पढ्न 'पढ', ठाउँ सेभ गर्न 'याद राख' भन्नुहोस्।";
      cameraApi.announceSpeech(helpMsg, "critical_hazard", true).then(() => {
        setResult(helpMsg);
      });
    }
  }, [disabled, busy, run]);

  const toggleVoiceControl = async () => {
    if (!voiceCommandService.isSupported()) {
      setVoiceError("तपाईंको उपकरणमा अडियो रेकर्डर वा माइक्रोफोन उपलब्ध छैन।");
      return;
    }

    if (isVoiceActive) {
      voiceCommandService.stop();
      setIsVoiceActive(false);
    } else {
      setVoiceError(null);
      const started = await voiceCommandService.start(
        handleVoiceCommand,
        (listening, err, statusText) => {
          setIsVoiceActive(listening);
          if (err) setVoiceError(err);
          if (statusText) setResult(statusText);
        }
      );
      if (started) {
        setIsVoiceActive(true);
        triggerHaptic("command");
        setResult("आवाज नियन्त्रण सक्रिय: 'पैसा हेर', 'के छ', 'पढ', वा 'याद राख' भन्नुहोस्।");
      }
    }
  };

  useEffect(() => {
    return () => {
      voiceCommandService.stop();
    };
  }, []);

  return (
    <section className="assistive-actions" aria-labelledby="assistive-actions-title">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
        <h2 id="assistive-actions-title" style={{ margin: 0 }}>सहायक कार्यहरू (Voice & On-Demand)</h2>
        <button
          type="button"
          className={`btn ${isVoiceActive ? "btn-primary" : "btn-outline"}`}
          onClick={toggleVoiceControl}
          style={{ fontSize: "0.85rem", padding: "6px 12px" }}
          aria-pressed={isVoiceActive}
          aria-label={isVoiceActive ? "आवाज नियन्त्रण सक्रिय छ, बन्द गर्न क्लिक गर्नुहोस्" : "आवाज नियन्त्रण सुरु गर्नुहोस्"}
        >
          {isVoiceActive ? "🎙️ सुन्दैछ… (Voice ON)" : "🎤 आवाज नियन्त्रण (Voice Control)"}
        </button>
      </div>

      <div className="detection-toolbar">
        <button
          className="btn btn-outline"
          disabled={disabled || busy}
          onClick={() => run(() => cameraApi.queryScene("के छ?"))}
          aria-label="दृश्य विवरण: अगाडि के छ भन्नुहोस्"
        >
          👀 के छ?
        </button>
        <button
          className="btn btn-outline"
          disabled={disabled || busy}
          onClick={() => run(() => cameraApi.identifyCurrency())}
          aria-label="नेपाली मुद्रा पहिचान: नोट चिन्नुहोस्"
        >
          💵 नोट चिन्नुहोस्
        </button>
        <button
          className={`btn ${isAutoCurrency ? "btn-primary" : "btn-outline"}`}
          disabled={disabled || busy}
          onClick={toggleAutoCurrency}
          aria-pressed={isAutoCurrency}
          aria-label={isAutoCurrency ? "स्वतः मुद्रा पहिचान बन्द गर्नुहोस्" : "स्वतः मुद्रा पहिचान सुरु गर्नुहोस्"}
          style={isAutoCurrency ? { borderColor: "rgba(16, 185, 129, 0.8)", boxShadow: "0 0 10px rgba(16, 185, 129, 0.3)" } : undefined}
        >
          {isAutoCurrency ? "⚡ स्वतः नोट: चालू" : "⚡ स्वतः नोट: बन्द"}
        </button>
        <button
          className="btn btn-outline"
          disabled={disabled || busy}
          onClick={() => run(() => cameraApi.readText())}
          aria-label="अक्षर पढ्नुहोस्: साइनबोर्ड वा कागज पढ्नुहोस्"
        >
          📖 पढ्नुहोस्
        </button>
        <button
          className="btn btn-outline"
          disabled={disabled || busy}
          onClick={() => run(async () => {
            const res = await cameraApi.identifyBusRoute();
            return { message: res.spoken_phrase_ne || (res.matched ? `बस: ${res.destination}` : "बसको बोर्ड फेला परेन।") };
          })}
          aria-label="सार्वजनिक बस गन्तव्य र नम्बर पहिचान गर्नुहोस्"
        >
          🚌 बस रुट
        </button>
        <button
          className="btn btn-outline"
          disabled={disabled || busy}
          onClick={() => run(async () => {
            const res = await cameraApi.identifyQrPayment();
            return { message: res.spoken_phrase_ne || (res.detected ? `क्युआर: ${res.merchant_name}` : "क्युआर कोड फेला परेन।") };
          })}
          aria-label="क्युआर भुक्तानी स्ट्यान्डी स्क्यान गर्नुहोस् (Fonepay, eSewa, Khalti)"
        >
          📱 क्युआर भुक्तानी
        </button>
        <button
          className="btn btn-outline"
          disabled={disabled || busy}
          onClick={() => run(async () => {
            const res = await cameraApi.getCultureDate();
            if (res.spoken_ne) {
              cameraApi.announceSpeech(res.spoken_ne, "informational", true).catch(() => {});
            }
            return { message: res.spoken_ne || res.formatted_bs };
          })}
          aria-label="आजको नेपाली मिति (विक्रम संवत्) र बार सुन्नुहोस्"
        >
          📅 मिति (BS)
        </button>
        <button
          className="btn btn-outline"
          disabled={disabled || busy}
          onClick={() => run(() => cameraApi.saveLocationBookmark())}
          aria-label="यो ठाउँ याद राख्नुहोस्: जीपीएस स्थान सुरक्षित गर्नुहोस्"
        >
          📍 ठाउँ याद राख
        </button>
        <button
          className="btn btn-outline"
          disabled={disabled || busy}
          onClick={() => run(() => cameraApi.recognizeFace())}
          aria-label="चिनजानको अनुहार पहिचान गर्नुहोस्"
        >
          👤 अनुहार
        </button>
        {onTriggerSOS && (
          <button
            type="button"
            className="btn btn-outline"
            disabled={disabled || busy}
            onClick={onTriggerSOS}
            style={{ borderColor: "rgba(239, 68, 68, 0.7)", color: "#fca5a5" }}
            aria-label="आपतकालीन पूर्व-सूचना: १० सेकेन्ड काउन्टडाउन सुरु गर्नुहोस्"
          >
            🚨 आपतकालीन (SOS)
          </button>
        )}
      </div>

      {voiceError && (
        <p style={{ color: "var(--accent-pink)", fontSize: "0.8rem", margin: "4px 0" }} role="alert">
          {voiceError}
        </p>
      )}

      {/* Screen Reader Optimized Live Announcement Region */}
      <div aria-live="assertive" className="sr-only" role="status">
        {busy ? "प्रक्रिया चल्दैछ…" : result}
      </div>

      <p className="assistive-result" role="status" aria-live="polite">
        {busy ? "प्रक्रिया हुँदैछ…" : result}
      </p>
    </section>
  );
};
