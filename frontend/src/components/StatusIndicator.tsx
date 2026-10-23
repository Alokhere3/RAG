import React from "react";
import type { ComponentStatus } from "../types/health";

interface StatusIndicatorProps {
  label: string;
  status: ComponentStatus;
  healthyLabel?: string;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  label,
  status,
  healthyLabel = "Healthy",
}) => {
  const getBadgeConfig = () => {
    switch (status) {
      case "healthy":
        return {
          text: healthyLabel,
          colorClass: "status-healthy",
          dotColor: "#10B981",
        };
      case "unavailable":
      case "error":
        return {
          text: "Unavailable",
          colorClass: "status-unavailable",
          dotColor: "#EF4444",
        };
      case "loading":
      default:
        return {
          text: "Checking...",
          colorClass: "status-loading",
          dotColor: "#9CA3AF",
        };
    }
  };

  const badge = getBadgeConfig();

  return (
    <div className="status-row" data-testid={`status-row-${label.toLowerCase()}`}>
      <span className="status-label">{label}</span>
      <div className={`status-badge ${badge.colorClass}`}>
        <span
          className="status-dot"
          style={{ backgroundColor: badge.dotColor }}
          aria-hidden="true"
        />
        <span className="status-text">{badge.text}</span>
      </div>
    </div>
  );
};
