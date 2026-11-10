import { useEffect, useRef, useState } from "react";
import {
  formatBytes,
  type DetectedOS,
  type LatestReleaseInfo,
} from "../services/releases";
import {
  animateButtonBounce,
  animateRadarPulse,
  animateTabTransition,
} from "../utils/animations";
import { FIRMWARE_SOURCE_URL, RELEASES_PAGE_URL } from "../config";

export type PlatformKey = "android" | "ios" | "windows" | "firmware";

interface DownloadShowcaseProps {
  detectedOS: DetectedOS;
  release: LatestReleaseInfo | null;
  releaseLoading: boolean;
  lang: "en" | "ne";
  t: any;
  onAnnounce: (msg: string) => void;
}

export function DownloadShowcase({
  detectedOS,
  release,
  lang,
  t,
  onAnnounce,
}: DownloadShowcaseProps) {
  // Determine default platform: prioritizing phone browsers first
  const getInitialPlatform = (): PlatformKey => {
    if (detectedOS === "Android") return "android";
    if (detectedOS === "iOS") return "ios";
    if (detectedOS === "Windows") return "windows";
    return "android"; // default mobile-first
  };

  const [activePlatform, setActivePlatform] = useState<PlatformKey>(getInitialPlatform);
  const [copiedWinget, setCopiedWinget] = useState(false);
  const [copiedSha, setCopiedSha] = useState<string | null>(null);
  const [simulatedVoice, setSimulatedVoice] = useState<string>("रू. १०० (एक सय रुपैयाँ)");
  const [isSimulating, setIsSimulating] = useState(false);

  const panelRef = useRef<HTMLDivElement>(null);
  const radarRingsRef = useRef<HTMLDivElement>(null);

  // Trigger anime.js tab transition whenever activePlatform changes
  useEffect(() => {
    if (panelRef.current) {
      animateTabTransition(panelRef.current);
    }
  }, [activePlatform]);

  // Trigger radar pulse animation for the interactive phone simulation
  useEffect(() => {
    if (radarRingsRef.current) {
      const rings = radarRingsRef.current.querySelectorAll(".radar-ring");
      const anim = animateRadarPulse(Array.from(rings) as HTMLElement[]);
      return () => {
        if (anim && typeof (anim as any).pause === "function") {
          (anim as any).pause();
        }
      };
    }
  }, []);

  const handleTabClick = (platform: PlatformKey, e: React.MouseEvent<HTMLButtonElement>) => {
    animateButtonBounce(e.currentTarget);
    setActivePlatform(platform);
    const label =
      platform === "android"
        ? t.downloads.tabAndroid
        : platform === "ios"
        ? t.downloads.tabIOS
        : platform === "windows"
        ? t.downloads.tabWindows
        : t.downloads.tabFirmware;
    onAnnounce(`${label} selected`);
  };

  const copyWingetCommand = async (e: React.MouseEvent<HTMLButtonElement>) => {
    animateButtonBounce(e.currentTarget);
    const cmd = "winget install TaksyaStudio.Trinetra";
    try {
      await navigator.clipboard.writeText(cmd);
      setCopiedWinget(true);
      onAnnounce(t.downloads.copiedWinget || "Winget command copied");
      setTimeout(() => setCopiedWinget(false), 3000);
    } catch {
      // ignore
    }
  };

  const copySha = async (sha: string, e: React.MouseEvent<HTMLButtonElement>) => {
    animateButtonBounce(e.currentTarget);
    try {
      await navigator.clipboard.writeText(sha);
      setCopiedSha(sha);
      onAnnounce(t.downloads.copiedChecksum || "Checksum copied");
      setTimeout(() => setCopiedSha(null), 3000);
    } catch {
      // ignore
    }
  };

  const triggerPhoneSimulation = (e: React.MouseEvent) => {
    animateButtonBounce(e.currentTarget as HTMLElement);
    setIsSimulating(true);
    const phrases =
      lang === "ne"
        ? [
            "रू. १०० (एक सय रुपैयाँ) — असली नोट",
            "बाटो सफा छ, ५ मिटर अगाडि कुनै अवरोध छैन।",
            "अगाडिको व्यक्तिले नमस्ते संकेत गर्नुभयो।",
            "रू. ५०० (पाँच सय रुपैयाँ)",
          ]
        : [
            "NPR 100 Note Verified Authentic",
            "Path clear. 5 meters safe walking buffer.",
            "Namaste gesture detected in front of camera.",
            "NPR 500 Note Detected",
          ];
    const randomPhrase = phrases[Math.floor(Math.random() * phrases.length)];
    setSimulatedVoice(randomPhrase);
    onAnnounce(randomPhrase);
    setTimeout(() => setIsSimulating(false), 1200);
  };

  // Pre-configured URLs
  const apkDownloadUrl =
    release?.androidAsset?.downloadUrl ||
    "https://github.com/taksyastudio-gif/trinetra/releases/latest/download/Trinetra-v0.2.0-Android.apk";
  const apkSize = release?.androidAsset?.size
    ? formatBytes(release.androidAsset.size)
    : "28.0 MB";

  const windowsDownloadUrl =
    release?.windowsAsset?.downloadUrl ||
    "https://github.com/taksyastudio-gif/trinetra/releases/latest/download/Trinetra-v0.2.0-Setup.exe";
  const windowsSize = release?.windowsAsset?.size
    ? formatBytes(release.windowsAsset.size)
    : "454.5 MB";

  return (
    <div className="download-hub-wrapper">
      {/* Platform Segmented Tabs */}
      <div
        className="platform-tabs"
        role="tablist"
        aria-label="Operating system selection"
      >
        {/* Android Tab */}
        <button
          type="button"
          role="tab"
          id="tab-android"
          aria-selected={activePlatform === "android"}
          aria-controls="panel-android"
          tabIndex={activePlatform === "android" ? 0 : -1}
          className={`platform-tab-btn ${activePlatform === "android" ? "active" : ""}`}
          onClick={(e) => handleTabClick("android", e)}
        >
          <svg
            className="tab-icon"
            viewBox="0 0 24 24"
            width="20"
            height="20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M17.523 15.3414c-.5511 0-.9993-.4486-.9993-.9997s.4482-.9993.9993-.9993c.551 0 .9993.4482.9993.9993.0001.5511-.4483.9997-.9993.9997m-11.046 0c-.5511 0-.9993-.4486-.9993-.9997s.4482-.9993.9993-.9993c.5511 0 .9993.4482.9993.9993 0 .5511-.4482.9997-.9993.9997m11.4045-6.02l1.9973-3.4592a.416.416 0 00-.1521-.5676.416.416 0 00-.5676.1521l-2.0223 3.503C15.5902 8.414 13.8533 8.125 12 8.125s-3.5902.289-5.1368.8297L4.8409 5.4517a.4161.4161 0 00-.5677-.1521.4157.4157 0 00-.1521.5676l1.9973 3.4592C2.6889 11.1867.3432 14.6589 0 18.761h24c-.3432-4.1021-2.6889-7.5743-6.1185-9.4396" />
          </svg>
          <span className="tab-label">{t.downloads.tabAndroid || "Android Mobile"}</span>
          {detectedOS === "Android" && (
            <span className="tab-badge" aria-label="Detected device">
              ● {lang === "ne" ? "तपाईंको फोन" : "Your Device"}
            </span>
          )}
        </button>

        {/* iOS Tab */}
        <button
          type="button"
          role="tab"
          id="tab-ios"
          aria-selected={activePlatform === "ios"}
          aria-controls="panel-ios"
          tabIndex={activePlatform === "ios" ? 0 : -1}
          className={`platform-tab-btn ${activePlatform === "ios" ? "active" : ""}`}
          onClick={(e) => handleTabClick("ios", e)}
        >
          <svg
            className="tab-icon"
            viewBox="0 0 24 24"
            width="20"
            height="20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M15.97 6.38c.62-.75 1.04-1.8 0.93-2.85-.9.04-1.99.6-2.63 1.35-.57.66-.97 1.72-.83 2.74 1.01.08 2.04-.52 2.53-1.24z" />
          </svg>
          <span className="tab-label">{t.downloads.tabIOS || "Apple iOS"}</span>
          {detectedOS === "iOS" && (
            <span className="tab-badge" aria-label="Detected device">
              ● {lang === "ne" ? "तपाईंको फोन" : "Your Device"}
            </span>
          )}
        </button>

        {/* Windows Tab */}
        <button
          type="button"
          role="tab"
          id="tab-windows"
          aria-selected={activePlatform === "windows"}
          aria-controls="panel-windows"
          tabIndex={activePlatform === "windows" ? 0 : -1}
          className={`platform-tab-btn ${activePlatform === "windows" ? "active" : ""}`}
          onClick={(e) => handleTabClick("windows", e)}
        >
          <svg
            className="tab-icon"
            viewBox="0 0 24 24"
            width="20"
            height="20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M0 3.449L9.75 2.1v9.451H0m10.949-9.602L24 0v11.4h-13.051M0 12.6h9.75v9.451L0 20.699M10.949 12.6H24V24l-13.051-1.951" />
          </svg>
          <span className="tab-label">{t.downloads.tabWindows || "Windows PC"}</span>
          {detectedOS === "Windows" && (
            <span className="tab-badge" aria-label="Detected device">
              ● {lang === "ne" ? "तपाईंको पीसी" : "Your Device"}
            </span>
          )}
        </button>

        {/* ESP32 Firmware Tab */}
        <button
          type="button"
          role="tab"
          id="tab-firmware"
          aria-selected={activePlatform === "firmware"}
          aria-controls="panel-firmware"
          tabIndex={activePlatform === "firmware" ? 0 : -1}
          className={`platform-tab-btn ${activePlatform === "firmware" ? "active" : ""}`}
          onClick={(e) => handleTabClick("firmware", e)}
        >
          <svg
            className="tab-icon"
            viewBox="0 0 24 24"
            width="20"
            height="20"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <rect x="4" y="4" width="16" height="16" rx="2" />
            <rect x="9" y="9" width="6" height="6" />
            <line x1="9" y1="1" x2="9" y2="4" />
            <line x1="15" y1="1" x2="15" y2="4" />
            <line x1="9" y1="20" x2="9" y2="23" />
            <line x1="15" y1="20" x2="15" y2="23" />
            <line x1="20" y1="9" x2="23" y2="9" />
            <line x1="20" y1="14" x2="23" y2="14" />
            <line x1="1" y1="9" x2="4" y2="9" />
            <line x1="1" y1="14" x2="4" y2="14" />
          </svg>
          <span className="tab-label">{t.downloads.tabFirmware || "ESP32-CAM"}</span>
        </button>
      </div>

      {/* Main Showcase Grid */}
      <div className="download-content-grid" ref={panelRef}>
        {/* Left Column: Active Platform Information */}
        <div className="download-platform-panel">
          {/* ANDROID PANEL */}
          {activePlatform === "android" && (
            <div
              id="panel-android"
              role="tabpanel"
              aria-labelledby="tab-android"
              className="platform-card"
            >
              <div className="card-platform-header">
                <div className="platform-tag">
                  <span>🤖</span>
                  <strong>{lang === "ne" ? "एन्ड्रोइड फोन विशेष" : "Android Phone Optimized"}</strong>
                </div>
                <h3 className="platform-title">{t.downloads.android.title}</h3>
                <p className="platform-desc">{t.downloads.android.subtitle}</p>
              </div>

              {/* Action Buttons with 48px+ touch targets */}
              <div className="cta-action-group">
                <a
                  href={apkDownloadUrl}
                  className="btn btn-primary btn-large download-action-btn"
                  download
                  onClick={(e) => animateButtonBounce(e.currentTarget)}
                >
                  <svg
                    viewBox="0 0 24 24"
                    width="22"
                    height="22"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="7 10 12 15 17 10" />
                    <line x1="12" y1="15" x2="12" y2="3" />
                  </svg>
                  <div className="btn-text-block">
                    <span className="btn-main-label">
                      {t.downloads.downloadApk || "Download Android APK"}
                    </span>
                    <span className="btn-sub-label">
                      v0.2.0 • {apkSize} • 100% Offline
                    </span>
                  </div>
                </a>

                <a
                  href="#how-it-works"
                  className="btn btn-secondary btn-large"
                  onClick={(e) => animateButtonBounce(e.currentTarget)}
                >
                  <svg
                    viewBox="0 0 24 24"
                    width="20"
                    height="20"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    aria-hidden="true"
                  >
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                  <span>{t.downloads.launchPwa || "Interactive Web PWA"}</span>
                </a>
              </div>

              {/* Step-by-Step Android Guide */}
              <div className="guide-stepper">
                <h4 className="guide-title">{t.downloads.android.guideTitle}</h4>
                <ol className="steps-list">
                  <li className="step-item">
                    <span className="step-num">1</span>
                    <div className="step-body">
                      <strong>{lang === "ne" ? "APK डाउनलोड गर्नुहोस्" : "Download APK"}</strong>
                      <p>{t.downloads.android.step1}</p>
                    </div>
                  </li>
                  <li className="step-item">
                    <span className="step-num">2</span>
                    <div className="step-body">
                      <strong>{lang === "ne" ? "स्थापना अनुमति दिनुहोस्" : "Enable Install from Source"}</strong>
                      <p>{t.downloads.android.step2}</p>
                    </div>
                  </li>
                  <li className="step-item">
                    <span className="step-num">3</span>
                    <div className="step-body">
                      <strong>{lang === "ne" ? "क्यामेरा र माइक अनुमति" : "Grant Sensory Permissions"}</strong>
                      <p>{t.downloads.android.step3}</p>
                    </div>
                  </li>
                </ol>
              </div>

              {/* Feature Pills */}
              <div className="feature-pills-row">
                <span className="feature-pill">✓ {lang === "ne" ? "नेपाली नोट पहिचान" : "NPR Banknotes"}</span>
                <span className="feature-pill">✓ {lang === "ne" ? "आवाज निर्देशन" : "Spoken Guidance"}</span>
                <span className="feature-pill">✓ {lang === "ne" ? "शून्य इन्टरनेट" : "Zero Cloud Latency"}</span>
              </div>
            </div>
          )}

          {/* IOS PANEL */}
          {activePlatform === "ios" && (
            <div
              id="panel-ios"
              role="tabpanel"
              aria-labelledby="tab-ios"
              className="platform-card"
            >
              <div className="card-platform-header">
                <div className="platform-tag">
                  <span>🍎</span>
                  <strong>{lang === "ne" ? "एप्पल सफारी वेब एप" : "Apple iOS Safari Web App"}</strong>
                </div>
                <h3 className="platform-title">{t.downloads.ios.title}</h3>
                <p className="platform-desc">{t.downloads.ios.subtitle}</p>
              </div>

              {/* Action Buttons */}
              <div className="cta-action-group">
                <a
                  href="#how-it-works"
                  className="btn btn-primary btn-large download-action-btn"
                  onClick={(e) => animateButtonBounce(e.currentTarget)}
                >
                  <svg
                    viewBox="0 0 24 24"
                    width="22"
                    height="22"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    aria-hidden="true"
                  >
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                  <div className="btn-text-block">
                    <span className="btn-main-label">
                      {t.downloads.launchPwa || "Launch Web App in Safari"}
                    </span>
                    <span className="btn-sub-label">
                      {lang === "ne" ? "सफारीमा सीधै खोल्नुहोस्" : "Zero Install Required • VoiceOver Ready"}
                    </span>
                  </div>
                </a>

                <a
                  href="https://github.com/taksyastudio-gif/trinetra/issues"
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-secondary btn-large"
                  onClick={(e) => animateButtonBounce(e.currentTarget)}
                >
                  <svg
                    viewBox="0 0 24 24"
                    width="20"
                    height="20"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    aria-hidden="true"
                  >
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                  <span>{lang === "ne" ? "टेस्टफ्लाइट बेटा अनुरोध" : "Request TestFlight Beta"}</span>
                </a>
              </div>

              {/* Apple Safari 3-Step Visual Guide */}
              <div className="guide-stepper">
                <h4 className="guide-title">{t.downloads.ios.guideTitle}</h4>
                <ol className="steps-list">
                  <li className="step-item">
                    <span className="step-num">1</span>
                    <div className="step-body">
                      <strong>{lang === "ne" ? "सफारी सेयर बटन" : "Tap Safari Share Icon"}</strong>
                      <p>{t.downloads.ios.step1}</p>
                    </div>
                  </li>
                  <li className="step-item">
                    <span className="step-num">2</span>
                    <div className="step-body">
                      <strong>{lang === "ne" ? "होम स्क्रिनमा थप्नुहोस्" : "Add to Home Screen"}</strong>
                      <p>{t.downloads.ios.step2}</p>
                    </div>
                  </li>
                  <li className="step-item">
                    <span className="step-num">3</span>
                    <div className="step-body">
                      <strong>{lang === "ne" ? "पूरा स्क्रिनमा चलाउनुहोस्" : "Launch Fullscreen"}</strong>
                      <p>{t.downloads.ios.step3}</p>
                    </div>
                  </li>
                </ol>
              </div>

              {/* Feature Pills */}
              <div className="feature-pills-row">
                <span className="feature-pill">✓ Apple VoiceOver</span>
                <span className="feature-pill">✓ WebRTC Realtime Camera</span>
                <span className="feature-pill">✓ Fullscreen PWA</span>
              </div>
            </div>
          )}

          {/* WINDOWS PANEL */}
          {activePlatform === "windows" && (
            <div
              id="panel-windows"
              role="tabpanel"
              aria-labelledby="tab-windows"
              className="platform-card"
            >
              <div className="card-platform-header">
                <div className="platform-tag">
                  <span>💻</span>
                  <strong>{lang === "ne" ? "विन्डोज ६४-बिट" : "Windows 64-Bit Desktop"}</strong>
                </div>
                <h3 className="platform-title">{t.downloads.windows.title}</h3>
                <p className="platform-desc">{t.downloads.windows.subtitle}</p>
              </div>

              {/* Action Buttons */}
              <div className="cta-action-group">
                <a
                  href={windowsDownloadUrl}
                  className="btn btn-primary btn-large download-action-btn"
                  download
                  onClick={(e) => animateButtonBounce(e.currentTarget)}
                >
                  <svg
                    viewBox="0 0 24 24"
                    width="22"
                    height="22"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="7 10 12 15 17 10" />
                    <line x1="12" y1="15" x2="12" y2="3" />
                  </svg>
                  <div className="btn-text-block">
                    <span className="btn-main-label">
                      {t.downloads.windows.downloadButton}
                    </span>
                    <span className="btn-sub-label">
                      v0.2.0 • {windowsSize} • Embedded Python Engine
                    </span>
                  </div>
                </a>

                <a
                  href={RELEASES_PAGE_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-secondary btn-large"
                  onClick={(e) => animateButtonBounce(e.currentTarget)}
                >
                  <svg
                    viewBox="0 0 24 24"
                    width="20"
                    height="20"
                    fill="currentColor"
                    aria-hidden="true"
                  >
                    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
                  </svg>
                  <span>{t.downloads.viewAllReleases}</span>
                </a>
              </div>

              {/* Windows Package Manager (winget) Command Snippet */}
              <div className="terminal-box">
                <div className="terminal-header">
                  <div className="terminal-dots" aria-hidden="true">
                    <span className="dot red" />
                    <span className="dot yellow" />
                    <span className="dot green" />
                  </div>
                  <span className="terminal-title">
                    {t.downloads.wingetTitle || "Windows Package Manager (winget)"}
                  </span>
                </div>
                <div className="terminal-content">
                  <code>winget install TaksyaStudio.Trinetra</code>
                  <button
                    type="button"
                    className="btn btn-sm btn-terminal-copy"
                    onClick={copyWingetCommand}
                    aria-label="Copy winget install command"
                  >
                    {copiedWinget ? (
                      <span className="text-success">✓ {t.downloads.copiedWinget || "Copied!"}</span>
                    ) : (
                      <span>📋 {t.downloads.copyWinget || "Copy"}</span>
                    )}
                  </button>
                </div>
              </div>

              {/* Requirements & SmartScreen note */}
              <div className="system-note">
                <p>
                  <strong>{lang === "ne" ? "प्रणाली आवश्यकता:" : "Requirements:"}</strong>{" "}
                  {t.downloads.windows.requirements}
                </p>
                <p className="smartscreen-tip">
                  💡 {lang === "ne"
                    ? "पहिलो पटक खोल्दा Windows SmartScreen आएमा 'More info' थिचेर 'Run anyway' रोज्नुहोस्।"
                    : "On first launch, if Windows SmartScreen appears: Click 'More info' → 'Run anyway'."}
                </p>
              </div>
            </div>
          )}

          {/* ESP32 FIRMWARE PANEL */}
          {activePlatform === "firmware" && (
            <div
              id="panel-firmware"
              role="tabpanel"
              aria-labelledby="tab-firmware"
              className="platform-card"
            >
              <div className="card-platform-header">
                <div className="platform-tag">
                  <span>📷</span>
                  <strong>{lang === "ne" ? "चश्मा क्यामेरा फर्मवेयर" : "Assistive Glasses Firmware"}</strong>
                </div>
                <h3 className="platform-title">{t.downloads.firmware.title}</h3>
                <p className="platform-desc">{t.downloads.firmware.subtitle}</p>
              </div>

              <div className="cta-action-group">
                <a
                  href={FIRMWARE_SOURCE_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-primary btn-large download-action-btn"
                  onClick={(e) => animateButtonBounce(e.currentTarget)}
                >
                  <svg
                    viewBox="0 0 24 24"
                    width="22"
                    height="22"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    aria-hidden="true"
                  >
                    <polyline points="16 18 22 12 16 6" />
                    <polyline points="8 6 2 12 8 18" />
                  </svg>
                  <div className="btn-text-block">
                    <span className="btn-main-label">{t.downloads.firmware.actionButton}</span>
                    <span className="btn-sub-label">Arduino IDE • OV2640 Driver • Wi-Fi Stream</span>
                  </div>
                </a>
              </div>

              <div className="firmware-spec-box">
                <h4 className="guide-title">{lang === "ne" ? "प्राविधिक विवरण:" : "Hardware Setup:"}</h4>
                <ul className="spec-bullets">
                  <li><strong>Module:</strong> AI-Thinker ESP32-CAM (OV2640 lens)</li>
                  <li><strong>Stream Protocol:</strong> MJPEG over HTTP (Port 81)</li>
                  <li><strong>Baud Rate:</strong> 115200 bps</li>
                  <li><strong>Power:</strong> 5V 2A micro USB or compact lithium pouch cell</li>
                </ul>
                <p className="firmware-instructions-text">{t.downloads.firmware.instructions}</p>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Interactive Phone Simulator with anime.js Radar */}
        <div className="phone-simulator-column">
          <div className="phone-device-container">
            {/* Pulsing Sonar Waves around phone top */}
            <div className="radar-emitter" ref={radarRingsRef} aria-hidden="true">
              <span className="radar-ring" />
              <span className="radar-ring" />
              <span className="radar-ring" />
            </div>

            {/* Smartphone Chassis */}
            <div
              className={`smartphone-mockup ${isSimulating ? "animating" : ""}`}
              onClick={triggerPhoneSimulation}
              role="button"
              tabIndex={0}
              aria-label="Interactive Trinetra camera simulation. Click to test spoken guidance."
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  triggerPhoneSimulation(e as any);
                }
              }}
            >
              <div className="phone-notch">
                <span className="speaker" />
                <span className="camera" />
              </div>

              {/* Screen Content */}
              <div className="phone-screen">
                {/* Viewfinder Header */}
                <div className="screen-header">
                  <div className="live-indicator">
                    <span className="pulse-dot" />
                    <span>TRINETRA NANO • LIVE</span>
                  </div>
                  <span className="fps-counter">30 FPS</span>
                </div>

                {/* Camera Viewfinder with Object Detection Box */}
                <div className="camera-viewfinder">
                  <div className="detection-box">
                    <span className="corner tl" />
                    <span className="corner tr" />
                    <span className="corner bl" />
                    <span className="corner br" />
                    <div className="detection-label">
                      <span>🇳🇵 रू. १०० (NPR 100)</span>
                      <span className="confidence">98.4%</span>
                    </div>
                  </div>

                  {/* Ground Surface Scan Lines */}
                  <div className="ground-scan-grid" aria-hidden="true">
                    <div className="scan-line" />
                  </div>
                </div>

                {/* Spoken Voice Subtitle Bubble */}
                <div className="spoken-speech-bubble">
                  <div className="voice-wave-icon" aria-hidden="true">
                    <span className="bar" />
                    <span className="bar" />
                    <span className="bar" />
                  </div>
                  <div className="spoken-text-content">
                    <span className="speech-prefix">
                      {lang === "ne" ? "आवाज निर्देशन:" : "Spoken Audio Guidance:"}
                    </span>
                    <strong className="speech-phrase">{simulatedVoice}</strong>
                  </div>
                </div>

                {/* Interactive Phone Bottom Action */}
                <div className="phone-footer-hint">
                  <small>
                    {lang === "ne"
                      ? "👆 परीक्षण गर्न फोन स्क्रिनमा ट्याप गर्नुहोस्"
                      : "👆 Tap phone screen to simulate voice walkthrough"}
                  </small>
                </div>
              </div>
            </div>

            {/* Quick Checksum / Verification widget */}
            {release?.windowsAsset?.checksum && (
              <div className="checksum-quick-card">
                <div className="checksum-meta">
                  <span className="checksum-label">SHA-256 Provenance</span>
                  <code className="checksum-value">
                    {release.windowsAsset.checksum.slice(0, 16)}...
                  </code>
                </div>
                <button
                  type="button"
                  className="btn btn-sm btn-outline"
                  onClick={(e) => copySha(release.windowsAsset!.checksum!, e)}
                  aria-label="Copy SHA-256 Checksum"
                >
                  {copiedSha ? "✓ Copied" : "Copy Hash"}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
