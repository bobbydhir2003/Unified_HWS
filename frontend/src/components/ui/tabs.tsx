import { Tabs as T } from "radix-ui";
import * as React from "react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

/**
 * Two tab styles only:
 *  - Page tabs (underline): sections of a page — Radix `Tabs` below, or routed `PageTabs`.
 *  - `Segmented`: filters / view switches inside a card or toolbar.
 */
export const Tabs = T.Root;
export function TabsList({ className, ...props }: React.ComponentProps<typeof T.List>) {
  return <T.List className={cn("flex max-w-full items-end gap-6 overflow-x-auto border-b scrollbar-thin", className)} {...props} />;
}
const pageTab =
  "-mb-px inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap border-b-2 border-transparent px-0.5 pb-2.5 pt-1.5 text-body font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 [&_svg]:size-4";
const pageTabActive = "border-primary font-semibold text-heading";
export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof T.Trigger>) {
  return <T.Trigger className={cn(pageTab, "data-[state=active]:border-primary data-[state=active]:font-semibold data-[state=active]:text-heading", className)} {...props} />;
}
export function TabsContent({ className, ...props }: React.ComponentProps<typeof T.Content>) {
  return <T.Content className={cn("mt-4 outline-none data-[state=active]:animate-in", className)} {...props} />;
}

/** Count shown next to a tab label. */
export function TabCount({ n, tone }: { n: number | string; tone?: "danger" }) {
  return <span className={cn("rounded-full px-1.5 text-label font-semibold tabular", tone === "danger" ? "bg-destructive-soft text-destructive" : "bg-muted text-muted-foreground")}>{n}</span>;
}

/** Routed page tabs (each tab is a URL). */
export function PageTabs({ items, label, className }: {
  items: { to: string; label: React.ReactNode; icon?: React.ElementType; end?: boolean; count?: number }[]; label: string; className?: string;
}) {
  return (
    <nav aria-label={label} className={cn("flex max-w-full items-end gap-6 overflow-x-auto border-b scrollbar-thin", className)}>
      {items.map((it) => (
        <NavLink key={it.to} to={it.to} end={it.end} className={({ isActive }) => cn(pageTab, isActive && pageTabActive)}>
          {it.icon && <it.icon />}{it.label}{it.count != null && <TabCount n={it.count} />}
        </NavLink>
      ))}
    </nav>
  );
}

/** Segmented filter. Buttons expose their state with aria-pressed. */
export function Segmented<V extends string>({ value, onChange, options, label, className, size = "sm" }: {
  value: V; onChange: (v: V) => void; options: { value: V; label: React.ReactNode; count?: number; testId?: string }[];
  label: string; className?: string; size?: "sm" | "md";
}) {
  return (
    <div role="group" aria-label={label} className={cn("inline-flex max-w-full flex-wrap overflow-hidden rounded-md border border-control bg-card", className)}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)} data-testid={o.testId}
          className={cn("inline-flex items-center gap-1.5 border-r border-control px-3 font-medium text-muted-foreground last:border-r-0 hover:bg-muted hover:text-foreground focus-visible:relative focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
            size === "sm" ? "h-8 text-table" : "h-9 text-body",
            value === o.value && "bg-accent font-semibold text-accent-foreground hover:bg-accent hover:text-accent-foreground")}>
          {o.label}{o.count != null && <span className="tabular opacity-80">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}
