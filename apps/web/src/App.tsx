import { useEffect, useRef, useState } from 'react'
import anime from 'animejs'

/* ===== SVG Icon Component ===== */
const TrinetraLogo = ({ size = 36 }: { size?: number }) => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width={size} height={size}>
    <defs>
      <linearGradient id="eyeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style={{ stopColor: '#7c3aed' }} />
        <stop offset="100%" style={{ stopColor: '#06b6d4' }} />
      </linearGradient>
      <linearGradient id="irisGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style={{ stopColor: '#06b6d4' }} />
        <stop offset="100%" style={{ stopColor: '#7c3aed' }} />
      </linearGradient>
    </defs>
    <ellipse cx="50" cy="50" rx="40" ry="28" fill="none" stroke="url(#eyeGrad)" strokeWidth="3" />
    <circle cx="50" cy="50" r="16" fill="url(#irisGrad)" opacity="0.9" />
    <circle cx="50" cy="50" r="7" fill="#050510" />
    <circle cx="45" cy="45" r="3" fill="white" opacity="0.7" />
    <circle cx="50" cy="18" r="4" fill="url(#eyeGrad)" opacity="0.8" />
  </svg>
)

/* ===== Feature Data ===== */
const features = [
  {
    icon: '👁️',
    title: 'Scene Understanding',
    titleNe: 'दृश्य बुझाइ',
    desc: 'Powered by Gemini AI, Trinetra describes the full scene — people, actions, environment — not just objects.',
  },
  {
    icon: '🗣️',
    title: 'Nepali-First Speech',
    titleNe: 'नेपाली बोली',
    desc: 'Natural Nepali speech output via Piper neural TTS. Speaks in your language, locally, with zero cloud dependency.',
  },
  {
    icon: '🎤',
    title: 'Voice Commands',
    titleNe: 'आवाज आदेश',
    desc: '"के छ?" — Ask what\'s around you. Fully hands-free interaction designed for real-world use.',
  },
  {
    icon: '💵',
    title: 'Currency Recognition',
    titleNe: 'नोट पहिचान',
    desc: 'Instantly identify Nepali rupee denominations. Trained on real Nepal currency with offline AI models.',
  },
  {
    icon: '🗺️',
    title: 'Offline Navigation',
    titleNe: 'अफलाइन नेभिगेसन',
    desc: 'Built on OpenStreetMap data. Pedestrian routing that works in Kathmandu, Pokhara, or any village — no internet required.',
  },
  {
    icon: '📳',
    title: 'Haptic Feedback',
    titleNe: 'कम्पन प्रतिक्रिया',
    desc: 'Vibration patterns complement audio for noisy streets. Gentle pulse for distant obstacles, rapid buzz for danger.',
  },
  {
    icon: '📷',
    title: 'ESP32-CAM Wearable',
    titleNe: 'पहिरने क्यामेरा',
    desc: 'Affordable chest-mounted camera (~$5) streams video over WiFi. Open hardware design anyone can build.',
  },
  {
    icon: '🆘',
    title: 'Emergency SOS',
    titleNe: 'आपतकालीन SOS',
    desc: 'One voice command sends your GPS location to trusted contacts via SMS. Works without internet.',
  },
  {
    icon: '🔒',
    title: 'Privacy-First',
    titleNe: 'गोपनीयता',
    desc: 'All processing happens locally on your device. No cloud uploads, no tracking, no data collection. Ever.',
  },
]

/* ===== Flow Steps ===== */
const flowSteps = [
  { icon: '📷', title: 'ESP32-CAM', desc: 'Chest-mounted camera captures surroundings' },
  { icon: '📶', title: 'WiFi Stream', desc: 'Video streams to your phone wirelessly' },
  { icon: '🧠', title: 'AI Processing', desc: 'On-device detection & scene understanding' },
  { icon: '🔊', title: 'Audio/Haptic', desc: 'Nepali speech + vibration feedback' },
]

/* ===== Particles Background ===== */
function Particles() {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const container = containerRef.current
    const particleCount = 30

    for (let i = 0; i < particleCount; i++) {
      const particle = document.createElement('div')
      particle.className = 'particle'
      particle.style.left = `${Math.random() * 100}%`
      particle.style.top = `${Math.random() * 100}%`
      const colors = ['#7c3aed', '#06b6d4', '#8b5cf6', '#14b8a6']
      particle.style.background = colors[Math.floor(Math.random() * colors.length)]
      particle.style.width = `${Math.random() * 3 + 1}px`
      particle.style.height = particle.style.width
      container.appendChild(particle)

      anime({
        targets: particle,
        opacity: [0, () => Math.random() * 0.4 + 0.1, 0],
        translateX: () => anime.random(-80, 80),
        translateY: () => anime.random(-80, 80),
        scale: [0, () => Math.random() + 0.5, 0],
        duration: anime.random(4000, 8000),
        delay: anime.random(0, 5000),
        easing: 'easeInOutQuad',
        loop: true,
      })
    }

    return () => {
      container.innerHTML = ''
    }
  }, [])

  return <div className="particles-container" ref={containerRef} />
}

/* ===== Intersection Observer Hook ===== */
function useScrollReveal(threshold = 0.15) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('animate-in')
            observer.unobserve(entry.target)
          }
        })
      },
      { threshold }
    )

    const children = el.querySelectorAll('.feature-card, .flow-step, .flow-arrow, .stat-item, .arch-diagram, .download-card, .open-source-content')
    children.forEach((child) => observer.observe(child))

    return () => observer.disconnect()
  }, [threshold])

  return ref
}

/* ===== Main App ===== */
const REPO_URL = 'https://github.com/taksyastudio-gif/trinetra'
const RELEASES_URL = `${REPO_URL}/releases`
const DESKTOP_EXE_DOWNLOAD_URL = `${REPO_URL}/releases/latest/download/trinetra-desktop.exe`

export default function App() {
  const [scrolled, setScrolled] = useState(false)
  const [activeModal, setActiveModal] = useState<'apk' | 'desktop' | null>(null)
  const heroRef = useRef<HTMLDivElement>(null)
  const sectionRef = useScrollReveal()

  // Close modal on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setActiveModal(null)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Navbar scroll effect
  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 50)
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  // Hero entrance animation
  useEffect(() => {
    if (!heroRef.current) return

    const tl = anime.timeline({ easing: 'easeOutExpo' })

    tl.add({
      targets: '.hero-badge',
      opacity: [0, 1],
      translateY: [20, 0],
      duration: 800,
    })
      .add({
        targets: '.hero-title',
        opacity: [0, 1],
        translateY: [40, 0],
        duration: 1000,
      }, '-=500')
      .add({
        targets: '.hero-nepali',
        opacity: [0, 1],
        translateY: [30, 0],
        duration: 800,
      }, '-=600')
      .add({
        targets: '.hero-description',
        opacity: [0, 1],
        translateY: [30, 0],
        duration: 800,
      }, '-=500')
      .add({
        targets: '.hero-buttons',
        opacity: [0, 1],
        translateY: [20, 0],
        duration: 800,
      }, '-=500')
      .add({
        targets: '.scroll-indicator',
        opacity: [0, 0.6],
        translateY: [20, 0],
        duration: 600,
      }, '-=300')
  }, [])

  // Feature cards stagger animation on scroll
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            anime({
              targets: '.feature-card',
              opacity: [0, 1],
              translateY: [40, 0],
              delay: anime.stagger(100),
              duration: 800,
              easing: 'easeOutCubic',
            })
            observer.unobserve(entry.target)
          }
        })
      },
      { threshold: 0.1 }
    )

    const section = document.querySelector('.features')
    if (section) observer.observe(section)

    return () => observer.disconnect()
  }, [])

  // Flow steps animation
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            anime({
              targets: '.flow-step, .flow-arrow',
              opacity: [0, 1],
              translateY: [30, 0],
              delay: anime.stagger(150),
              duration: 700,
              easing: 'easeOutCubic',
            })
            observer.unobserve(entry.target)
          }
        })
      },
      { threshold: 0.2 }
    )

    const section = document.querySelector('.how-it-works')
    if (section) observer.observe(section)

    return () => observer.disconnect()
  }, [])

  // Stats counter animation
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            anime({
              targets: '.stat-item',
              opacity: [0, 1],
              translateY: [20, 0],
              delay: anime.stagger(100),
              duration: 600,
              easing: 'easeOutCubic',
            })

            // Animate counter numbers
            const counters = document.querySelectorAll('.stat-number[data-count]')
            counters.forEach((el) => {
              const target = parseInt(el.getAttribute('data-count') || '0', 10)
              const obj = { value: 0 }
              anime({
                targets: obj,
                value: target,
                duration: 2000,
                easing: 'easeOutExpo',
                round: 1,
                update: () => {
                  el.textContent = obj.value.toString()
                },
              })
            })

            observer.unobserve(entry.target)
          }
        })
      },
      { threshold: 0.3 }
    )

    const section = document.querySelector('.stats')
    if (section) observer.observe(section)

    return () => observer.disconnect()
  }, [])

  return (
    <>
      <Particles />
      <div className="bg-glow" />

      {/* Navigation */}
      <nav className={`navbar ${scrolled ? 'scrolled' : ''}`}>
        <div className="container">
          <a href="#" className="nav-logo" aria-label="Trinetra Home">
            <TrinetraLogo size={36} />
            <span>Trinetra</span>
          </a>
          <div className="nav-links">
            <a href="#features">Features</a>
            <a href="#how-it-works">How it Works</a>
            <a href="#architecture">Architecture</a>
            <a href="#open-source">Open Source</a>
            <button onClick={() => setActiveModal('apk')} className="nav-cta">Download</button>
          </div>
          <button className="mobile-menu-btn" aria-label="Toggle menu">
            <span /><span /><span />
          </button>
        </div>
      </nav>

      {/* Hero */}
      <section className="hero" ref={heroRef}>
        <div className="hero-eye" aria-hidden="true">
          <div className="eye-outer" />
          <div className="eye-iris" />
          <div className="eye-pupil" />
        </div>

        <div className="hero-content">
          <div className="hero-badge">
            <span className="dot" />
            Open Source • Made in Nepal 🇳🇵
          </div>

          <h1 className="hero-title">
            Your <span className="gradient-text">Third Eye</span>
          </h1>

          <p className="hero-nepali nepali">
            त्रिनेत्र — तपाईंको तेस्रो आँखा
          </p>

          <p className="hero-description">
            An open-source assistive vision platform that helps blind and visually impaired
            individuals perceive the world through AI-powered scene understanding, Nepali speech,
            and affordable wearable hardware.
          </p>

            <div className="hero-buttons">
            <button onClick={() => setActiveModal('desktop')} className="btn-primary">
              💻 Desktop & Hardware Suite
            </button>
            <button onClick={() => setActiveModal('apk')} className="btn-secondary">
              📱 Mobile App (Android)
            </button>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary"
            >
              ⭐ GitHub
            </a>
          </div>
        </div>

        <div className="scroll-indicator" aria-hidden="true">
          <span>Scroll</span>
          <div className="scroll-line" />
        </div>
      </section>

      {/* Features */}
      <section className="features" id="features" ref={sectionRef}>
        <div className="container">
          <div className="section-header">
            <span className="section-label">Features</span>
            <h2 className="section-title">
              Built for <span className="gradient-text">Real Life</span>
            </h2>
            <p className="section-subtitle">
              Every feature designed with input from the visually impaired community in Nepal.
            </p>
          </div>

          <div className="features-grid">
            {features.map((f, i) => (
              <div className="feature-card" key={i}>
                <div className="feature-icon">{f.icon}</div>
                <h3>
                  {f.title} <span className="nepali" style={{ opacity: 0.6, fontSize: '0.9em' }}>({f.titleNe})</span>
                </h3>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="how-it-works" id="how-it-works">
        <div className="container">
          <div className="section-header">
            <span className="section-label">How it Works</span>
            <h2 className="section-title">
              From <span className="gradient-text">Camera to Voice</span>
            </h2>
            <p className="section-subtitle">
              A simple, affordable pipeline that turns vision into spoken awareness.
            </p>
          </div>

          <div className="how-it-works-flow">
            {flowSteps.map((step, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center' }}>
                <div className="flow-step">
                  <div className="flow-step-icon">{step.icon}</div>
                  <h4>{step.title}</h4>
                  <p>{step.desc}</p>
                </div>
                {i < flowSteps.length - 1 && (
                  <div className="flow-arrow" aria-hidden="true">→</div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="stats">
        <div className="container">
          <div className="stats-grid">
            <div className="stat-item">
              <div className="stat-number" data-count="35">0</div>
              <div className="stat-label">ms Detection Latency</div>
            </div>
            <div className="stat-item">
              <div className="stat-number">{'<'}$<span data-count="15">0</span></div>
              <div className="stat-label">Hardware Cost</div>
            </div>
            <div className="stat-item">
              <div className="stat-number" data-count="100">0</div>
              <div className="stat-label">% Offline Capable</div>
            </div>
            <div className="stat-item">
              <div className="stat-number" data-count="0">0</div>
              <div className="stat-label">Data Sent to Cloud</div>
            </div>
          </div>
        </div>
      </section>

      {/* Architecture */}
      <section className="architecture" id="architecture">
        <div className="container">
          <div className="section-header">
            <span className="section-label">Architecture</span>
            <h2 className="section-title">
              Modular & <span className="gradient-text">Open</span>
            </h2>
            <p className="section-subtitle">
              Every component is decoupled, replaceable, and privacy-safe.
            </p>
          </div>

          <div className="arch-diagram">
            <div className="arch-layer">
              <div className="arch-node highlight">📷 ESP32-CAM</div>
            </div>
            <div className="arch-connector">↓ WiFi Stream</div>
            <div className="arch-layer">
              <div className="arch-node highlight">📱 Expo Mobile App</div>
              <div className="arch-node">💻 Desktop (Tauri 2)</div>
            </div>
            <div className="arch-connector">↓ Local Processing</div>
            <div className="arch-layer">
              <div className="arch-node">🧠 YOLOX-Nano</div>
              <div className="arch-node">✨ Gemini API</div>
              <div className="arch-node">🗺️ OSM Maps</div>
            </div>
            <div className="arch-connector">↓ Output</div>
            <div className="arch-layer">
              <div className="arch-node">🔊 Piper TTS</div>
              <div className="arch-node">📳 Haptics</div>
              <div className="arch-node">🆘 SOS</div>
            </div>
          </div>
        </div>
      </section>

      {/* Download CTA */}
      <section className="download" id="download">
        <div className="container">
          <div className="download-card">
            <h2>
              <span className="nepali">त्रिनेत्र</span> Download
            </h2>
            <p>
              Get the latest version of Trinetra on your Android device. 
              The app auto-updates — install once, always stay current.
            </p>
            <div className="download-buttons">
              <button onClick={() => setActiveModal('apk')} className="btn-primary">
                📱 Download APK
              </button>
              <button onClick={() => setActiveModal('desktop')} className="btn-secondary">
                💻 Desktop App
              </button>
            </div>
            <div className="download-badge">
              ✨ Auto-updates via EAS Update on every release
            </div>
          </div>
        </div>
      </section>

      {/* Open Source */}
      <section className="open-source" id="open-source">
        <div className="container">
          <div className="section-header">
            <span className="section-label">Open Source</span>
            <h2 className="section-title">
              Built by the <span className="gradient-text">Community</span>
            </h2>
          </div>

          <div className="open-source-content">
            <p>
              Trinetra is 100% open source under MIT License. We believe assistive technology
              should be free, accessible, and community-driven. Whether you're a developer,
              designer, hardware tinkerer, or someone who wants to help — you're welcome.
            </p>
            <p className="nepali" style={{ fontSize: '1.1rem', color: '#8b5cf6' }}>
              सबैका लागि, सबैबाट — यो तपाईंको पनि परियोजना हो।
            </p>
            <div style={{ marginTop: '32px', display: 'flex', gap: '16px', justifyContent: 'center', flexWrap: 'wrap' }}>
              <a
                href={REPO_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-primary"
              >
                🐙 View on GitHub
              </a>
              <a
                href={`${REPO_URL}#readme`}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary"
              >
                📖 Read the Docs
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="footer">
        <div className="container">
          <div className="footer-left">
            <TrinetraLogo size={28} />
            <span>Trinetra</span>
          </div>
          <div className="footer-links">
            <a href={REPO_URL} target="_blank" rel="noopener noreferrer">GitHub</a>
            <a href="#features">Features</a>
            <button onClick={() => setActiveModal('apk')} style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              Download
            </button>
          </div>
          <div className="footer-right">
            Made with ❤️ in Nepal 🇳🇵 • Open Source
          </div>
        </div>
      </footer>

      {/* Download Modal */}
      {activeModal && (
        <div className="modal-backdrop" onClick={() => setActiveModal(null)} role="dialog" aria-modal="true">
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <button
              className="modal-close-btn"
              onClick={() => setActiveModal(null)}
              aria-label="Close dialog"
            >
              ✕
            </button>

            {activeModal === 'apk' ? (
              <>
                <div className="modal-header">
                  <h3>📱 Download Trinetra for Android</h3>
                  <p className="nepali" style={{ color: 'var(--accent-cyan)' }}>
                    त्रिनेत्र एन्ड्रोइड एप डाउनलोड गर्नुहोस्
                  </p>
                  <p style={{ marginTop: '8px' }}>
                    Install the APK directly onto your Android device. Once installed, future updates are delivered over-the-air seamlessly.
                  </p>
                </div>

                <div className="modal-options">
                  <a
                    href={RELEASES_URL}
                    className="download-option-card"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <div className="download-option-info">
                      <span className="option-icon">📦</span>
                      <div>
                        <h4>GitHub Releases (Pre-Release)</h4>
                        <span>Download APK & inspect release builds</span>
                      </div>
                    </div>
                    <span className="btn-primary" style={{ padding: '8px 16px', fontSize: '0.85rem' }}>
                      Releases ↗
                    </span>
                  </a>
                </div>

                <div className="modal-steps" style={{ borderColor: 'rgba(236, 72, 153, 0.4)', background: 'rgba(236, 72, 153, 0.05)' }}>
                  <h5 style={{ color: 'var(--accent-pink)' }}>⚠️ Note for Teammates & Testers</h5>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    The Android APK build pipeline is currently being initialized. Once our first mobile build passes CI, the ready-to-install <code>trinetra.apk</code> will be directly downloadable here and on the Releases page!
                  </p>
                </div>

                <div className="modal-steps">
                  <h5>Installation Guide (३ सजिला चरणहरू)</h5>
                  <ol>
                    <li>Tap <strong>Direct APK Download</strong> to save <code>trinetra.apk</code> to your device.</li>
                    <li>Open your Downloads folder, tap the file, and toggle <strong>"Allow from this source"</strong> if prompted.</li>
                    <li>Open Trinetra! Any new push to GitHub will automatically stream updates to your app without reinstalling.</li>
                  </ol>
                </div>

                <div className="modal-footer">
                  🔒 100% Free & Open Source • Zero Cloud Analytics
                </div>
              </>
            ) : (
              <>
                <div className="modal-header">
                  <h3>💻 Trinetra Desktop & Hardware Suite</h3>
                  <p className="nepali" style={{ color: 'var(--accent-purple)' }}>
                    हार्डवेयर विकास र परीक्षण सुइट (Tauri 2 + Python Vision Engine)
                  </p>
                  <p style={{ marginTop: '8px' }}>
                    Real-time visual feed, ESP32-CAM stream receiver, AI obstacle detection, and live audio guidance on Windows.
                  </p>
                </div>

                <div className="modal-options">
                  <a
                    href={DESKTOP_EXE_DOWNLOAD_URL}
                    className="download-option-card"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <div className="download-option-info">
                      <span className="option-icon">🪟</span>
                      <div>
                        <h4>Download Desktop Executable (.exe)</h4>
                        <span>v0.1.0 Standalone Windows App • No setup required</span>
                      </div>
                    </div>
                    <span className="btn-primary" style={{ padding: '8px 16px', fontSize: '0.85rem' }}>
                      Download EXE ↓
                    </span>
                  </a>

                  <a
                    href={`${REPO_URL}/blob/master/hardware/firmware/esp32-cam/trinetra_esp32_cam.ino`}
                    className="download-option-card"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <div className="download-option-info">
                      <span className="option-icon">📷</span>
                      <div>
                        <h4>ESP32-CAM Firmware (.ino)</h4>
                        <span>Flash AI-Thinker module with low-latency MJPEG stream</span>
                      </div>
                    </div>
                    <span className="btn-secondary" style={{ padding: '8px 16px', fontSize: '0.85rem' }}>
                      Get Code ↗
                    </span>
                  </a>

                  <a
                    href={`${REPO_URL}/archive/refs/heads/master.zip`}
                    className="download-option-card"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <div className="download-option-info">
                      <span className="option-icon">📦</span>
                      <div>
                        <h4>Download Source (.zip)</h4>
                        <span>Complete workstation with 1-click launcher</span>
                      </div>
                    </div>
                    <span className="btn-secondary" style={{ padding: '8px 16px', fontSize: '0.85rem' }}>
                      Download ZIP ↓
                    </span>
                  </a>
                </div>

                <div className="modal-steps">
                  <h5>⚡ 1-Click Hardware Test (Hardware Teammates)</h5>
                  <ol>
                    <li>Clone or download repository: <code>git clone {REPO_URL}.git</code></li>
                    <li>Double-click <strong><code>start-trinetra.bat</code></strong> in the project folder.</li>
                    <li>In the desktop window, switch to <strong>"📡 Network Stream (ESP32-CAM)"</strong> tab.</li>
                    <li>Enter your ESP32-CAM stream URL (e.g. <code>http://192.168.1.100:81/stream</code>) and click <strong>Start Camera</strong>!</li>
                  </ol>
                </div>

                <div className="modal-footer">
                  Runs 100% offline at 127.0.0.1 with zero cloud uploads
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
