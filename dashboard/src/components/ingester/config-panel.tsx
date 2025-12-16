"use client";

/**
 * Configuration panel with sliders for ingester parameters
 */

import { Slider } from "@/components/ui/slider";
import { useLogStore } from "@/stores/log-store";
import { CONFIG_RANGES, DEFAULT_CONFIG } from "@/lib/types";

interface ConfigPanelProps {
  name: string;
  disabled?: boolean;
}

// Helper component for a single slider
function ConfigSlider({
  label,
  value,
  min,
  max,
  step,
  disabled,
  onChange,
  unit = "",
  decimals = 0,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  disabled?: boolean;
  onChange: (value: number) => void;
  unit?: string;
  decimals?: number;
}) {
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono">
          {decimals > 0 ? value.toFixed(decimals) : value}{unit}
        </span>
      </div>
      <Slider
        value={[value]}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onValueChange={([v]) => onChange(v)}
        className="w-full"
      />
    </div>
  );
}

export function ConfigPanel({ name, disabled }: ConfigPanelProps) {
  const { config, setConfig } = useLogStore();
  const ingesterConfig = config[name] || {};

  // World Simulator
  if (name === "world") {
    const ranges = CONFIG_RANGES.world;
    const defaults = DEFAULT_CONFIG.world;
    return (
      <div className="space-y-4 py-3">
        <ConfigSlider
          label="Fleet Size"
          value={ingesterConfig.ships ?? defaults.ships}
          {...ranges.ships}
          disabled={disabled}
          onChange={(v) => setConfig(name, "ships", v)}
        />
        <ConfigSlider
          label="Dark Ships"
          value={ingesterConfig.darkPct ?? defaults.darkPct}
          {...ranges.darkPct}
          disabled={disabled}
          onChange={(v) => setConfig(name, "darkPct", v)}
          unit="%"
        />
        <ConfigSlider
          label="Speed Multiplier"
          value={ingesterConfig.speedMult ?? defaults.speedMult}
          {...ranges.speedMult}
          disabled={disabled}
          onChange={(v) => setConfig(name, "speedMult", v)}
          unit="x"
        />
        <p className="text-xs text-muted-foreground mt-2">
          60x = 1 real second equals 1 simulated minute
        </p>
      </div>
    );
  }

  // AIS Ingester
  if (name === "ais") {
    const ranges = CONFIG_RANGES.ais;
    const defaults = DEFAULT_CONFIG.ais;
    return (
      <div className="space-y-4 py-3">
        <ConfigSlider
          label="Ships to Track"
          value={ingesterConfig.ships ?? defaults.ships}
          {...ranges.ships}
          disabled={disabled}
          onChange={(v) => setConfig(name, "ships", v)}
        />
        <ConfigSlider
          label="Update Rate"
          value={ingesterConfig.rate ?? defaults.rate}
          {...ranges.rate}
          disabled={disabled}
          onChange={(v) => setConfig(name, "rate", v)}
          unit=" Hz"
          decimals={1}
        />
      </div>
    );
  }

  // Radar Ingester
  if (name === "radar") {
    const ranges = CONFIG_RANGES.radar;
    const defaults = DEFAULT_CONFIG.radar;
    return (
      <div className="space-y-4 py-3">
        <ConfigSlider
          label="Active Tracks"
          value={ingesterConfig.tracks ?? defaults.tracks}
          {...ranges.tracks}
          disabled={disabled}
          onChange={(v) => setConfig(name, "tracks", v)}
        />
        <ConfigSlider
          label="Update Rate"
          value={ingesterConfig.rate ?? defaults.rate}
          {...ranges.rate}
          disabled={disabled}
          onChange={(v) => setConfig(name, "rate", v)}
          unit=" Hz"
          decimals={1}
        />
        <ConfigSlider
          label="Detection Range"
          value={ingesterConfig.rangePct ?? defaults.rangePct}
          {...ranges.rangePct}
          disabled={disabled}
          onChange={(v) => setConfig(name, "rangePct", v)}
          unit="%"
        />
      </div>
    );
  }

  // Satellite Ingester
  if (name === "satellite") {
    const ranges = CONFIG_RANGES.satellite;
    const defaults = DEFAULT_CONFIG.satellite;
    return (
      <div className="space-y-4 py-3">
        <ConfigSlider
          label="Pass Rate"
          value={ingesterConfig.rate ?? defaults.rate}
          {...ranges.rate}
          disabled={disabled}
          onChange={(v) => setConfig(name, "rate", v)}
          unit=" Hz"
          decimals={2}
        />
        <ConfigSlider
          label="Cloud Cover"
          value={ingesterConfig.cloudCover ?? defaults.cloudCover}
          {...ranges.cloudCover}
          disabled={disabled}
          onChange={(v) => setConfig(name, "cloudCover", v)}
          unit="%"
        />
        <ConfigSlider
          label="Vessels/Pass"
          value={ingesterConfig.vesselsPerPass ?? defaults.vesselsPerPass}
          {...ranges.vesselsPerPass}
          disabled={disabled}
          onChange={(v) => setConfig(name, "vesselsPerPass", v)}
        />
        <p className="text-xs text-muted-foreground mt-2">
          SAR ignores clouds, Optical affected by cloud cover
        </p>
      </div>
    );
  }

  // Drone Ingester
  if (name === "drone") {
    const ranges = CONFIG_RANGES.drone;
    const defaults = DEFAULT_CONFIG.drone;
    return (
      <div className="space-y-4 py-3">
        <ConfigSlider
          label="Frame Rate"
          value={ingesterConfig.rate ?? defaults.rate}
          {...ranges.rate}
          disabled={disabled}
          onChange={(v) => setConfig(name, "rate", v)}
          unit=" Hz"
          decimals={1}
        />
        <ConfigSlider
          label="Detections/Frame"
          value={ingesterConfig.detectionsPerFrame ?? defaults.detectionsPerFrame}
          {...ranges.detectionsPerFrame}
          disabled={disabled}
          onChange={(v) => setConfig(name, "detectionsPerFrame", v)}
        />
        <p className="text-xs text-muted-foreground mt-2">
          3 drones patrol 5 zones across Indian Ocean
        </p>
      </div>
    );
  }

  // Fusion Engine
  if (name === "fusion") {
    const ranges = CONFIG_RANGES.fusion;
    const defaults = DEFAULT_CONFIG.fusion;
    return (
      <div className="space-y-4 py-3">
        <ConfigSlider
          label="Processing Rate"
          value={ingesterConfig.rate ?? defaults.rate}
          {...ranges.rate}
          disabled={disabled}
          onChange={(v) => setConfig(name, "rate", v)}
          unit=" Hz"
          decimals={1}
        />
        <p className="text-xs text-muted-foreground mt-2">
          Higher rate = more responsive tracking but more CPU usage.
          2 Hz recommended for real-time correlation.
        </p>
      </div>
    );
  }

  return null;
}
