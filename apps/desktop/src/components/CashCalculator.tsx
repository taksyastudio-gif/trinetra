import React, { useState, useEffect, useCallback } from "react";
import { cameraApi } from "../services/cameraApi";
import { triggerHaptic } from "../services/voiceCommands";

interface CashCalculatorProps {
  detectedDenomination?: number | null;
  disabled?: boolean;
}

export const CashCalculator: React.FC<CashCalculatorProps> = ({
  detectedDenomination = null,
  disabled = false,
}) => {
  const [cashList, setCashList] = useState<number[]>([]);
  const [itemPrice, setItemPrice] = useState<string>("");
  const [lastAnnouncedDenom, setLastAnnouncedDenom] = useState<number | null>(null);

  // Automatically offer to add newly detected note
  useEffect(() => {
    if (
      detectedDenomination &&
      detectedDenomination > 0 &&
      detectedDenomination !== lastAnnouncedDenom
    ) {
      setLastAnnouncedDenom(detectedDenomination);
    }
  }, [detectedDenomination, lastAnnouncedDenom]);

  const addNote = useCallback((val: number) => {
    setCashList((prev) => [...prev, val]);
    triggerHaptic("command");
  }, []);

  const clearCash = useCallback(() => {
    setCashList([]);
    setItemPrice("");
    triggerHaptic("command");
  }, []);

  const totalCash = cashList.reduce((acc, curr) => acc + curr, 0);
  const cost = parseFloat(itemPrice) || 0;
  const changeDue = Math.max(0, totalCash - cost);

  const broadcastTotal = async () => {
    if (totalCash === 0) return;
    triggerHaptic("success");
    const msg = `मैले जम्मा ${totalCash} रुपैयाँ दिएँ।`;
    try {
      await cameraApi.announceSpeech(msg, "spatial_navigation", true);
    } catch {
      // Fallback
    }
  };

  const broadcastChange = async () => {
    if (totalCash === 0 || cost === 0) return;
    triggerHaptic("success");
    const msg = `${cost} रुपैयाँ कटाई ${changeDue} रुपैयाँ फिर्ता दिनुहोस्।`;
    try {
      await cameraApi.announceSpeech(msg, "spatial_navigation", true);
    } catch {
      // Fallback
    }
  };

  if (disabled) return null;

  return (
    <section
      className="cash-calculator-card"
      aria-label="Nepali Cash Totalizer & Change Calculator"
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
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "1.4rem" }}>💰</span>
          <h2 style={{ fontSize: "1.1rem", margin: 0, fontWeight: 700 }}>
            पैसा हिसाब तथा बाँकी क्यालकुलेटर (Cash Totalizer)
          </h2>
        </div>
        {cashList.length > 0 && (
          <button
            type="button"
            className="btn btn-outline"
            onClick={clearCash}
            style={{ fontSize: "0.8rem", padding: "4px 10px" }}
            aria-label="Clear all counted cash"
          >
            हटाउनुहोस् (Reset)
          </button>
        )}
      </div>

      {/* Safety Notice: Denomination only, not counterfeit authentication */}
      <div
        role="note"
        aria-label="Currency Recognition Boundary"
        style={{
          backgroundColor: "rgba(245, 158, 11, 0.12)",
          border: "1px solid rgba(245, 158, 11, 0.35)",
          borderRadius: "8px",
          padding: "8px 12px",
          marginBottom: "12px",
          fontSize: "0.8rem",
          color: "#fbbf24",
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}
      >
        <span>⚠️</span>
        <span>
          <strong>सूचना:</strong> यो प्रणालीले नोटको दर (Denomination) मात्र चिन्न मद्दत गर्छ। यसले नक्कली वा सक्कली (Counterfeit Authenticity) प्रमाणीकरण गर्दैन।
        </span>
      </div>

      {/* Real-time Hand-held Note Action */}
      {detectedDenomination && detectedDenomination > 0 && (
        <div
          style={{
            backgroundColor: "rgba(16, 185, 129, 0.15)",
            border: "1px solid #10b981",
            borderRadius: "8px",
            padding: "10px 14px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "14px",
          }}
        >
          <div>
            <span style={{ fontSize: "0.85rem", color: "#a7f3d0" }}>
              हातमा भेटिएको नोट:
            </span>
            <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "#10b981" }}>
              रु. {detectedDenomination}
            </div>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => addNote(detectedDenomination)}
            style={{
              backgroundColor: "#10b981",
              borderColor: "#10b981",
              fontSize: "0.9rem",
              padding: "6px 14px",
              fontWeight: 700,
            }}
            aria-label={`Add Rs. ${detectedDenomination} to counted cash`}
          >
            + हिसाबमा जोड्नुहोस् (Add)
          </button>
        </div>
      )}

      {/* Quick Add Buttons for Summit Testing */}
      <div style={{ marginBottom: "12px" }}>
        <span
          style={{
            fontSize: "0.8rem",
            color: "var(--text-muted, #94a3b8)",
            display: "block",
            marginBottom: "6px",
          }}
        >
          द्रुत नोट थप्नुहोस् (Quick Select / Add Denomination):
        </span>
        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
          {[10, 20, 50, 100, 500, 1000].map((val) => (
            <button
              key={val}
              type="button"
              className="btn btn-outline"
              onClick={() => addNote(val)}
              style={{
                fontSize: "0.82rem",
                padding: "4px 8px",
                minWidth: "48px",
                fontWeight: 600,
              }}
              aria-label={`Add Rs. ${val}`}
            >
              रु {val}
            </button>
          ))}
        </div>
      </div>

      {/* Cash Summary & Calculation Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "12px",
          backgroundColor: "rgba(15, 23, 42, 0.6)",
          borderRadius: "8px",
          padding: "12px",
          marginBottom: "12px",
        }}
      >
        <div>
          <span style={{ fontSize: "0.8rem", color: "#94a3b8" }}>
            तपाईंले दिएको जम्मा रकम:
          </span>
          <div
            style={{
              fontSize: "1.4rem",
              fontWeight: 800,
              color: totalCash > 0 ? "#38bdf8" : "#94a3b8",
            }}
          >
            रु. {totalCash}
          </div>
          {cashList.length > 0 && (
            <div style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "2px" }}>
              ({cashList.map((n) => `रु.${n}`).join(" + ")})
            </div>
          )}
        </div>

        <div>
          <label
            htmlFor="item-price-input"
            style={{ fontSize: "0.8rem", color: "#94a3b8", display: "block" }}
          >
            सामान / भाडाको मूल्य (Rs):
          </label>
          <input
            id="item-price-input"
            type="number"
            value={itemPrice}
            onChange={(e) => setItemPrice(e.target.value)}
            placeholder="उदा. ४०"
            style={{
              width: "100%",
              padding: "6px 8px",
              marginTop: "4px",
              backgroundColor: "#1e293b",
              border: "1px solid #475569",
              borderRadius: "6px",
              color: "#ffffff",
              fontSize: "0.95rem",
              fontWeight: 600,
            }}
          />
        </div>
      </div>

      {/* Change Due Display */}
      {cost > 0 && totalCash >= cost && (
        <div
          style={{
            backgroundColor: "rgba(56, 189, 248, 0.15)",
            border: "1px solid #38bdf8",
            borderRadius: "8px",
            padding: "10px 14px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "12px",
          }}
        >
          <div>
            <span style={{ fontSize: "0.85rem", color: "#bae6fd" }}>
              फिर्ता पाउनुपर्ने रकम (Change Due):
            </span>
            <div style={{ fontSize: "1.3rem", fontWeight: 800, color: "#38bdf8" }}>
              रु. {changeDue}
            </div>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            onClick={broadcastChange}
            style={{
              fontSize: "0.85rem",
              padding: "6px 12px",
              backgroundColor: "#0284c7",
              borderColor: "#0284c7",
            }}
            aria-label="Broadcast Change Request: Ask shopkeeper to return change"
          >
            🔊 बाँकी माग्नुहोस्
          </button>
        </div>
      )}

      {/* Direct Spoken Broadcast Buttons */}
      {totalCash > 0 && (
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          <button
            type="button"
            className="btn btn-outline"
            onClick={broadcastTotal}
            style={{ fontSize: "0.85rem", flex: 1, padding: "8px 12px" }}
            aria-label="Broadcast total amount given"
          >
            📢 "मैले {totalCash} रुपैयाँ दिएँ"
          </button>
        </div>
      )}
    </section>
  );
};
