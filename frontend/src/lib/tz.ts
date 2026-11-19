/** Minimal timezone helpers so the schedule renders in the clinic's timezone, not the browser's. */

const fmtCache = new Map<string, Intl.DateTimeFormat>();
function fmt(tz: string) {
  let f = fmtCache.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
    fmtCache.set(tz, f);
  }
  return f;
}

export type ZParts = { y: number; m: number; d: number; h: number; min: number };

export function zoned(date: Date | string, tz: string): ZParts {
  const parts = Object.fromEntries(fmt(tz).formatToParts(typeof date === "string" ? new Date(date) : date).map((p) => [p.type, p.value]));
  return { y: +parts.year, m: +parts.month, d: +parts.day, h: +parts.hour % 24, min: +parts.minute };
}

function offsetMs(utcMs: number, tz: string) {
  const p = zoned(new Date(utcMs), tz);
  return Date.UTC(p.y, p.m - 1, p.d, p.h, p.min) - Math.floor(utcMs / 60000) * 60000;
}

/** Wall-clock date (YYYY-MM-DD) + minutes after midnight in tz → UTC Date. */
export function fromZoned(dateStr: string, minutes: number, tz: string): Date {
  const [y, m, d] = dateStr.split("-").map(Number);
  const guess = Date.UTC(y, m - 1, d, Math.floor(minutes / 60), minutes % 60);
  let ts = guess - offsetMs(guess, tz);
  ts = guess - offsetMs(ts, tz);
  return new Date(ts);
}

export const ymd = (p: { y: number; m: number; d: number }) => `${p.y}-${String(p.m).padStart(2, "0")}-${String(p.d).padStart(2, "0")}`;

export function todayIn(tz: string) {
  return ymd(zoned(new Date(), tz));
}

/** Add days to a YYYY-MM-DD string (calendar arithmetic, tz-independent). */
export function addDays(dateStr: string, n: number) {
  const [y, m, d] = dateStr.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + n));
  return ymd({ y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: t.getUTCDate() });
}

export function weekday(dateStr: string) {
  const [y, m, d] = dateStr.split("-").map(Number);
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7; // 0 = Monday
}

export function minutesOfDay(date: Date | string, tz: string) {
  const p = zoned(date, tz);
  return p.h * 60 + p.min;
}

export function hhmm(minutes: number) {
  const h = Math.floor(minutes / 60), m = minutes % 60;
  const ampm = h >= 12 ? "PM" : "AM";
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${ampm}`;
}

export function toISOWithZone(date: Date) {
  return date.toISOString();
}
