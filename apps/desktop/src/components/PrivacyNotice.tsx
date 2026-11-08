import React from "react";

export const PrivacyNotice: React.FC = () => {
  return (
    <footer className="notices-section" role="contentinfo" aria-label="Privacy and Safety Information">
      <div className="notice-card privacy-card">
        <h2 className="notice-title">🔒 Privacy Assurance</h2>
        <p className="notice-body">
          Video frames are processed strictly in volatile memory on your local machine
          (<code>127.0.0.1</code>) and are <strong>never saved to disk, uploaded to the cloud, or shared</strong>.
          The camera will never activate without your explicit click.
        </p>
      </div>

      <div className="notice-card safety-card">
        <h2 className="notice-title">⚠️ Essential Safety Warning</h2>
        <p className="notice-body">
          Trinetra is an open-source assistive technology platform.
          It is <strong>NOT a certified medical device</strong>. It must
          <strong> never replace</strong> a white cane, guide dog, or orientation &amp; mobility training.
        </p>
      </div>

      <div
        style={{
          textAlign: "center",
          padding: "16px 0 8px",
          color: "var(--text-muted, #94a3b8)",
          fontSize: "0.82rem",
          lineHeight: 1.6,
          borderTop: "1px solid var(--border-color, #334155)",
          marginTop: "16px",
        }}
      >
        <strong>Trinetra (त्रिनेत्र) v0.2.0</strong> • Open-Source Assistive Vision &amp; Communication Platform
        <br />
        Licensed under Apache-2.0 • 100% Offline On-Device Architecture
      </div>
    </footer>
  );
};
