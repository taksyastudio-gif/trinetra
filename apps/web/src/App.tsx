import { useEffect, useState, useTransition } from "react";
import logoSvg from "./assets/logo.svg";
import statusData from "./data/status.json";
import enTranslations from "./i18n/en.json";
import neTranslations from "./i18n/ne.json";
import {
  APP_VERSION,
  FIRMWARE_SOURCE_URL,
  GITHUB_REPO_URL,
  RELEASES_PAGE_URL,
} from "./config";
import {
  detectOS,
  fetchLatestRelease,
  formatBytes,
  formatDate,
  type DetectedOS,
  type LatestReleaseInfo,
} from "./services/releases";

type Language = "en" | "ne";
type Theme = "dark" | "light";
type StatusFilter = "all" | "working" | "experimental" | "planned";

export default function App() {
  const [lang, setLang] = useState<Language>(() => {
    try {
      const saved = localStorage.getItem("trinetra_lang");
      if (saved === "ne" || saved === "en") return saved;
      // Default to Nepali if user browser prefers Nepali, otherwise English
      return navigator.language.startsWith("ne") ? "ne" : "en";
    } catch {
      return "en";
    }
  });

  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = localStorage.getItem("trinetra_theme");
      if (saved === "light" || saved === "dark") return saved;
      return window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    } catch {
      return "dark";
    }
  });

  const [release, setRelease] = useState<LatestReleaseInfo | null>(null);
  const [releaseLoading, setReleaseLoading] = useState(true);
  const [detectedOS] = useState<DetectedOS>(() => detectOS());
  const [copiedSha, setCopiedSha] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [, startTransition] = useTransition();

  const t = lang === "ne" ? neTranslations : enTranslations;

  // Sync html lang and localStorage
  useEffect(() => {
    document.documentElement.lang = lang;
    try {
      localStorage.setItem("trinetra_lang", lang);
    } catch {
      // ignore
    }
  }, [lang]);

  // Sync theme to root dataset and localStorage
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("trinetra_theme", theme);
    } catch {
      // ignore
    }
  }, [theme]);

  // Fetch release info client-side
  useEffect(() => {
    let isMounted = true;
    fetchLatestRelease()
      .then((data) => {
        if (isMounted) {
          setRelease(data);
          setReleaseLoading(false);
        }
      })
      .catch(() => {
        if (isMounted) {
          setReleaseLoading(false);
        }
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const toggleLanguage = () => {
    const nextLang: Language = lang === "en" ? "ne" : "en";
    startTransition(() => {
      setLang(nextLang);
    });
    setAnnouncement(
      nextLang === "ne"
        ? "भाषा नेपालीमा परिवर्तन भयो"
        : "Language changed to English"
    );
  };

  const toggleTheme = () => {
    const nextTheme: Theme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    setAnnouncement(
      t.live.themeChanged.replace("{theme}", nextTheme)
    );
  };

  const handleCopyChecksum = async (sha: string) => {
    try {
      await navigator.clipboard.writeText(sha);
      setCopiedSha(sha);
      setAnnouncement(t.live.checksumCopied);
      setTimeout(() => setCopiedSha(null), 3000);
    } catch {
      // Fallback
    }
  };

  // Primary OS download button logic
  const getPrimaryDownloadAction = () => {
    if (detectedOS === "Windows") {
      if (release?.windowsAsset?.downloadUrl) {
        return {
          label: t.hero.downloadPrimary.replace("{os}", "Windows"),
          url: release.windowsAsset.downloadUrl,
          isDirectDownload: true,
          size: formatBytes(release.windowsAsset.size),
        };
      }
      return {
        label: `${t.downloads.windows.title} (${t.status.workingBadge})`,
        url: "#downloads",
        isDirectDownload: false,
        size: null,
      };
    }

    if (detectedOS === "Android") {
      if (release?.androidAsset?.downloadUrl) {
        return {
          label: t.hero.downloadPrimary.replace("{os}", "Android (APK)"),
          url: release.androidAsset.downloadUrl,
          isDirectDownload: true,
          size: formatBytes(release.androidAsset.size),
        };
      }
      return {
        label: `${t.downloads.android.title} (PWA)`,
        url: "#downloads",
        isDirectDownload: false,
        size: null,
      };
    }

    if (detectedOS === "iOS") {
      return {
        label: `${t.downloads.ios.title} (PWA)`,
        url: "#downloads",
        isDirectDownload: false,
        size: null,
      };
    }

    return {
      label: t.hero.downloadFallback,
      url: GITHUB_REPO_URL,
      isDirectDownload: false,
      size: null,
    };
  };

  const primaryAction = getPrimaryDownloadAction();

  // Filtered status items
  const filteredStatusItems = statusData.filter((item) => {
    if (statusFilter === "all") return true;
    return item.status === statusFilter;
  });

  return (
    <>
      {/* Screen Reader Live Region */}
      <div
        className="sr-only"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {announcement}
      </div>

      {/* Skip to Content Link */}
      <a href="#main-content" className="skip-link">
        {t.nav.skipToContent}
      </a>

      {/* Site Header */}
      <header className="site-header" role="banner">
        <div className="container header-inner">
          <a href="#" className="brand-link" aria-label="Trinetra Home">
            <img
              src={logoSvg}
              alt=""
              aria-hidden="true"
              className="brand-logo"
              width="32"
              height="32"
            />
            <div className="brand-wordmark">
              <span>{t.nav.wordmarkLatin}</span>
              <span className="brand-devanagari">
                {t.nav.wordmarkDevanagari}
              </span>
            </div>
          </a>

          <nav className="site-nav" role="navigation" aria-label="Main Navigation">
            <a href="#downloads" className="nav-link">
              {t.nav.downloads}
            </a>
            <a href="#how-it-works" className="nav-link">
              {t.nav.howItWorks}
            </a>
            <a href="#status" className="nav-link">
              {t.nav.status}
            </a>
            <a href="#privacy" className="nav-link">
              {t.nav.privacy}
            </a>
            <a href="#changelog" className="nav-link">
              {t.nav.changelog}
            </a>
          </nav>

          <div className="header-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={toggleLanguage}
              aria-label={t.nav.toggleLanguage}
            >
              {lang === "en" ? "नेपाली" : "English"}
            </button>
            <button
              type="button"
              className="btn btn-icon"
              onClick={toggleTheme}
              aria-label={t.nav.toggleTheme}
              title={t.nav.toggleTheme}
            >
              {theme === "dark" ? (
                // Sun Icon
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="5" />
                  <line x1="12" y1="1" x2="12" y2="3" />
                  <line x1="12" y1="21" x2="12" y2="23" />
                  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                  <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                  <line x1="1" y1="12" x2="3" y2="12" />
                  <line x1="21" y1="12" x2="23" y2="12" />
                  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                  <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
                </svg>
              ) : (
                // Moon Icon
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Landmark */}
      <main id="main-content" tabIndex={-1}>
        {/* Section 1: Hero */}
        <section className="section hero-section" aria-labelledby="hero-title">
          <div className="container hero-content">
            <div className="hero-tag">
              <span aria-hidden="true">🇳🇵</span>
              <span>
                {t.hero.osDetected.replace("{os}", detectedOS)}
              </span>
            </div>

            <h1 id="hero-title" className="hero-title">
              {t.hero.tagline}
            </h1>

            <p className="hero-desc">{t.hero.description}</p>

            <div className="hero-cta">
              <a
                href={primaryAction.url}
                className="btn btn-primary btn-large"
                {...(primaryAction.isDirectDownload
                  ? { download: "" }
                  : {})}
              >
                {primaryAction.label}
              </a>

              <p className="hero-release-info">
                {t.hero.versionInfo.replace(
                  "{version}",
                  release?.version || APP_VERSION
                )}
                {primaryAction.size ? ` • ${primaryAction.size}` : ""}
              </p>

              <a href="#downloads" className="hero-alt-link">
                {t.hero.otherPlatforms}
              </a>
            </div>
          </div>
        </section>

        {/* Section 2: Downloads */}
        <section id="downloads" className="section" aria-labelledby="downloads-title">
          <div className="container">
            <div className="section-header">
              <h2 id="downloads-title" className="section-title">
                {t.downloads.title}
              </h2>
              <p className="section-subtitle">{t.downloads.subtitle}</p>
            </div>

            <div className="cards-grid">
              {/* Windows Card */}
              <div className="card">
                <div className="card-icon" aria-hidden="true">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                    <line x1="8" y1="21" x2="16" y2="21" />
                    <line x1="12" y1="17" x2="12" y2="21" />
                  </svg>
                </div>
                <h3 className="card-title">{t.downloads.windows.title}</h3>
                <p className="card-desc">{t.downloads.windows.subtitle}</p>

                <div className="card-meta">
                  <div className="meta-row">
                    <span className="meta-label">
                      {t.downloads.versionLabel}
                    </span>
                    <span className="meta-value">
                      v{release?.version || APP_VERSION}
                    </span>
                  </div>
                  <div className="meta-row">
                    <span className="meta-label">{t.downloads.dateLabel}</span>
                    <span className="meta-value">
                      {release?.publishedAt
                        ? formatDate(release.publishedAt)
                        : "Nov 2026"}
                    </span>
                  </div>
                  <div className="meta-row">
                    <span className="meta-label">{t.downloads.sizeLabel}</span>
                    <span className="meta-value">
                      {release?.windowsAsset?.size
                        ? formatBytes(release.windowsAsset.size)
                        : "~120 MB"}
                    </span>
                  </div>
                  {release?.windowsAsset?.checksum && (
                    <div className="checksum-box">
                      <span className="checksum-hash" title={release.windowsAsset.checksum}>
                        {release.windowsAsset.checksum.slice(0, 16)}...
                      </span>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ minHeight: "32px", padding: "0.2rem 0.6rem", fontSize: "0.75rem" }}
                        onClick={() =>
                          handleCopyChecksum(release.windowsAsset!.checksum!)
                        }
                      >
                        {copiedSha === release.windowsAsset.checksum
                          ? t.downloads.copiedChecksum
                          : t.downloads.copyChecksum}
                      </button>
                    </div>
                  )}
                </div>

                {release?.windowsAsset?.downloadUrl ? (
                  <a
                    href={release.windowsAsset.downloadUrl}
                    className="btn btn-primary"
                    download
                  >
                    {t.downloads.windows.downloadButton}
                  </a>
                ) : (
                  <a
                    href={`${GITHUB_REPO_URL}#readme`}
                    className="btn btn-secondary"
                    target="_blank"
                    rel="noreferrer"
                  >
                    {t.downloads.windows.sourceButton}
                  </a>
                )}
              </div>

              {/* Android Card */}
              <div className="card">
                <div className="card-icon" aria-hidden="true">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect x="5" y="2" width="14" height="20" rx="2" ry="2" />
                    <line x1="12" y1="18" x2="12.01" y2="18" />
                  </svg>
                </div>
                <h3 className="card-title">{t.downloads.android.title}</h3>
                <p className="card-desc">{t.downloads.android.subtitle}</p>

                <div className="card-meta">
                  <strong style={{ marginBottom: "0.25rem", color: "var(--text-primary)" }}>
                    {t.downloads.android.guideTitle}
                  </strong>
                  <p style={{ margin: "0.2rem 0" }}>{t.downloads.android.step1}</p>
                  <p style={{ margin: "0.2rem 0" }}>{t.downloads.android.step2}</p>
                  <p style={{ margin: "0.2rem 0" }}>{t.downloads.android.step3}</p>
                </div>

                {release?.androidAsset?.downloadUrl ? (
                  <a
                    href={release.androidAsset.downloadUrl}
                    className="btn btn-primary"
                    download
                  >
                    Download APK ({formatBytes(release.androidAsset.size)})
                  </a>
                ) : (
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-tertiary)" }}>
                    {t.downloads.android.apkNote}
                  </p>
                )}
              </div>

              {/* iOS Card */}
              <div className="card">
                <div className="card-icon" aria-hidden="true">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8z" />
                    <path d="M12 6v6l4 2" />
                  </svg>
                </div>
                <h3 className="card-title">{t.downloads.ios.title}</h3>
                <p className="card-desc">{t.downloads.ios.subtitle}</p>

                <div className="card-meta">
                  <strong style={{ marginBottom: "0.25rem", color: "var(--text-primary)" }}>
                    {t.downloads.ios.guideTitle}
                  </strong>
                  <p style={{ margin: "0.2rem 0" }}>{t.downloads.ios.step1}</p>
                  <p style={{ margin: "0.2rem 0" }}>{t.downloads.ios.step2}</p>
                  <p style={{ margin: "0.2rem 0" }}>{t.downloads.ios.step3}</p>
                </div>
              </div>

              {/* ESP32-CAM Firmware Card */}
              <div className="card">
                <div className="card-icon" aria-hidden="true">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z" />
                    <circle cx="12" cy="13" r="3" />
                  </svg>
                </div>
                <h3 className="card-title">{t.downloads.firmware.title}</h3>
                <p className="card-desc">{t.downloads.firmware.subtitle}</p>

                <div className="card-meta">
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                    {t.downloads.firmware.instructions}
                  </p>
                </div>

                <a
                  href={FIRMWARE_SOURCE_URL}
                  className="btn btn-primary"
                  target="_blank"
                  rel="noreferrer"
                >
                  {t.downloads.firmware.actionButton}
                </a>
              </div>
            </div>
          </div>
        </section>

        {/* Section 3: How It Works */}
        <section id="how-it-works" className="section" aria-labelledby="how-title">
          <div className="container">
            <div className="section-header">
              <h2 id="how-title" className="section-title">
                {t.howItWorks.title}
              </h2>
              <p className="section-subtitle">{t.howItWorks.subtitle}</p>
            </div>

            <div className="steps-grid">
              {/* Step 1 */}
              <div className="step-card">
                <div className="step-illustration" aria-hidden="true">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="44"
                    height="44"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                    <circle cx="12" cy="13" r="4" />
                  </svg>
                </div>
                <h3 className="step-title">{t.howItWorks.step1Title}</h3>
                <p className="step-desc">{t.howItWorks.step1Desc}</p>
              </div>

              {/* Step 2 */}
              <div className="step-card">
                <div className="step-illustration" aria-hidden="true">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="44"
                    height="44"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect x="4" y="4" width="16" height="16" rx="2" />
                    <rect x="9" y="9" width="6" height="6" />
                    <line x1="9" y1="1" x2="9" y2="4" />
                    <line x1="15" y1="1" x2="15" y2="4" />
                    <line x1="9" y1="20" x2="9" y2="23" />
                    <line x1="15" y1="20" x2="15" y2="23" />
                    <line x1="20" y1="9" x2="23" y2="9" />
                    <line x1="20" y1="15" x2="23" y2="15" />
                    <line x1="1" y1="9" x2="4" y2="9" />
                    <line x1="1" y1="15" x2="4" y2="15" />
                  </svg>
                </div>
                <h3 className="step-title">{t.howItWorks.step2Title}</h3>
                <p className="step-desc">{t.howItWorks.step2Desc}</p>
              </div>

              {/* Step 3 */}
              <div className="step-card">
                <div className="step-illustration" aria-hidden="true">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="44"
                    height="44"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                    <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" />
                  </svg>
                </div>
                <h3 className="step-title">{t.howItWorks.step3Title}</h3>
                <p className="step-desc">{t.howItWorks.step3Desc}</p>
              </div>
            </div>
          </div>
        </section>

        {/* Section 4: What Works Today, Honestly */}
        <section id="status" className="section" aria-labelledby="status-title">
          <div className="container">
            <div className="section-header">
              <h2 id="status-title" className="section-title">
                {t.status.title}
              </h2>
              <p className="section-subtitle">{t.status.subtitle}</p>
            </div>

            {/* Filter controls */}
            <div
              className="status-filters"
              role="group"
              aria-label="Filter features by status"
            >
              {(
                [
                  { key: "all", label: t.status.filterAll },
                  { key: "working", label: t.status.filterWorking },
                  { key: "experimental", label: t.status.filterExperimental },
                  { key: "planned", label: t.status.filterPlanned },
                ] as const
              ).map((f) => (
                <button
                  key={f.key}
                  type="button"
                  className="filter-btn"
                  aria-pressed={statusFilter === f.key}
                  onClick={() => setStatusFilter(f.key)}
                >
                  {f.label}
                </button>
              ))}
            </div>

            <div className="status-grid">
              {filteredStatusItems.map((item) => {
                const name = lang === "ne" ? item.name_ne : item.name_en;
                const note = lang === "ne" ? item.note_ne : item.note_en;
                const badgeLabel =
                  item.status === "working"
                    ? t.status.workingBadge
                    : item.status === "experimental"
                    ? t.status.experimentalBadge
                    : t.status.plannedBadge;

                return (
                  <div key={item.id} className="status-card">
                    <div className="status-header">
                      <h3 className="status-name">{name}</h3>
                      <span
                        className={`status-badge badge-${item.status}`}
                        aria-label={`Status: ${badgeLabel}`}
                      >
                        {badgeLabel}
                      </span>
                    </div>
                    <p className="status-note">{note}</p>
                  </div>
                );
              })}
            </div>

            <div className="benchmarks-callout">
              <strong>{lang === "ne" ? "परीक्षण टिप्पणी:" : "Benchmark Calibration Note:"}</strong>{" "}
              {t.status.benchmarksNote}
            </div>
          </div>
        </section>

        {/* Section 5: Accessibility & Privacy */}
        <section id="privacy" className="section" aria-labelledby="privacy-title">
          <div className="container">
            <div className="section-header">
              <h2 id="privacy-title" className="section-title">
                {t.privacy.title}
              </h2>
              <p className="section-subtitle">{t.privacy.subtitle}</p>
            </div>

            <div className="cards-grid">
              <div className="card">
                <div className="card-icon" aria-hidden="true">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                  </svg>
                </div>
                <h3 className="card-title">{t.privacy.offlineTitle}</h3>
                <p className="card-desc">{t.privacy.offlineDesc}</p>
              </div>

              <div className="card">
                <div className="card-icon" aria-hidden="true">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                  </svg>
                </div>
                <h3 className="card-title">{t.privacy.screenReaderTitle}</h3>
                <p className="card-desc">{t.privacy.screenReaderDesc}</p>
              </div>

              <div className="card">
                <div className="card-icon" aria-hidden="true">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect x="2" y="4" width="20" height="16" rx="2" />
                    <line x1="6" y1="8" x2="6.01" y2="8" />
                    <line x1="10" y1="8" x2="10.01" y2="8" />
                    <line x1="14" y1="8" x2="14.01" y2="8" />
                    <line x1="18" y1="8" x2="18.01" y2="8" />
                    <line x1="8" y1="12" x2="8.01" y2="12" />
                    <line x1="12" y1="12" x2="12.01" y2="12" />
                    <line x1="16" y1="12" x2="16.01" y2="12" />
                    <line x1="7" y1="16" x2="17" y2="16" />
                  </svg>
                </div>
                <h3 className="card-title">{t.privacy.keyboardTitle}</h3>
                <p className="card-desc">{t.privacy.keyboardDesc}</p>
              </div>

              <div className="card">
                <div className="card-icon" aria-hidden="true">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <circle cx="12" cy="12" r="10" />
                    <path d="M12 2a10 10 0 0 1 0 20z" />
                  </svg>
                </div>
                <h3 className="card-title">{t.privacy.contrastTitle}</h3>
                <p className="card-desc">{t.privacy.contrastDesc}</p>
              </div>
            </div>
          </div>
        </section>

        {/* Section 6: Changelog */}
        <section id="changelog" className="section" aria-labelledby="changelog-title">
          <div className="container">
            <div className="section-header">
              <h2 id="changelog-title" className="section-title">
                {t.changelog.title}
              </h2>
              <p className="section-subtitle">{t.changelog.subtitle}</p>
            </div>

            <div className="changelog-box">
              {releaseLoading ? (
                <p style={{ textAlign: "center", color: "var(--text-secondary)" }}>
                  {t.changelog.loading}
                </p>
              ) : release?.hasRelease ? (
                <>
                  <div className="changelog-header">
                    <span className="changelog-tag">{release.name}</span>
                    <span className="changelog-date">
                      {t.changelog.releasedOn.replace(
                        "{date}",
                        formatDate(release.publishedAt)
                      )}
                    </span>
                  </div>
                  <div className="changelog-body">
                    {release.body || "Performance improvements and bug fixes."}
                  </div>
                  <div style={{ marginTop: "1.5rem" }}>
                    <a
                      href={release.htmlUrl}
                      className="btn btn-secondary"
                      target="_blank"
                      rel="noreferrer"
                    >
                      {t.changelog.viewRelease}
                    </a>
                  </div>
                </>
              ) : (
                <div style={{ textAlign: "center" }}>
                  <p style={{ color: "var(--text-secondary)", marginBottom: "1.5rem" }}>
                    {t.changelog.noReleases}
                  </p>
                  <a
                    href={RELEASES_PAGE_URL}
                    className="btn btn-secondary"
                    target="_blank"
                    rel="noreferrer"
                  >
                    {t.downloads.viewAllReleases}
                  </a>
                </div>
              )}
            </div>
          </div>
        </section>
      </main>

      {/* Footer Landmark */}
      <footer className="site-footer" role="contentinfo">
        <div className="container">
          <div className="disclaimer-banner" role="note">
            ⚠️ {t.footer.disclaimer}
          </div>

          <nav className="footer-nav" aria-label="Footer Navigation">
            <a
              href={GITHUB_REPO_URL}
              className="footer-link"
              target="_blank"
              rel="noreferrer"
            >
              {t.footer.github}
            </a>
            <a
              href={FIRMWARE_SOURCE_URL}
              className="footer-link"
              target="_blank"
              rel="noreferrer"
            >
              {t.footer.firmware}
            </a>
            <a
              href={RELEASES_PAGE_URL}
              className="footer-link"
              target="_blank"
              rel="noreferrer"
            >
              {t.footer.releases}
            </a>
            <a
              href={`${GITHUB_REPO_URL}/issues`}
              className="footer-link"
              target="_blank"
              rel="noreferrer"
            >
              {t.footer.reportIssue}
            </a>
          </nav>

          <div className="footer-bottom">
            <span>{t.footer.copyright}</span>
            <span>{t.footer.license}</span>
          </div>
        </div>
      </footer>
    </>
  );
}
