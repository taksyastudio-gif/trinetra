/**
 * Trinetra Spatial Audio Radar (Sonar Proximity Engine)
 * Generates directional stereo clicks / pulses for blind and visually impaired navigation.
 * Uses native Web Audio API with zero external dependencies.
 */

import { DetectionItem } from "../types/api";

class SpatialAudioRadar {
  private audioCtx: AudioContext | null = null;
  private isEnabled: boolean = false;
  private lastTickTime: number = 0;
  private minDistance: number = 999.0;
  private activeSector: "left" | "center" | "right" = "center";

  public setEnabled(enabled: boolean) {
    this.isEnabled = enabled;
    if (enabled && !this.audioCtx) {
      try {
        const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        this.audioCtx = new AudioContextClass();
      } catch (err) {
        console.warn("Web Audio API not supported:", err);
      }
    }
  }

  public getIsEnabled(): boolean {
    return this.isEnabled;
  }

  public getMinDistance(): number {
    return this.minDistance;
  }

  public getActiveSector(): "left" | "center" | "right" {
    return this.activeSector;
  }

  public stop() {
    this.minDistance = 999.0;
  }

  public toggle(): boolean {
    this.setEnabled(!this.isEnabled);
    return this.isEnabled;
  }

  /**
   * Called on every perception frame to evaluate closest obstacle and trigger spatial ticks.
   */
  public updateDetections(detections: DetectionItem[]) {
    if (!this.isEnabled || !this.audioCtx) return;

    if (this.audioCtx.state === "suspended") {
      this.audioCtx.resume().catch(() => {});
    }

    if (!detections || detections.length === 0) {
      this.minDistance = 999.0;
      return;
    }

    // Find closest object
    let closestDist = 999.0;
    let closestSector: "left" | "center" | "right" = "center";

    for (const d of detections) {
      const boxHeight = d.box ? Math.max(0.05, d.box.y_max - d.box.y_min) : 0.4;
      const dist = d.distance_m ?? Math.max(0.4, Math.min(3.0, 1.0 / (boxHeight * 1.5)));
      if (dist < closestDist) {
        closestDist = dist;
        closestSector = (d.sector as "left" | "center" | "right") || "center";
      }
    }

    this.minDistance = closestDist;
    this.activeSector = closestSector;

    // Only tick if obstacle is within 2.5 meters
    if (closestDist > 2.5) return;

    // Calculate pulse interval based on distance:
    // 0.4m -> 140ms, 1.0m -> 350ms, 2.0m -> 800ms, 2.5m -> 1200ms
    const intervalMs = Math.max(120, Math.min(1300, closestDist * 450));
    const now = performance.now();

    if (now - this.lastTickTime >= intervalMs) {
      this.lastTickTime = now;
      this.playSpatialTick(closestSector, closestDist);
    }
  }

  private playSpatialTick(sector: "left" | "center" | "right", distance: number) {
    if (!this.audioCtx) return;

    try {
      const now = this.audioCtx.currentTime;

      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();

      // Stereo pan: left = -0.85, center = 0.0, right = +0.85
      let panValue = 0.0;
      if (sector === "left") panValue = -0.85;
      else if (sector === "right") panValue = 0.85;

      let panner: StereoPannerNode | null = null;
      if (this.audioCtx.createStereoPanner) {
        panner = this.audioCtx.createStereoPanner();
        panner.pan.setValueAtTime(panValue, now);
      }

      // Pitch increases as distance gets dangerously close (400Hz up to 1000Hz)
      const freq = Math.max(400, Math.min(1100, 1100 - distance * 280));
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, now);

      // Short tactile acoustic click (35ms envelope)
      gain.gain.setValueAtTime(0.001, now);
      gain.gain.exponentialRampToValueAtTime(0.35, now + 0.006);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.038);

      if (panner) {
        osc.connect(gain);
        gain.connect(panner);
        panner.connect(this.audioCtx.destination);
      } else {
        osc.connect(gain);
        gain.connect(this.audioCtx.destination);
      }

      osc.start(now);
      osc.stop(now + 0.040);
    } catch {
      // Audio node failure non-fatal
    }
  }
}

export const spatialAudioRadar = new SpatialAudioRadar();
