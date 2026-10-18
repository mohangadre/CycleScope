/** Server-side public default from a successfully selected ingestion cutoff. */
function configuredDate(name: string): string | undefined {
  const value = process.env[name];
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const parsed = new Date(`${value}T00:00:00Z`);
  if (
    !Number.isFinite(parsed.valueOf()) ||
    parsed.toISOString().slice(0, 10) !== value ||
    value < "1990-01-01" ||
    value > "2035-12-31"
  )
    return undefined;
  return value;
}

export const configuredAsOf = () => configuredDate("CYCLESCOPE_DEFAULT_AS_OF");
export const configuredStart = () => configuredDate("CYCLESCOPE_DEFAULT_START");
