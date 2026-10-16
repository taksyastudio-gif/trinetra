import React from "react";

export const Header: React.FC = () => {
  return (
    <header className="app-header" role="banner">
      <div className="header-brand">
        <h1 className="header-title">TRINETRA</h1>
        <span className="header-badge" aria-label="System stage: Sprint 1 Core Pipeline">
          Sprint 1: Vision Foundation
        </span>
      </div>
      <p className="header-subtitle">
        Assistive vision and spatial awareness platform for blind and visually impaired individuals.
      </p>
    </header>
  );
};
