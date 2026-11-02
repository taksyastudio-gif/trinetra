import React from "react";
import { SupportedLanguage } from "../types/api";

interface LanguageSelectorProps {
  language: SupportedLanguage;
  onLanguageChange: (language: SupportedLanguage) => void;
  disabled?: boolean;
  isUpdating?: boolean;
}

export const LanguageSelector: React.FC<LanguageSelectorProps> = ({
  language,
  onLanguageChange,
  disabled = false,
  isUpdating = false,
}) => {
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value as SupportedLanguage;
    if (val === "ne" || val === "en") {
      onLanguageChange(val);
    }
  };

  return (
    <div
      className="language-selector-container"
      role="region"
      aria-label="Speech Language Selection"
    >
      <label htmlFor="trinetra-language-select" className="language-selector-label">
        <span className="language-icon" aria-hidden="true">
          🌐
        </span>
        <span className="language-label-text">
          Language / भाषा:
        </span>
      </label>

      <div className="language-select-wrapper">
        <select
          id="trinetra-language-select"
          className="language-select"
          value={language}
          onChange={handleChange}
          disabled={disabled || isUpdating}
          aria-label="Select speech announcement language. Default is Nepali. Hotkey: Press L to switch."
          title="Switch speech language between Nepali and English (Hotkey: L)"
        >
          <option value="ne">🇳🇵 नेपाली (Nepali - Default)</option>
          <option value="en">🇬🇧 English (English)</option>
        </select>

        {isUpdating && (
          <span
            className="language-updating-indicator"
            aria-live="polite"
            aria-busy="true"
          >
            Syncing...
          </span>
        )}
      </div>

      <span className="language-hotkey-badge" aria-hidden="true">
        Key: L
      </span>

      {/* Screen-reader accessible live announcement for language state change */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        Current speech language is {language === "ne" ? "Nepali" : "English"}.
      </div>
    </div>
  );
};
