import React, { useState } from "react";
import { CameraDeviceInfo } from "../types/api";

interface DeviceSelectorProps {
  devices: CameraDeviceInfo[];
  selectedDeviceIndex: number | string;
  cameraActive: boolean;
  onSelectDevice: (index: number | string) => void;
  onRefreshDevices: () => void;
}

export const DeviceSelector: React.FC<DeviceSelectorProps> = ({
  devices,
  selectedDeviceIndex,
  cameraActive,
  onSelectDevice,
  onRefreshDevices,
}) => {
  const isNetworkStream = typeof selectedDeviceIndex === "string";
  const [streamUrl, setStreamUrl] = useState<string>(
    typeof selectedDeviceIndex === "string" ? selectedDeviceIndex : "http://192.168.1.100:81/stream"
  );
  const [isNetworkMode, setIsNetworkMode] = useState<boolean>(isNetworkStream);

  const handleModeChange = (network: boolean) => {
    setIsNetworkMode(network);
    if (!network) {
      onSelectDevice(0);
    } else {
      onSelectDevice(streamUrl);
    }
  };

  const handleApplyUrl = () => {
    if (streamUrl.trim()) {
      onSelectDevice(streamUrl.trim());
    }
  };

  return (
    <div className="device-selector-container" role="region" aria-label="Camera Hardware Selector">
      <div className="device-selector-mode-tabs">
        <button
          type="button"
          className={`btn btn-sm ${!isNetworkMode ? "btn-primary" : "btn-outline"}`}
          onClick={() => handleModeChange(false)}
          disabled={cameraActive}
          aria-pressed={!isNetworkMode}
        >
          📹 USB / Webcam
        </button>
        <button
          type="button"
          className={`btn btn-sm ${isNetworkMode ? "btn-primary" : "btn-outline"}`}
          onClick={() => handleModeChange(true)}
          disabled={cameraActive}
          aria-pressed={isNetworkMode}
        >
          📡 Network Stream (ESP32-CAM)
        </button>
      </div>

      {!isNetworkMode ? (
        <div className="device-selector-controls">
          <label htmlFor="camera-device-select" className="device-select-label">
            Camera Device:
          </label>
          <select
            id="camera-device-select"
            className="device-select-dropdown"
            value={typeof selectedDeviceIndex === "number" ? selectedDeviceIndex : 0}
            disabled={cameraActive}
            onChange={(e) => onSelectDevice(Number(e.target.value))}
            aria-label="Select camera hardware device"
            aria-describedby="device-select-help"
          >
            {devices.length === 0 ? (
              <option value={0}>Camera 0 (Default)</option>
            ) : (
              devices.map((device) => (
                <option
                  key={device.index}
                  value={device.index}
                  disabled={!device.is_available && device.status !== "in_use"}
                >
                  {device.name} — [{device.status.toUpperCase()}]
                </option>
              ))
            )}
          </select>

          <button
            type="button"
            className="btn btn-outline btn-sm"
            onClick={onRefreshDevices}
            disabled={cameraActive}
            aria-label="Refresh connected camera list"
          >
            🔄 Scan Cameras
          </button>
        </div>
      ) : (
        <div className="device-selector-controls network-stream-controls">
          <label htmlFor="camera-stream-url" className="device-select-label">
            Stream URL:
          </label>
          <input
            id="camera-stream-url"
            type="text"
            className="device-stream-input"
            value={streamUrl}
            disabled={cameraActive}
            onChange={(e) => setStreamUrl(e.target.value)}
            placeholder="http://192.168.1.100:81/stream"
            aria-label="ESP32-CAM or IP Camera stream URL"
          />
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={handleApplyUrl}
            disabled={cameraActive || !streamUrl.trim()}
          >
            Set URL
          </button>
        </div>
      )}

      <p id="device-select-help" className="device-select-hint">
        {cameraActive
          ? "Stop camera before switching devices to safely release hardware locks."
          : isNetworkMode
          ? "Enter your ESP32-CAM HTTP/MJPEG URL (e.g. http://<ip>:81/stream) or RTSP stream URL."
          : "Select your built-in webcam or external USB camera before starting video capture."}
      </p>
    </div>
  );
};
