const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const shortDate = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

export function formatCurrency(value: number): string {
  return currency.format(value);
}

export function formatSession(value: string): string {
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.valueOf()) ? shortDate.format(parsed) : value;
}

export function formatPower(value: number): string {
  if (value === 0) return "0";
  return value < 0.001 || value >= 1000 ? value.toExponential(2) : value.toPrecision(3);
}

export function priceTooltip(value: unknown): string {
  if (typeof value === "number") return formatCurrency(value);
  if (Array.isArray(value) && value.length === 2) {
    const [lower, upper] = value as unknown[];
    if (typeof lower === "number" && typeof upper === "number") {
      return `${formatCurrency(lower)} – ${formatCurrency(upper)}`;
    }
  }
  return "Unavailable";
}

export const chartColors = {
  observed: "#41d7b0",
  projected: "#79a9ff",
  peak: "#f2c46f",
  trough: "#ba9bff",
  text: "#94a3b8",
  grid: "#223044",
};

export const tooltipStyle = {
  backgroundColor: "#111c2e",
  border: "1px solid #344157",
  borderRadius: 8,
  color: "#e5e7eb",
  fontSize: 12,
};

export const chartMargin = { top: 24, right: 12, bottom: 26, left: 8 };
