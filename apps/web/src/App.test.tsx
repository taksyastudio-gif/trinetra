import { render, screen, fireEvent } from "@testing-library/react";
import axe from "axe-core";
import { describe, it, expect, beforeEach } from "vitest";
import App from "./App";

describe("Trinetra Web Accessibility & Functionality", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    document.documentElement.lang = "en";
  });

  it("has zero axe-core accessibility violations", async () => {
    const { container } = render(<App />);

    // axe-core check on the rendered container
    const results = await axe.run(container, {
      rules: {
        // region rule expects land-marks outside component root which is handled by header/main/footer
        region: { enabled: false },
      },
    });

    if (results.violations.length > 0) {
      console.error(
        "Axe violations:",
        JSON.stringify(results.violations, null, 2)
      );
    }
    expect(results.violations).toEqual([]);
  });

  it("contains exactly one h1 tag", () => {
    render(<App />);
    const h1s = document.querySelectorAll("h1");
    expect(h1s.length).toBe(1);
  });

  it("contains all required landmarks and skip link", () => {
    render(<App />);
    expect(document.querySelector("a.skip-link")).not.toBeNull();
    expect(document.querySelector("header.site-header")).not.toBeNull();
    expect(document.querySelector("main#main-content")).not.toBeNull();
    expect(document.querySelector("footer.site-footer")).not.toBeNull();
  });

  it("toggles language between English and Nepali", () => {
    render(<App />);
    const langBtn = screen.getByRole("button", { name: /नेपालीमा पढ्नुहोस्|Switch to English/i });
    expect(langBtn).not.toBeNull();

    // Toggle to Nepali
    fireEvent.click(langBtn);
    expect(document.documentElement.lang).toBe("ne");

    // Toggle back to English
    fireEvent.click(langBtn);
    expect(document.documentElement.lang).toBe("en");
  });

  it("toggles theme between dark and light", () => {
    render(<App />);
    const themeBtn = screen.getByRole("button", { name: /toggle color theme|रङ शैली परिवर्तन गर्नुहोस्/i });
    expect(themeBtn).not.toBeNull();

    const initialTheme = document.documentElement.getAttribute("data-theme");
    fireEvent.click(themeBtn);
    const newTheme = document.documentElement.getAttribute("data-theme");
    expect(newTheme).not.toBe(initialTheme);
  });

  it("filters status matrix items correctly", () => {
    render(<App />);
    const experimentalBtn = screen.getByRole("button", { name: /^Experimental$|^परीक्षणमा$/i });
    fireEvent.click(experimentalBtn);
    expect(experimentalBtn.getAttribute("aria-pressed")).toBe("true");

    const badges = document.querySelectorAll(".status-badge");
    expect(badges.length).toBeGreaterThan(0);
    badges.forEach((b) => {
      expect(b.classList.contains("badge-experimental")).toBe(true);
    });
  });

  it("contains zero mentions of UYSS, CS-12, or expo", () => {
    const { container } = render(<App />);
    const text = container.textContent || "";
    expect(text).not.toMatch(/UYSS/i);
    expect(text).not.toMatch(/CS-12/i);
    expect(text).not.toMatch(/\bexpo\b/i);
  });

  it("has no broken or empty hrefs in links", () => {
    render(<App />);
    const links = document.querySelectorAll("a");
    links.forEach((a) => {
      const href = a.getAttribute("href");
      expect(href).not.toBeNull();
      expect(href).not.toBe("");
      expect(href).not.toBe("http://");
      expect(href).not.toBe("https://");
    });
  });
});
