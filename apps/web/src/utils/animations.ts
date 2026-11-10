import { animate, stagger, type JSAnimation } from "animejs";

/**
 * Checks whether the user has requested reduced motion.
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/**
 * Runs hero staggered entrance animation.
 */
export function animateHeroEntrance(targets: string | HTMLElement | HTMLElement[]): void {
  if (prefersReducedMotion()) return;

  try {
    animate(targets, {
      opacity: [0, 1],
      translateY: [24, 0],
      delay: stagger(80, { start: 100 }),
      duration: 750,
      ease: "outCubic",
    });
  } catch {
    // Fallback gracefully if DOM is not ready
  }
}

/**
 * Animates concentric sonar/radar rings for Trinetra's "Third Eye" assistive radar.
 */
export function animateRadarPulse(targets: string | HTMLElement | HTMLElement[]): JSAnimation | null {
  if (prefersReducedMotion()) return null;

  try {
    return animate(targets, {
      scale: [1, 2.3],
      opacity: [0.65, 0],
      delay: stagger(700),
      duration: 2100,
      loop: true,
      ease: "outQuad",
    });
  } catch {
    return null;
  }
}

/**
 * Animates tab selection indicator glide and content panel fade-scale.
 */
export function animateTabTransition(panelTarget: string | HTMLElement): void {
  if (prefersReducedMotion()) return;

  try {
    animate(panelTarget, {
      opacity: [0, 1],
      translateY: [12, 0],
      scale: [0.98, 1],
      duration: 320,
      ease: "outQuad",
    });
  } catch {
    // Fallback
  }
}

/**
 * Elastic button tap micro-interaction.
 */
export function animateButtonBounce(target: HTMLElement): void {
  if (prefersReducedMotion()) return;

  try {
    animate(target, {
      scale: [1, 0.94, 1.03, 1],
      duration: 350,
      ease: "outElastic(1, .6)",
    });
  } catch {
    // Fallback
  }
}
