"use client";

import {
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SectorResult } from "@/lib/api";
import { chartColors, formatSession, tooltipStyle } from "./format";

export const sectorColors = [
  "#41d7b0",
  "#79a9ff",
  "#f2c46f",
  "#b29aff",
  "#ff9da5",
  "#7dd3fc",
  "#e9a8df",
  "#b5d774",
];

export function SectorRotationChart({ result }: { result: SectorResult }) {
  const points = result.sectors.map((sector) => ({
    ticker: sector.ticker,
    strength: sector.points.at(-1)!.smoothed_normalized_rs,
    momentum: 100 * sector.points.at(-1)!.momentum_log_rs,
    quadrant: sector.points.at(-1)!.quadrant,
  }));
  const dx = Math.max(0.5, ...points.map((point) => Math.abs(point.strength - 100))) * 1.2;
  const dy = Math.max(0.05, ...points.map((point) => Math.abs(point.momentum))) * 1.2;
  return (
    <div
      role="img"
      aria-label="Observed sector rotation: smoothed normalized relative strength against SPY on the horizontal axis, trailing log relative change times 100 on the vertical axis. These are descriptive quadrants, not forecasts."
      className="sector-chart"
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <ScatterChart margin={{ top: 25, right: 24, bottom: 32, left: 5 }} accessibilityLayer>
          <CartesianGrid stroke={chartColors.grid} strokeDasharray="3 5" />
          <XAxis
            type="number"
            dataKey="strength"
            name="Smoothed RS index"
            domain={[100 - dx, 100 + dx]}
            tickFormatter={(x: number) => x.toFixed(1)}
            tick={{ fill: chartColors.text, fontSize: 11 }}
            label={{
              value: "Smoothed relative strength · reference = 100",
              position: "bottom",
              fill: chartColors.text,
              fontSize: 11,
            }}
          />
          <YAxis
            type="number"
            dataKey="momentum"
            name="Log relative change ×100"
            domain={[-dy, dy]}
            tickFormatter={(x: number) => x.toFixed(2)}
            tick={{ fill: chartColors.text, fontSize: 11 }}
            width={65}
          />
          <ReferenceArea x1={100} x2={100 + dx} y1={0} y2={dy} fill="#41d7b0" fillOpacity={0.055} />
          <ReferenceArea x1={100 - dx} x2={100} y1={0} y2={dy} fill="#79a9ff" fillOpacity={0.055} />
          <ReferenceArea
            x1={100}
            x2={100 + dx}
            y1={-dy}
            y2={0}
            fill="#f2c46f"
            fillOpacity={0.055}
          />
          <ReferenceArea
            x1={100 - dx}
            x2={100}
            y1={-dy}
            y2={0}
            fill="#ff9da5"
            fillOpacity={0.055}
          />
          <ReferenceLine x={100} stroke="#718397" strokeDasharray="4 4" />
          <ReferenceLine y={0} stroke="#718397" strokeDasharray="4 4" />
          <Tooltip
            contentStyle={tooltipStyle}
            formatter={(v, name) => [
              typeof v === "number" ? v.toFixed(4) : String(v),
              String(name),
            ]}
          />
          <Scatter data={points} name="Sector" isAnimationActive={false}>
            {points.map((point, i) => (
              <Cell key={point.ticker} fill={sectorColors[i]} />
            ))}
            <LabelList dataKey="ticker" position="top" fill="#e7edf5" fontSize={11} />
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SectorHistoryChart({ result }: { result: SectorResult }) {
  const rows = result.sectors[0].points.map((point, index) =>
    Object.assign(
      { session_date: point.session_date },
      ...result.sectors.map((sector) => ({ [sector.ticker]: sector.points[index].normalized_rs })),
    ),
  );
  return (
    <div
      role="img"
      aria-label="Historical normalized sector to SPY price ratios. Every series begins at 100 on the reference session. Dates are observed exchange sessions."
      className="sector-chart"
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <LineChart
          data={rows}
          margin={{ top: 15, right: 16, bottom: 20, left: 5 }}
          accessibilityLayer
        >
          <CartesianGrid stroke={chartColors.grid} strokeDasharray="3 5" vertical={false} />
          <XAxis
            dataKey="session_date"
            tickFormatter={formatSession}
            tick={{ fill: chartColors.text, fontSize: 11 }}
            minTickGap={45}
          />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fill: chartColors.text, fontSize: 11 }}
            width={55}
          />
          <ReferenceLine y={100} stroke="#718397" strokeDasharray="4 4" />
          <Tooltip
            contentStyle={tooltipStyle}
            formatter={(v, name) => [
              typeof v === "number" ? v.toFixed(3) : String(v),
              String(name),
            ]}
          />
          <Legend wrapperStyle={{ fontSize: 11, paddingTop: 12 }} />
          {result.sectors.map((sector, index) => (
            <Line
              key={sector.ticker}
              type="linear"
              dataKey={sector.ticker}
              stroke={sectorColors[index]}
              strokeWidth={1.7}
              dot={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
