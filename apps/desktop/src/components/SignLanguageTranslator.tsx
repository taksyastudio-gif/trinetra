import React, { useState, useEffect } from "react";
import { cameraApi } from "../services/cameraApi";
import { triggerHaptic } from "../services/voiceCommands";

interface SignGestureInfo {
  detected: boolean;
  gesture_type: string;
  confidence: number;
  message: string;
  symbol: string;
  bounding_box?: number[] | null;
}

interface SignLanguageTranslatorProps {
  currentSign?: SignGestureInfo | null;
  disabled?: boolean;
}

export const SignLanguageTranslator: React.FC<SignLanguageTranslatorProps> = ({
  currentSign = null,
  disabled = false,
}) => {
  const [spokenSubtitle, setSpokenSubtitle] = useState<string>("");
  const [isListening, setIsListening] = useState<boolean>(false);
  const [autoSpeakGestures, setAutoSpeakGestures] = useState<boolean>(false);
  const [dismissedGesture, setDismissedGesture] = useState<string | null>(null);
  const [lastAnnouncedType, setLastAnnouncedType] = useState<string | null>(null);

  // Auto-announce detected gesture if enabled
  useEffect(() => {
    if (
      autoSpeakGestures &&
      currentSign &&
      currentSign.detected &&
      currentSign.gesture_type !== "unknown" &&
      currentSign.gesture_type !== "none" &&
      currentSign.gesture_type !== lastAnnouncedType &&
      currentSign.gesture_type !== dismissedGesture
    ) {
      setLastAnnouncedType(currentSign.gesture_type);
      cameraApi.announceSpeech(currentSign.message, "spatial_navigation", false).catch(() => {});
    }
  }, [currentSign, autoSpeakGestures, lastAnnouncedType, dismissedGesture]);

  // Hearing person speaks -> Real-time Devanagari live subtitle for deaf person
  const startHearingSpeechToSubtitle = async () => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (SpeechRecognition) {
      try {
        const recognition = new SpeechRecognition();
        recognition.lang = "ne-NP";
        recognition.continuous = false;
        recognition.interimResults = true;

        recognition.onstart = () => {
          setIsListening(true);
          triggerHaptic("command");
          setSpokenSubtitle("सुन्दैछ… कृपया नजिकै बोल्नुहोस् (Listening… speak into mic)");
        };

        recognition.onresult = (event: any) => {
          let transcript = "";
          for (let i = event.resultIndex; i < event.results.length; ++i) {
            transcript += event.results[i][0].transcript;
          }
          if (transcript.trim()) {
            setSpokenSubtitle(transcript);
          }
        };

        recognition.onerror = () => {
          setIsListening(false);
          fallbackLocalSTT();
        };

        recognition.onend = () => {
          setIsListening(false);
        };

        recognition.start();
        return;
      } catch {
        // Fallback to local offline STT
      }
    }

    await fallbackLocalSTT();
  };

  const fallbackLocalSTT = async () => {
    try {
      setIsListening(true);
      setSpokenSubtitle("स्थानीय माइक्रोफोन रेकर्डिङ (Offline STT… 3s)...");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunks, { type: "audio/wav" });
        const reader = new FileReader();
        reader.onloadend = async () => {
          const base64Audio = (reader.result as string).split(",")[1];
          try {
            const resp = await cameraApi.transcribeSpeech(base64Audio);
            setSpokenSubtitle(resp.transcript || resp.message || "बोली बुझियो");
          } catch {
            setSpokenSubtitle("अडियो प्रशोधन हुन सकेन");
          } finally {
            setIsListening(false);
          }
        };
        reader.readAsDataURL(blob);
      };

      mediaRecorder.start();
      setTimeout(() => {
        if (mediaRecorder.state === "recording") {
          mediaRecorder.stop();
        }
      }, 3000);
    } catch {
      setIsListening(false);
      setSpokenSubtitle("माइक पहुँच पाइएन (Microphone access denied).");
    }
  };

  // Mute / Deaf person taps common sign to speak aloud
  const speakSignPhrase = async (phrase: string) => {
    triggerHaptic("success");
    try {
      await cameraApi.announceSpeech(phrase, "spatial_navigation", true);
    } catch {
      // Fallback
    }
  };

  if (disabled) return null;

  const isVisibleGesture =
    currentSign &&
    currentSign.detected &&
    currentSign.gesture_type !== dismissedGesture;

  return (
    <section
      className="sign-translator-card"
      aria-label="Sign Language & Two-Way Deaf/Mute Interpreter"
      style={{
        backgroundColor: "var(--card-bg, #1e293b)",
        border: "1px solid var(--border-color, #334155)",
        borderRadius: "12px",
        padding: "16px",
        marginTop: "16px",
        boxShadow: "0 4px 12px rgba(0, 0, 0, 0.2)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "12px",
          flexWrap: "wrap",
          gap: "8px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "1.4rem" }}>🤟</span>
          <h2 style={{ fontSize: "1.1rem", margin: 0, fontWeight: 700 }}>
            सांकेतिक भाषा तथा दोहोरो संवाद (Sign Language & Subtitle Bridge)
          </h2>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <label style={{ fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "4px", color: "#94a3b8", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={autoSpeakGestures}
              onChange={(e) => setAutoSpeakGestures(e.target.checked)}
            />
            स्वतः आवाज (Auto TTS)
          </label>
          <span
            style={{
              backgroundColor: "rgba(56, 189, 248, 0.2)",
              color: "#38bdf8",
              padding: "3px 10px",
              borderRadius: "12px",
              fontSize: "0.75rem",
              fontWeight: 600,
            }}
          >
            Bounded Prototype (5 Words)
          </span>
        </div>
      </div>

      {/* Real-time Hand Sign Live Detection Alert with Cancel/Dismiss Option */}
      {isVisibleGesture && (
        <div
          style={{
            backgroundColor: currentSign.gesture_type === "help" || currentSign.gesture_type === "sick"
              ? "rgba(239, 68, 68, 0.15)"
              : "rgba(168, 85, 247, 0.15)",
            border: `2px solid ${
              currentSign.gesture_type === "help" || currentSign.gesture_type === "sick"
                ? "#ef4444"
                : "#a855f7"
            }`,
            borderRadius: "8px",
            padding: "12px",
            marginBottom: "14px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
          }}
          role="status"
          aria-live="polite"
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <span style={{ fontSize: "2rem" }}>{currentSign.symbol}</span>
            <div>
              <span style={{ fontSize: "0.8rem", color: "#d8b4fe", fontWeight: 700 }}>
                क्यामेरामा संकेत भेटियो ({currentSign.gesture_type.toUpperCase()} • {Math.round(currentSign.confidence * 100)}%):
              </span>
              <div style={{ fontSize: "1.05rem", fontWeight: 800, color: "#ffffff", marginTop: "2px" }}>
                {currentSign.message}
              </div>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            style={{ fontSize: "0.75rem", padding: "4px 8px", color: "#cbd5e1" }}
            onClick={() => setDismissedGesture(currentSign.gesture_type)}
            title="रद्द गर्नुहोस् (Dismiss)"
          >
            हटाउनुहोस् ✕
          </button>
        </div>
      )}

      {/* Subtitle Display for Deaf Users */}
      <div
        style={{
          backgroundColor: "#0f172a",
          border: "1px solid #334155",
          borderRadius: "8px",
          padding: "12px",
          marginBottom: "14px",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "8px",
          }}
        >
          <span style={{ fontSize: "0.82rem", color: "#94a3b8", fontWeight: 600 }}>
            👂 सुन्ने व्यक्तिले बोलेको शब्द (Live Subtitle for Deaf User):
          </span>
          <button
            type="button"
            className={`btn btn-sm ${isListening ? "btn-primary" : "btn-outline"}`}
            onClick={startHearingSpeechToSubtitle}
            disabled={isListening}
            style={{ fontSize: "0.78rem", padding: "4px 10px" }}
            aria-label="Toggle microphone for live subtitles"
          >
            {isListening ? "🎙️ सुन्दैछ (Listening…)" : "🎤 माइक सुरु (Live Subtitle)"}
          </button>
        </div>
        <div
          style={{
            minHeight: "44px",
            fontSize: "1.1rem",
            fontWeight: 700,
            color: spokenSubtitle ? "#38bdf8" : "#64748b",
            lineHeight: 1.4,
          }}
        >
          {spokenSubtitle || "माइक थिचेर बोल्नुहोस् — यहाँ ठूलो अक्षरमा देखिनेछ। (Press mic to display text)"}
        </div>
      </div>

      {/* Quick Sign-to-Speech Tap Board for Mute / Speech-Impaired User */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
          <span style={{ fontSize: "0.82rem", color: "#94a3b8", fontWeight: 600 }}>
            हातको इशारा वा द्रुत जवाफ बोल्नुहोस् (Tap Sign to Speak Aloud):
          </span>
          <span style={{ fontSize: "0.72rem", color: "#64748b" }}>
            Honest Rule: 5 Bounded Essential Vocabulary
          </span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "8px" }}>
          <button
            type="button"
            className="btn btn-outline"
            onClick={() => speakSignPhrase("मलाई मद्दत वा सहयोग चाहियो!")}
            style={{ fontSize: "0.85rem", padding: "8px", textAlign: "left", display: "flex", alignItems: "center", gap: "6px", borderColor: "rgba(239, 68, 68, 0.4)" }}
          >
            <span>🆘</span>
            <span>मद्दत (Help)</span>
          </button>

          <button
            type="button"
            className="btn btn-outline"
            onClick={() => speakSignPhrase("मलाई पिउने पानी चाहियो।")}
            style={{ fontSize: "0.85rem", padding: "8px", textAlign: "left", display: "flex", alignItems: "center", gap: "6px", borderColor: "rgba(56, 189, 248, 0.4)" }}
          >
            <span>💧</span>
            <span>पानी (Water)</span>
          </button>

          <button
            type="button"
            className="btn btn-outline"
            onClick={() => speakSignPhrase("मलाई खाना वा खाजा चाहियो।")}
            style={{ fontSize: "0.85rem", padding: "8px", textAlign: "left", display: "flex", alignItems: "center", gap: "6px", borderColor: "rgba(234, 179, 8, 0.4)" }}
          >
            <span>🍲</span>
            <span>खाना (Food)</span>
          </button>

          <button
            type="button"
            className="btn btn-outline"
            onClick={() => speakSignPhrase("धन्यवाद!")}
            style={{ fontSize: "0.85rem", padding: "8px", textAlign: "left", display: "flex", alignItems: "center", gap: "6px" }}
          >
            <span>🤝</span>
            <span>धन्यवाद (Thanks)</span>
          </button>

          <button
            type="button"
            className="btn btn-outline"
            onClick={() => speakSignPhrase("म बिरामी छु, मलाई सन्चो छैन।")}
            style={{ fontSize: "0.85rem", padding: "8px", textAlign: "left", display: "flex", alignItems: "center", gap: "6px", borderColor: "rgba(244, 63, 94, 0.4)" }}
          >
            <span>🤒</span>
            <span>बिरामी (Sick)</span>
          </button>

          <button
            type="button"
            className="btn btn-outline"
            onClick={() => speakSignPhrase("नमस्ते!")}
            style={{ fontSize: "0.85rem", padding: "8px", textAlign: "left", display: "flex", alignItems: "center", gap: "6px" }}
          >
            <span>🙏</span>
            <span>नमस्ते (Namaste)</span>
          </button>

          <button
            type="button"
            className="btn btn-outline"
            onClick={() => speakSignPhrase("कृपया एकछिन रोकिनुहोस्।")}
            style={{ fontSize: "0.85rem", padding: "8px", textAlign: "left", display: "flex", alignItems: "center", gap: "6px" }}
          >
            <span>✋</span>
            <span>रोकिनुहोस् (Stop)</span>
          </button>

          <button
            type="button"
            className="btn btn-outline"
            onClick={() => speakSignPhrase("हुन्छ, ठीक छ।")}
            style={{ fontSize: "0.85rem", padding: "8px", textAlign: "left", display: "flex", alignItems: "center", gap: "6px" }}
          >
            <span>👍</span>
            <span>हुन्छ (OK)</span>
          </button>
        </div>
      </div>
    </section>
  );
};
