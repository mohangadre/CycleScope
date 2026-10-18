"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { preparePriceData, type PriceChartPoint } from "./data";
import {
  chartColors,
  chartMargin,
  formatCurrency,
  formatSession,
  priceTooltip,
  tooltipStyle,
} from "./format";

export interface HistoricalPriceChartProps {
  points: readonly PriceChartPoint[];
  ticker: string;
}

export function HistoricalPriceChart({ points, ticker }: HistoricalPriceChartProps) {
  const data = preparePriceData(points);
  if (data.length === 0) {
    return <p className="chart-empty">No valid historical observations to chart.</p>;
  }

  return (
    <div>
      <div
        role="img"
        aria-label={`${ticker} observed adjusted close in US dollars per share over ${data.length} trading sessions. Session dates are equally spaced.`}
        style={{ height: 320, width: "100%", minWidth: 0 }}
      >
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <LineChart data={data} margin={chartMargin} accessibilityLayer>
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
                value: "Observed trading sessions",
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
              formatter={(value) => [priceTooltip(value), "Observed close"]}
              contentStyle={tooltipStyle}
              labelStyle={{ color: "#e5e7eb", marginBottom: 6 }}
              cursor={{ stroke: chartColors.text, strokeDasharray: "3 3" }}
            />
            <Line
              type="linear"
              dataKey="close"
              name="Observed adjusted close"
              stroke={chartColors.observed}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: "#0b1220" }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p style={{ color: "var(--muted, #94a3b8)", fontSize: 12, margin: "8px 0 0" }}>
        <span aria-hidden="true" style={{ color: chartColors.observed }}>
          ●{" "}
        </span>
        Observed adjusted close · USD per share · trading sessions equally spaced
      </p>
    </div>
  );
}
