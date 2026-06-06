export function formatLocalDateTime(ms: number): string {
  const date = new Date(ms);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function defaultTrendRangeMs(days = 90): { fromMs: number; toMs: number } {
  const to = new Date();
  to.setHours(23, 59, 59, 999);
  const from = new Date(to);
  from.setDate(from.getDate() - days);
  from.setHours(0, 0, 0, 0);
  return { fromMs: from.getTime(), toMs: to.getTime() };
}

export function parseTimeToMs(value: string | number): number {
  if (typeof value === "number") return value * 1000;
  return new Date(value).getTime();
}
