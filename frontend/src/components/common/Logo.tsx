import { PRODUCT_NAME } from "@/lib/legal";
import { cn } from "@/lib/utils";

/**
 * HMS Workflows mark: one continuous route through five points — a "W" for Workflows and a patient's path through
 * departments — ending at a teal destination node. Navy tile adapts to dark mode via --brand-navy. No medical cross.
 */
export function LogoMark({ size = 28, className, title }: { size?: number; className?: string; title?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" className={cn("shrink-0", className)} role={title ? "img" : undefined} aria-label={title} aria-hidden={title ? undefined : true}>
      <rect width="36" height="36" rx="8" fill="var(--brand-navy)" />
      <path d="M8 12.5 12.6 24 18 15.5 23.4 24 28 12.5" fill="none" stroke="#FFFFFF" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="28" cy="12.5" r="2.6" fill="var(--brand-teal)" />
    </svg>
  );
}

/** "HMS Workflows" wordmark: HMS semibold, Workflows regular, same ink. `inverse` for dark photographic backgrounds. */
export function Wordmark({ size = 28, className, inverse, tagline }: { size?: number; className?: string; inverse?: boolean; tagline?: string }) {
  const [a, ...rest] = PRODUCT_NAME.split(" ");
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark size={size} />
      <span className="leading-tight">
        <span className={cn("block text-section font-semibold tracking-tight", inverse ? "text-white" : "text-heading")}>
          {a} <span className={cn("font-normal", inverse ? "text-white/85" : "text-muted-foreground")}>{rest.join(" ")}</span>
        </span>
        {tagline && <span className={cn("block text-label", inverse ? "text-white/75" : "text-muted-foreground")}>{tagline}</span>}
      </span>
    </span>
  );
}
