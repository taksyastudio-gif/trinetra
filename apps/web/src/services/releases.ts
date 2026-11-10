import {
  RELEASES_OWNER,
  RELEASES_REPO,
  CACHE_KEY_RELEASES,
  CACHE_TTL_MS,
  APP_VERSION,
} from "../config";

export type DetectedOS = "Windows" | "Android" | "iOS" | "macOS" | "Linux" | "Unknown";

export interface ReleaseAsset {
  name: string;
  size: number;
  downloadUrl: string;
  checksum?: string;
}

export interface LatestReleaseInfo {
  version: string;
  tag: string;
  name: string;
  publishedAt: string;
  htmlUrl: string;
  body: string;
  windowsAsset?: ReleaseAsset;
  androidAsset?: ReleaseAsset;
  checksumsUrl?: string;
  hasRelease: boolean;
}

export function detectOS(): DetectedOS {
  if (typeof window === "undefined" || typeof navigator === "undefined") {
    return "Windows";
  }

  const uad = (navigator as unknown as { userAgentData?: { platform?: string } })
    .userAgentData;
  if (uad?.platform) {
    const p = uad.platform.toLowerCase();
    if (p.includes("win")) return "Windows";
    if (p.includes("android")) return "Android";
    if (p.includes("ios") || p.includes("iphone") || p.includes("ipad")) return "iOS";
    if (p.includes("mac")) return "macOS";
    if (p.includes("linux")) return "Linux";
  }

  const ua = navigator.userAgent;
  if (/android/i.test(ua)) return "Android";
  if (/iPad|iPhone|iPod/.test(ua)) return "iOS";
  if (/Win/i.test(ua)) return "Windows";
  if (/Mac/i.test(ua)) return "macOS";
  if (/Linux/i.test(ua)) return "Linux";

  return "Unknown";
}

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

export function formatDate(dateString: string): string {
  try {
    const d = new Date(dateString);
    if (isNaN(d.getTime())) return dateString;
    return d.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return dateString;
  }
}

export async function fetchLatestRelease(): Promise<LatestReleaseInfo> {
  const directExeUrl = `https://github.com/${RELEASES_OWNER}/${RELEASES_REPO}/releases/latest/download/Trinetra.exe`;
  const fallback: LatestReleaseInfo = {
    version: APP_VERSION,
    tag: `v${APP_VERSION}`,
    name: `Trinetra v${APP_VERSION} (Standalone)`,
    publishedAt: "2026-11-08T18:00:00Z",
    htmlUrl: `https://github.com/${RELEASES_OWNER}/${RELEASES_REPO}/releases`,
    body: "100% In-House Native Assistive Platform for Windows",
    windowsAsset: {
      name: "Trinetra.exe",
      size: 476625790,
      downloadUrl: directExeUrl,
    },
    androidAsset: {
      name: "Trinetra-v0.2.0-Android.apk",
      size: 29360128,
      downloadUrl: `https://github.com/${RELEASES_OWNER}/${RELEASES_REPO}/releases/latest/download/Trinetra-v0.2.0-Android.apk`,
    },
    hasRelease: true,
  };

  if (typeof window === "undefined") return fallback;

  // 1-hour cache check in sessionStorage wrapped in try/catch
  try {
    const cached = window.sessionStorage.getItem(CACHE_KEY_RELEASES);
    if (cached) {
      const parsed = JSON.parse(cached);
      if (Date.now() - parsed.timestamp < CACHE_TTL_MS) {
        return parsed.data;
      }
    }
  } catch {
    // sessionStorage not accessible or corrupt
  }

  try {
    const res = await fetch(
      `https://api.github.com/repos/${RELEASES_OWNER}/${RELEASES_REPO}/releases/latest`,
      {
        headers: {
          Accept: "application/vnd.github.v3+json",
        },
      }
    );

    if (!res.ok) {
      // 404 means no releases yet in repo
      return fallback;
    }

    const data = await res.json();
    const assets: Array<{
      name: string;
      size: number;
      browser_download_url: string;
    }> = data.assets || [];

    const windowsAssetRaw = assets.find(
      (a) => a.name.endsWith(".exe") || a.name.endsWith(".msi") || a.name.endsWith(".zip")
    );
    const androidAssetRaw = assets.find((a) => a.name.endsWith(".apk"));
    const checksumAssetRaw = assets.find(
      (a) =>
        a.name.toLowerCase().includes("sha256") ||
        a.name.toLowerCase().includes("checksum")
    );

    let windowsChecksum: string | undefined;
    if (checksumAssetRaw) {
      try {
        const textRes = await fetch(checksumAssetRaw.browser_download_url);
        if (textRes.ok) {
          const checksumText = await textRes.text();
          if (windowsAssetRaw) {
            const line = checksumText
              .split("\n")
              .find((l) => l.includes(windowsAssetRaw.name));
            if (line) {
              const match = line.match(/[a-fA-F0-9]{64}/);
              if (match) windowsChecksum = match[0];
            }
          }
        }
      } catch {
        // Checksum file fetch failure is non-fatal
      }
    }

    const releaseInfo: LatestReleaseInfo = {
      version: data.tag_name?.replace(/^v/, "") || APP_VERSION,
      tag: data.tag_name || `v${APP_VERSION}`,
      name: data.name || `Trinetra v${APP_VERSION}`,
      publishedAt: data.published_at || new Date().toISOString(),
      htmlUrl: data.html_url || fallback.htmlUrl,
      body: data.body || "",
      windowsAsset: windowsAssetRaw
        ? {
            name: windowsAssetRaw.name,
            size: windowsAssetRaw.size,
            downloadUrl: windowsAssetRaw.browser_download_url,
            checksum: windowsChecksum,
          }
        : undefined,
      androidAsset: androidAssetRaw
        ? {
            name: androidAssetRaw.name,
            size: androidAssetRaw.size,
            downloadUrl: androidAssetRaw.browser_download_url,
          }
        : undefined,
      checksumsUrl: checksumAssetRaw?.browser_download_url,
      hasRelease: true,
    };

    try {
      window.sessionStorage.setItem(
        CACHE_KEY_RELEASES,
        JSON.stringify({ timestamp: Date.now(), data: releaseInfo })
      );
    } catch {
      // sessionStorage write error ignored
    }

    return releaseInfo;
  } catch {
    return fallback;
  }
}
