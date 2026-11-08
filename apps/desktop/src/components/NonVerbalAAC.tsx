import React, { useState, useCallback } from "react";
import { cameraApi } from "../services/cameraApi";
import { triggerHaptic } from "../services/voiceCommands";

interface PhraseItem {
  id: string;
  nepali: string;
  englishMeaning: string;
  category: "travel" | "shop" | "emergency" | "daily";
  priority?: "high" | "normal";
}

const PRESET_PHRASES: PhraseItem[] = [
  // 1. बाटो र यात्रा (Travel & Road)
  {
    id: "t1",
    nepali: "मलाई बाटो काट्न मद्दत गर्नुहोस्।",
    englishMeaning: "Please help me cross the road",
    category: "travel",
    priority: "high",
  },
  {
    id: "t2",
    nepali: "यो गाडी वा बस रत्नपार्क जान्छ?",
    englishMeaning: "Does this vehicle go to Ratna Park?",
    category: "travel",
  },
  {
    id: "t3",
    nepali: "कृपया मलाई अर्को बस स्टपमा ओराल्नुहोस्।",
    englishMeaning: "Please drop me at the next bus stop",
    category: "travel",
  },
  {
    id: "t4",
    nepali: "अगाडि बाटो खुला छ कि रोकिएको छ?",
    englishMeaning: "Is the road ahead clear or blocked?",
    category: "travel",
  },

  // 2. पसल र किनमेल (Shopping & Market)
  {
    id: "s1",
    nepali: "यसको मूल्य कति रुपैयाँ हो?",
    englishMeaning: "How much does this cost?",
    category: "shop",
  },
  {
    id: "s2",
    nepali: "मलाई यो सामान दिनुहोस्।",
    englishMeaning: "Please give me this item",
    category: "shop",
  },
  {
    id: "s3",
    nepali: "मसँग खुद्रा पैसा छैन, डिजिटल भुक्तानी मिल्छ?",
    englishMeaning: "I don't have change, is digital pay ok?",
    category: "shop",
  },
  {
    id: "s4",
    nepali: "रसिद वा बिल पाउन सकिन्छ?",
    englishMeaning: "Can I get a receipt or bill?",
    category: "shop",
  },

  // 3. आपतकालीन र मद्दत (Emergency & Safety)
  {
    id: "e1",
    nepali: "म बोल्न सक्दिन, मलाई तत्काल मद्दत चाहिन्छ।",
    englishMeaning: "I cannot speak, I need urgent assistance",
    category: "emergency",
    priority: "high",
  },
  {
    id: "e2",
    nepali: "म हराएँ, कृपया मलाई नजिकको प्रहरी कार्यालय वा चोक देखाइदिनुहोस्।",
    englishMeaning: "I am lost, please direct me to police/chowk",
    category: "emergency",
    priority: "high",
  },
  {
    id: "e3",
    nepali: "कृपया मेरो परिवारको नम्बरमा फोन गरिदिनुहोस्।",
    englishMeaning: "Please call my family's phone number",
    category: "emergency",
    priority: "high",
  },
  {
    id: "e4",
    nepali: "मलाई स्वास्थ्य समस्या भयो, एम्बुलेन्स बोलाइदिनुहोस्।",
    englishMeaning: "Medical emergency, please call an ambulance",
    category: "emergency",
    priority: "high",
  },

  // 4. दैनिक शिष्टाचार (Daily Courtesy)
  {
    id: "d1",
    nepali: "नमस्ते, आरामै हुनुहुन्छ?",
    englishMeaning: "Namaste, how are you?",
    category: "daily",
  },
  {
    id: "d2",
    nepali: "धेरै धेरै धन्यवाद!",
    englishMeaning: "Thank you very much!",
    category: "daily",
  },
  {
    id: "d3",
    nepali: "हो, ठिक छ।",
    englishMeaning: "Yes, that is fine.",
    category: "daily",
  },
  {
    id: "d4",
    nepali: "होइन, मलाई पर्दैन।",
    englishMeaning: "No, I do not need it.",
    category: "daily",
  },
];

interface Props {
  disabled?: boolean;
}

export const NonVerbalAAC: React.FC<Props> = ({ disabled = false }) => {
  const [activeTab, setActiveTab] = useState<"travel" | "shop" | "emergency" | "daily">("travel");
  const [customText, setCustomText] = useState("");
  const [lastSpoken, setLastSpoken] = useState<string | null>(null);
  const [broadcastMessage, setBroadcastMessage] = useState<string | null>(null);
  const [pocketMode, setPocketMode] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);

  // Speak function with fallback
  const speakText = useCallback(async (text: string) => {
    if (!text.trim()) return;
    setIsSpeaking(true);
    setLastSpoken(text);
    triggerHaptic("command");

    try {
      // 1. Try local Trinetra Piper Neural TTS
      await cameraApi.announceSpeech(text, "high", true);
    } catch {
      // 2. Fallback to browser Web Speech API
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "ne-NP";
        utterance.rate = 0.95;
        window.speechSynthesis.speak(utterance);
      }
    } finally {
      setIsSpeaking(false);
    }
  }, []);

  const handlePhraseClick = (phrase: PhraseItem) => {
    speakText(phrase.nepali);
    // Also show on screen so bystanders in noisy areas can read
    setBroadcastMessage(phrase.nepali);
  };

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (customText.trim()) {
      speakText(customText.trim());
      setBroadcastMessage(customText.trim());
      setCustomText("");
    }
  };

  const togglePocketMode = () => {
    const nextState = !pocketMode;
    setPocketMode(nextState);
    triggerHaptic("success");
    const msg = nextState
      ? "सर्टको खल्ती मोड सक्रिय भयो। क्यामेरा बाहिर फर्काएर खल्तीमा राख्नुहोस्।"
      : "सर्टको खल्ती मोड बन्द गरियो।";
    speakText(msg);
  };

  const filteredPhrases = PRESET_PHRASES.filter((p) => p.category === activeTab);

  return (
    <section
      className={`non-verbal-aac-panel ${pocketMode ? "pocket-mode-active" : ""}`}
      aria-labelledby="aac-title"
      style={{
        backgroundColor: "var(--bg-surface)",
        border: "2px solid var(--border-color)",
        borderRadius: "12px",
        padding: "16px",
        display: "flex",
        flexDirection: "column",
        gap: "14px",
      }}
    >
      {/* Header and Pocket Mode Toggle */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "10px",
          borderBottom: "1px solid var(--border-color)",
          paddingBottom: "10px",
        }}
      >
        <div>
          <h2 id="aac-title" style={{ fontSize: "1.2rem", margin: 0, color: "var(--text-primary)" }}>
            🗣️ आवाजविहीन संवाद सहायक (Non-Verbal AAC Bridge)
          </h2>
          <p style={{ margin: "2px 0 0 0", fontSize: "0.85rem", color: "var(--text-muted)" }}>
            बोल्न नसक्ने व्यक्तिहरूका लागि एक-ट्याप नेपाली बोली र ठूलो दृश्य संवाद कार्ड
          </p>
        </div>

        <button
          type="button"
          onClick={togglePocketMode}
          className={`btn ${pocketMode ? "btn-warning" : "btn-outline"}`}
          style={{
            fontWeight: "bold",
            padding: "8px 14px",
            fontSize: "0.88rem",
            display: "flex",
            alignItems: "center",
            gap: "6px",
          }}
          aria-pressed={pocketMode}
          aria-label="सर्टको खल्ती मोड अन वा अफ गर्नुहोस्"
        >
          {pocketMode ? "📱 खल्ती मोड अन (Pocket ON)" : "👕 खल्ती मोड (Shirt-Pocket Mode)"}
        </button>
      </div>

      {/* Broadcast Display Banner (For Noisy Traffic & Bystanders) */}
      {broadcastMessage && (
        <div
          role="region"
          aria-live="polite"
          style={{
            backgroundColor: "#002147",
            border: "2px solid #d4a017",
            borderRadius: "8px",
            padding: "12px 16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
          }}
        >
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: "0.75rem", color: "#d4a017", textTransform: "uppercase", fontWeight: "bold" }}>
              📢 चालक, पसले वा सहयोगीलाई देखाउनुहोस् (Show to Bystander):
            </div>
            <div style={{ fontSize: "1.3rem", fontWeight: "bold", color: "#ffffff", marginTop: "4px" }}>
              {broadcastMessage}
            </div>
          </div>
          <div style={{ display: "flex", gap: "6px", marginLeft: "12px" }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => speakText(broadcastMessage)}
              disabled={isSpeaking || disabled}
              style={{ padding: "6px 12px", fontSize: "0.85rem" }}
              aria-label="फेरि बोल्नुहोस्"
            >
              🔊 फेरि बोल्नुहोस्
            </button>
            <button
              type="button"
              className="btn btn-outline"
              onClick={() => setBroadcastMessage(null)}
              style={{ padding: "6px 10px", fontSize: "0.85rem" }}
              aria-label="हटाउनुहोस्"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Category Tabs */}
      <div
        role="tablist"
        aria-label="संवाद विधा छान्नुहोस्"
        style={{
          display: "flex",
          gap: "8px",
          flexWrap: "wrap",
        }}
      >
        {[
          { id: "travel", label: "🚦 बाटो र यात्रा (Transit)", icon: "🚶" },
          { id: "shop", label: "🏪 पसल र किनमेल (Market)", icon: "🛒" },
          { id: "emergency", label: "🚨 आपतकालीन मद्दत (Emergency)", icon: "🆘" },
          { id: "daily", label: "💬 दैनिक शिष्टाचार (Daily)", icon: "🙏" },
        ].map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => {
              setActiveTab(tab.id as any);
              triggerHaptic("command");
            }}
            className={`btn ${activeTab === tab.id ? "btn-primary" : "btn-surface"}`}
            style={{
              flex: "1 1 auto",
              padding: "10px 12px",
              fontSize: "0.9rem",
              fontWeight: activeTab === tab.id ? "bold" : "normal",
              border: activeTab === tab.id ? "2px solid var(--border-focus)" : "1px solid var(--border-color)",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Preset Phrases Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          gap: "10px",
        }}
      >
        {filteredPhrases.map((phrase) => {
          const isEmergency = phrase.category === "emergency";
          return (
            <button
              key={phrase.id}
              type="button"
              disabled={disabled}
              onClick={() => handlePhraseClick(phrase)}
              className="btn"
              style={{
                backgroundColor: isEmergency ? "#3e1215" : "var(--bg-surface-elevated)",
                border: isEmergency ? "2px solid #ef4444" : "1.5px solid var(--border-color)",
                color: "#ffffff",
                padding: "14px 16px",
                borderRadius: "8px",
                textAlign: "left",
                display: "flex",
                flexDirection: "column",
                gap: "4px",
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
              aria-label={`${phrase.nepali} - ${phrase.englishMeaning}`}
            >
              <div style={{ fontSize: "1.05rem", fontWeight: "bold", lineHeight: 1.35 }}>
                {phrase.nepali}
              </div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                {phrase.englishMeaning}
              </div>
            </button>
          );
        })}
      </div>

      {/* Custom Nepali Phrase Input */}
      <form
        onSubmit={handleCustomSubmit}
        style={{
          display: "flex",
          gap: "8px",
          marginTop: "6px",
          flexWrap: "wrap",
        }}
      >
        <label htmlFor="custom-aac-input" className="sr-only">
          आफ्नो वाक्य टाइप गर्नुहोस् वा लेख्नुहोस्
        </label>
        <input
          id="custom-aac-input"
          type="text"
          value={customText}
          onChange={(e) => setCustomText(e.target.value)}
          placeholder="यहाँ कुनै पनि वाक्य टाइप गर्नुहोस् (उदा. मलाई ५ मिनेट पर्खनुहोस्)..."
          disabled={disabled}
          style={{
            flex: "1 1 260px",
            backgroundColor: "var(--bg-primary)",
            color: "var(--text-primary)",
            border: "1.5px solid var(--border-color)",
            borderRadius: "6px",
            padding: "10px 14px",
            fontSize: "0.95rem",
          }}
        />
        <button
          type="submit"
          disabled={disabled || !customText.trim() || isSpeaking}
          className="btn btn-primary"
          style={{ padding: "10px 18px", fontWeight: "bold", fontSize: "0.92rem" }}
        >
          🗣️ आवाज निकाल्नुहोस् (Speak)
        </button>
      </form>

      {/* Active Spoken Status Indicator */}
      {lastSpoken && (
        <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", textAlign: "right" }}>
          अन्तिम आवाज: <span style={{ color: "var(--color-success)" }}>"{lastSpoken}"</span>
        </div>
      )}
    </section>
  );
};
