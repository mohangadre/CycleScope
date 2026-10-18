"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  buildForecastChartData,
  visibleTurningWindows,
  type ForecastChartPoint,
  type ForecastTurningWindow,
  type PriceChartPoint,
} from "./data";
import {
  chartColors,
  chartMargin,
  formatCurrency,
  formatSession,
  priceTooltip,
  tooltipStyle,
} from "./format";

export interface ForecastChartProps {
  history: readonly PriceChartPoint[];
  points: readonly ForecastChartPoint[];
  /** Actual last training session, from forecast_origin rather than requested as_of. */
  asOf: string;
  turningWindows?: readonly ForecastTurningWindow[];
  ticker: string;
}

export function ForecastChart({
  history,
  points,
  asOf,
  turningWindows = [],
  ticker,
}: ForecastChartProps) {
  const data = buildForecastChartData(history, points, asOf);
  if (data.length === 0 || !data.some((point) => point.session_date > asOf)) {
    return <p className="chart-empty">No valid future projection to chart.</p>;
  }
  const windows = visibleTurningWindows(turningWindows, data, asOf);
  const hasOrigin = data.some(
    (point) => point.session_date === asOf && point.observed !== undefined,
  );

  return (
    <div>
      <div
        role="img"
        aria-label={`${ticker} exploratory forecast in US dollars per share. Observed history is solid teal. Projection is dashed blue after the ${asOf} cutoff. Shading is an uncalibrated uncertainty band. Turning windows are heuristics.`}
        style={{ height: 340, width: "100%", minWidth: 0 }}
      >
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <ComposedChart data={data} margin={chartMargin} accessibilityLayer>
            <CartesianGrid stroke={chartColors.grid} vertical={false} strokeDasharray="3 5" />
            <XAxis
              dataKey="session_date"
              type="category"
              tickFormatter={formatSession}
              minTickGap={42}
              tick={{ fill: chartColors.text, fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              label={{
                value: "Exchange trading sessions",
                position: "bottom",
                fill: chartColors.text,
                fontSize: 11,
              }}
            />
            <YAxis
              domain={["auto", "auto"]}
              tickFormatter={formatCurrency}
              width={72}
              tick={{ fill: chartColors.text, fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              labelFormatter={(label) => `Session ${String(label)}`}
              formatter={(value, name) => [priceTooltip(value), String(name)]}
              contentStyle={tooltipStyle}
              labelStyle={{ color: "#e5e7eb", marginBottom: 6 }}
              cursor={{ stroke: chartColors.text, strokeDasharray: "3 3" }}
            />
            {windows.map((window, index) => (
              <ReferenceArea
                key={`${window.kind}-${window.window_start}-${index}`}
                x1={window.window_start}
                x2={window.window_end}
                fill={window.kind === "peak" ? chartColors.peak : chartColors.trough}
                fillOpacity={0.08}
                strokeOpacity={0}
              />
            ))}
            <Area
              type="linear"
              dataKey="uncertaintyRange"
              name="Uncalibrated band"
              stroke="none"
              fill={chartColors.projected}
              fillOpacity={0.17}
              connectNulls={false}
              activeDot={false}
              isAnimationActive={false}
            />
            <Line
              type="linear"
              dataKey="observed"
              name="Observed close"
              stroke={chartColors.observed}
              strokeWidth={2}
              dot={false}
              connectNulls={false}
              activeDot={{ r: 4, stroke: "#0b1220", strokeWidth: 2 }}
              isAnimationActive={false}
            />
            <Line
              type="linear"
              dataKey="projected"
              name="Exploratory projection"
              stroke={chartColors.projected}
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={false}
              connectNulls={false}
              activeDot={{ r: 4, stroke: "#0b1220", strokeWidth: 2 }}
              isAnimationActive={false}
            />
            {hasOrigin ? (
              <ReferenceLine
                x={asOf}
                stroke={chartColors.text}
                strokeDasharray="4 4"
                label={{
                  value: "Cutoff",
                  position: "insideTopLeft",
                  fill: "#cbd5e1",
                  fontSize: 11,
                }}
              />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div
        style={{
          display: "flex",
          gap: "8px 18px",
          flexWrap: "wrap",
          color: "var(--muted, #94a3b8)",
          fontSize: 12,
          marginTop: 8,
        }}
      >
        <span>
          <span aria-hidden="true" style={{ color: chartColors.observed }}>
            ━{" "}
          </span>
          Observed close
        </span>
        <span>
          <span aria-hidden="true" style={{ color: chartColors.projected }}>
            ┄{" "}
          </span>
          Exploratory projection
        </span>
        <span>
          <span aria-hidden="true" style={{ color: chartColors.projected }}>
            ▧{" "}
          </span>
          Uncalibrated band
        </span>
        {windows.length > 0 ? (
          <span>Faint vertical shading: heuristic peak/trough windows</span>
        ) : null}
      </div>
      {!hasOrigin ? (
        <p style={{ color: "var(--amber, #f2c46f)", fontSize: 12 }}>
          Origin observation is outside the selected history; the projection is shown without a
          historical join.
        </p>
      ) : null}
    </div>
  );
}
