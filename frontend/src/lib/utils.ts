import { type ClassValue, clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/** tailwind-merge must know the HMS Workflows type tokens are font sizes, or `text-label text-muted-foreground` would be
 *  treated as two colours and one silently dropped. */
const twMerge = extendTailwindMerge({
  extend: { theme: { text: ["label", "table", "body", "section", "metric", "title", "display", "lead"] } },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function titleCase(s: string | null | undefined) {
  if (!s) return "";
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
