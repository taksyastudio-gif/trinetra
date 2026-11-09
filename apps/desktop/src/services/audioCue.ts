/**
 * Trinetra Web Audio Earcons & Auditory Cues
 * ===========================================
 * Synthesizes zero-latency acoustic earcons via HTML5 Web Audio API.
 * Provides immediate auditory confirmation to blind users the millisecond
 * an action or hotkey is pressed, before TTS finishes synthesizing.
 */

let audioCtx: AudioContext | null = null;

function getAudioContext(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (AudioContextClass) {
      audioCtx = new AudioContextClass();
    }
  }
  if (audioCtx && audioCtx.state === "suspended") {
    audioCtx.resume().catch(() => {});
  }
  return audioCtx;
}

export type SoundEffectType = "mode_switch" | "success" | "hazard" | "tap" | "startup" | "heartbeat" | "watchdog_alert" | "uncertainty";

export function playAudioCue(type: SoundEffectType): void {
  try {
    const ctx = getAudioContext();
    if (!ctx) return;

    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.connect(gain);
    gain.connect(ctx.destination);

    if (type === "mode_switch") {
      // Crisp high-pitch double pip (580Hz -> 880Hz)
      osc.type = "sine";
      osc.frequency.setValueAtTime(587.33, now); // D5
      osc.frequency.setValueAtTime(880.0, now + 0.08); // A5
      gain.gain.setValueAtTime(0.15, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
      osc.start(now);
      osc.stop(now + 0.22);
    } else if (type === "success") {
      // Ascending major chord triad
      osc.type = "triangle";
      osc.frequency.setValueAtTime(523.25, now); // C5
      osc.frequency.setValueAtTime(659.25, now + 0.07); // E5
      osc.frequency.setValueAtTime(783.99, now + 0.14); // G5
      gain.gain.setValueAtTime(0.2, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
      osc.start(now);
      osc.stop(now + 0.35);
    } else if (type === "hazard") {
      // Sawtooth low warning pulse
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(220.0, now);
      osc.frequency.setValueAtTime(180.0, now + 0.12);
      gain.gain.setValueAtTime(0.25, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.28);
      osc.start(now);
      osc.stop(now + 0.28);
    } else if (type === "startup") {
      // Warm welcoming two-tone chime
      osc.type = "sine";
      osc.frequency.setValueAtTime(440.0, now); // A4
      osc.frequency.exponentialRampToValueAtTime(880.0, now + 0.25); // A5
      gain.gain.setValueAtTime(0.18, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
      osc.start(now);
      osc.stop(now + 0.45);
    } else if (type === "heartbeat") {
      // Extremely subtle, unobtrusive 20ms pulse to reassure blind user system is alive
      osc.type = "sine";
      osc.frequency.setValueAtTime(320.0, now);
      gain.gain.setValueAtTime(0.035, now);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.025);
      osc.start(now);
      osc.stop(now + 0.025);
    } else if (type === "watchdog_alert") {
      // Rapid double low pulse: Camera/Pipeline freeze or disconnect
      osc.type = "square";
      osc.frequency.setValueAtTime(140.0, now);
      osc.frequency.setValueAtTime(120.0, now + 0.12);
      gain.gain.setValueAtTime(0.22, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.28);
      osc.start(now);
      osc.stop(now + 0.28);
    } else if (type === "uncertainty") {
      // Descending cautionary tone: "Uncertain terrain, probe with cane"
      osc.type = "triangle";
      osc.frequency.setValueAtTime(440.0, now);
      osc.frequency.setValueAtTime(349.23, now + 0.12); // F4
      gain.gain.setValueAtTime(0.12, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.26);
      osc.start(now);
      osc.stop(now + 0.26);
    } else {
      // Short tap
      osc.type = "sine";
      osc.frequency.setValueAtTime(800, now);
      gain.gain.setValueAtTime(0.1, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
      osc.start(now);
      osc.stop(now + 0.05);
    }
  } catch {
    // Non-blocking audio fallback
  }
}
