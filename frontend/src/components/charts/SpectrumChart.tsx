"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { prepareSpectrumData, type SpectrumChartPoint } from "./data";
import { chartColors, chartMargin, formatPower, tooltipStyle } from "./format";

export interface SpectrumChartProps {
  points: readonly SpectrumChartPoint[];
  candidatePeriods?: readonly number[];
}

export function SpectrumChart({ points, candidatePeriods = [] }: SpectrumChartProps) {
  const data = prepareSpectrumData(points);
  if (data.length === 0) {
    return <p className="chart-empty">No valid spectral observations to chart.</p>;
  }
  const minPeriod = data[0].period_sessions;
  const maxPeriod = data[data.length - 1].period_sessions;
  const candidates = candidatePeriods.filter(
    (period) => Number.isFinite(period) && period >= minPeriod && period <= maxPeriod,
  );

  return (
    <div>
      <div
        role="img"
        aria-label="One-sided spectral power density versus candidate period in trading sessions. Historical spectral peaks have not been tested for statistical significance."
        style={{ height: 300, width: "100%", minWidth: 0 }}
      >
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <AreaChart data={data} margin={chartMargin} accessibilityLayer>
            <CartesianGrid stroke={chartColors.grid} vertical={false} strokeDasharray="3 5" />
            <XAxis
              dataKey="period_sessions"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(value: number) => Number(value.toPrecision(3)).toString()}
              tick={{ fill: chartColors.text, fontSize: 11 }}
              minTickGap={32}
              tickLine={false}
              axisLine={false}
              label={{
                value: "Period · trading sessions",
                position: "bottom",
                fill: chartColors.text,
                fontSize: 11,
              }}
            />
            <YAxis
              domain={[0, "auto"]}
              tickFormatter={formatPower}
              width={64}
              tick={{ fill: chartColors.text, fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              labelFormatter={(label) => `${Number(label).toFixed(2)} trading sessions`}
              formatter={(value) => [
                typeof value === "number" ? formatPower(value) : "Unavailable",
                "Power density",
              ]}
              contentStyle={tooltipStyle}
              labelStyle={{ color: "#e5e7eb", marginBottom: 6 }}
              cursor={{ stroke: chartColors.text, strokeDasharray: "3 3" }}
            />
            {candidates.map((period) => (
              <ReferenceLine
                key={period}
                x={period}
                stroke={chartColors.peak}
                strokeDasharray="3 4"
                strokeOpacity={0.75}
              />
            ))}
            <Area
              type="linear"
              dataKey="power"
              name="Power density"
              stroke={chartColors.projected}
              strokeWidth={2}
              fill={chartColors.projected}
              fillOpacity={0.12}
              dot={false}
              activeDot={{ r: 4, stroke: "#0b1220", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p style={{ color: "var(--muted, #94a3b8)", fontSize: 12, margin: "8px 0 0" }}>
        One-sided PSD · input units² per cycles/session
        {candidates.length > 0 ? " · amber guides mark historical candidates" : ""}
      </p>
    </div>
  );
}
