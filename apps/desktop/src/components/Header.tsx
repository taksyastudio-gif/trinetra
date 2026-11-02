import React from "react";

interface HeaderProps {
  rightSlot?: React.ReactNode;
}

export const Header: React.FC<HeaderProps> = ({ rightSlot }) => {
  return (
    <header className="app-header" role="banner">
      <div className="header-top-row">
        <div className="header-brand">
          <h1 className="header-title">TRINETRA</h1>
          <span className="header-badge" aria-label="System stage: Core Pipeline">
            Vision & Voice
          </span>
        </div>
        {rightSlot && <div className="header-actions">{rightSlot}</div>}
      </div>
      <p className="header-subtitle">
        Assistive vision and spatial awareness platform for blind and visually impaired individuals.
      </p>
    </header>
  );
};
