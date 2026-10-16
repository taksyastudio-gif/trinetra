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
          Trinetra is an experimental assistive technology research prototype.
          It is <strong>NOT a certified medical device or mobility aid</strong>. It must
          <strong> never replace</strong> your white cane, guide dog, or orientation &amp; mobility training.
        </p>
      </div>
    </footer>
  );
};
