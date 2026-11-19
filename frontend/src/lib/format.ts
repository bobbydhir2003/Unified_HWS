import { differenceInYears, format, formatDistanceToNowStrict, isToday, isYesterday, parseISO } from "date-fns";

const d = (v: string | Date) => (typeof v === "string" ? parseISO(v) : v);

export function age(dob: string): number {
  return differenceInYears(new Date(), parseISO(dob));
}

export function fmtDate(v?: string | Date | null) {
  return v ? format(d(v), "MMM d, yyyy") : "—";
}

export function fmtDob(dob: string) {
  return `${format(parseISO(dob), "MM/dd/yyyy")} (${age(dob)}y)`;
}

export function fmtTime(v?: string | Date | null, tz?: string) {
  if (!v) return "—";
  return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone: tz }).format(d(v));
}

export function fmtDateTime(v?: string | Date | null) {
  if (!v) return "—";
  const x = d(v);
  if (isToday(x)) return `Today ${format(x, "h:mm a")}`;
  if (isYesterday(x)) return `Yesterday ${format(x, "h:mm a")}`;
  return format(x, "MMM d, yyyy h:mm a");
}

export function fromNow(v?: string | Date | null) {
  return v ? formatDistanceToNowStrict(d(v), { addSuffix: true }) : "—";
}

export function minutesSince(v?: string | null) {
  if (!v) return null;
  return Math.max(0, Math.round((Date.now() - d(v).getTime()) / 60000));
}

export const sexShort = (s: string) => ({ female: "F", male: "M", intersex: "X", unknown: "U" })[s] ?? "U";

export function cToF(c?: string | number | null) {
  if (c === null || c === undefined || c === "") return null;
  return Math.round((Number(c) * 9) / 5 * 10 + 320) / 10;
}

export function fmtMoney(cents?: number | null) {
  if (cents === null || cents === undefined) return "—";
  return (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

/** One key per user intent: reuse it if the same action is retried (e.g. after a network error). */
export function newIdempotencyKey(scope: string) {
  return `${scope}-${crypto.randomUUID()}`;
}
