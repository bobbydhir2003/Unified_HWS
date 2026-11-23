import { AlertTriangle, FlaskConical, Inbox, type LucideIcon, RefreshCw, Sparkles } from "lucide-react";
import * as React from "react";
import { Link, useBlocker } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { ApiError } from "@/lib/api";
import type { AppointmentStatus } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";

/** Page header: optional eyebrow (department · facility · date), one title, a one-line description, actions on the right
 *  (at most one primary), and an optional toolbar row for filters. */
export function PageHeader({
  title, description, actions, children, className, eyebrow, toolbar,
}: { title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; children?: React.ReactNode; className?: string;
  eyebrow?: React.ReactNode; toolbar?: React.ReactNode }) {
  return (
    <div className={cn("mb-5 space-y-3", className)}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          {eyebrow && <p className="mb-0.5 text-label font-medium text-muted-foreground">{eyebrow}</p>}
          <h1 className="text-title font-semibold tracking-tight text-heading">{title}</h1>
          {description && <p className="mt-1 max-w-3xl text-body text-muted-foreground">{description}</p>}
          {children}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {toolbar && <div className="flex flex-wrap items-center gap-2">{toolbar}</div>}
    </div>
  );
}

export function EmptyState({
  icon: Icon = Inbox, title, description, action, className, compact,
}: { icon?: LucideIcon; title: string; description?: React.ReactNode; action?: React.ReactNode; className?: string; compact?: boolean }) {
  if (compact) {
    return (
      <div className={cn("flex items-center gap-2 px-4 py-3 text-table text-muted-foreground", className)}>
        <Icon className="size-4 shrink-0" aria-hidden /><span><span className="font-medium text-foreground">{title}</span>{description ? <> — {description}</> : null}</span>
        {action && <span className="ml-auto">{action}</span>}
      </div>
    );
  }
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 px-6 py-10 text-center", className)}>
      <div className="mb-1 rounded-full bg-muted p-2.5 text-muted-foreground"><Icon className="size-5" /></div>
      <p className="font-medium text-heading">{title}</p>
      {description && <p className="max-w-sm text-table text-muted-foreground">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, retry, className }: { error: unknown; retry?: () => void; className?: string }) {
  const msg = error instanceof Error ? error.message : "Something went wrong.";
  const status = error instanceof ApiError ? error.status : undefined;
  return (
    <div role="alert" className={cn("flex flex-col items-center gap-2 px-6 py-10 text-center", className)}>
      <div className="rounded-full bg-destructive-soft p-3 text-destructive"><AlertTriangle className="size-5" /></div>
      <p className="font-medium">{status === 403 ? "You don't have access to this" : status === 404 ? "Not found" : "Couldn't load this"}</p>
      <p className="max-w-md text-table text-muted-foreground">{msg}</p>
      {retry && status !== 403 && status !== 404 && (
        <Button variant="outline" size="sm" onClick={retry} className="mt-1"><RefreshCw /> Try again</Button>
      )}
    </div>
  );
}

export function LoadingRows({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2 p-4", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-10 w-full" style={{ opacity: 1 - i * 0.12 }} />)}
    </div>
  );
}

export function toastError(err: unknown, fallback = "Something went wrong") {
  toast.error(err instanceof Error ? err.message : fallback);
}

// Blue = active workflow, neutral = waiting/inactive, green = done, amber = needs attention. (Violet is AI-only.)
const APPT_STATUS: Record<AppointmentStatus, { label: string; variant: React.ComponentProps<typeof Badge>["variant"] }> = {
  scheduled: { label: "Scheduled", variant: "neutral" },
  confirmed: { label: "Confirmed", variant: "info" },
  checked_in: { label: "Checked in", variant: "primary" },
  roomed: { label: "Roomed", variant: "primary" },
  in_progress: { label: "With provider", variant: "primary" },
  completed: { label: "Visit done", variant: "success" },
  checked_out: { label: "Checked out", variant: "success" },
  cancelled: { label: "Cancelled", variant: "neutral" },
  no_show: { label: "No-show", variant: "warning" },
};

export function AppointmentStatusBadge({ status, className }: { status: AppointmentStatus; className?: string }) {
  const s = APPT_STATUS[status] ?? { label: titleCase(status), variant: "neutral" as const };
  return <Badge variant={s.variant} className={className}><span className="size-1.5 rounded-full bg-current" />{s.label}</Badge>;
}

export function AIBadge({ label = "AI-generated", className }: { label?: string; className?: string }) {
  return <Badge variant="ai" className={className}><Sparkles />{label}</Badge>;
}

export function SimulatedBadge({ className, label = "Simulated" }: { className?: string; label?: string }) {
  return (
    <Badge variant="neutral" className={cn("border-dashed", className)} title="No real external system is contacted">
      <FlaskConical />{label}
    </Badge>
  );
}

type ConfirmOpts = {
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  destructive?: boolean;
  requireReason?: boolean;
  reasonLabel?: string;
};

/** Imperative confirm dialog: `const ok = await confirm({...})`. Returns reason text when requireReason. */
export function useConfirm() {
  const [state, setState] = React.useState<(ConfirmOpts & { resolve: (v: string | false) => void }) | null>(null);
  const [reason, setReason] = React.useState("");
  const confirm = React.useCallback(
    (opts: ConfirmOpts) => new Promise<string | false>((resolve) => { setReason(""); setState({ ...opts, resolve }); }), [],
  );
  const close = (v: string | false) => { state?.resolve(v); setState(null); };
  const dialog = (
    <Dialog open={!!state} onOpenChange={(o) => !o && close(false)}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>{state?.title}</DialogTitle>
          {state?.description && <DialogDescription>{state.description}</DialogDescription>}
        </DialogHeader>
        {state?.requireReason && (
          <div className="grid gap-1.5">
            <label className="text-table font-medium" htmlFor="confirm-reason">{state.reasonLabel ?? "Reason"}</label>
            <Textarea id="confirm-reason" autoFocus value={reason} onChange={(e) => setReason(e.target.value)} rows={3} />
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)}>Cancel</Button>
          <Button
            variant={state?.destructive ? "destructive" : "default"}
            disabled={state?.requireReason && reason.trim().length < 3}
            onClick={() => close(reason.trim() || "ok")}
          >
            {state?.confirmLabel ?? "Confirm"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
  return { confirm, dialog };
}

/** Block in-app navigation and tab close while there are unsaved changes. */
export function useUnsavedChanges(dirty: boolean) {
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);
  React.useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);
  return (
    <Dialog open={blocker.state === "blocked"} onOpenChange={(o) => !o && blocker.reset?.()}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Discard unsaved changes?</DialogTitle>
          <DialogDescription>You have changes that haven't been saved. Leaving now will lose them.</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => blocker.reset?.()}>Keep editing</Button>
          <Button variant="destructive" onClick={() => blocker.proceed?.()}>Discard changes</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type Tone = "primary" | "success" | "warning" | "ai" | "danger";
const TONE_TEXT: Partial<Record<Tone, string>> = { warning: "text-warning", danger: "text-destructive" };

/** One metric: label (12), value (20, tabular), optional sub-line and bar. Neutral unless a rule makes it a warning. */
export function Metric({ label, value, sub, tone, bar, to, className }: {
  label: React.ReactNode; value: React.ReactNode; sub?: React.ReactNode; tone?: Tone; bar?: number; to?: string; className?: string;
}) {
  const body = (
    <>
      <p className="truncate text-label font-medium text-muted-foreground">{label}</p>
      <p className={cn("text-metric font-semibold tabular text-heading", tone && TONE_TEXT[tone])}>{value}</p>
      {bar != null && (
        <div className="my-1 h-1.5 overflow-hidden rounded-full bg-muted" role="img" aria-label={`${Math.round(bar)}%`}>
          <div className={cn("h-full rounded-full", bar >= 90 ? "bg-destructive" : bar >= 80 ? "bg-warning" : "bg-primary")} style={{ width: `${Math.min(100, Math.max(0, bar))}%` }} />
        </div>
      )}
      {sub && <p className="truncate text-label text-muted-foreground">{sub}</p>}
    </>
  );
  const cls = cn("block min-w-0 bg-card px-4 py-3", className);
  return to ? <Link to={to} className={cn(cls, "hover:bg-muted/60 focus-visible:relative focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50")}>{body}</Link> : <div className={cls}>{body}</div>;
}

/** A row of metrics in one bordered strip with dividers (replaces separate KPI tiles). */
export function MetricStrip({ children, className, cols }: { children: React.ReactNode; className?: string; cols?: 2 | 3 | 4 | 5 | 6 }) {
  const n = cols ?? Math.min(6, React.Children.toArray(children).filter(Boolean).length) as 2 | 3 | 4 | 5 | 6;
  const lg = { 1: "lg:grid-cols-1", 2: "lg:grid-cols-2", 3: "lg:grid-cols-3", 4: "lg:grid-cols-4", 5: "lg:grid-cols-5", 6: "lg:grid-cols-6" }[n] ?? "lg:grid-cols-4";
  return <div className={cn("grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-3", lg, className)}>{children}</div>;
}

/** Back-compatible single metric tile (bordered). Icons stay muted so colour is not decoration. */
export function Stat({ label, value, sub, icon: Icon, tone }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; icon?: LucideIcon; tone?: Tone;
}) {
  return (
    <div className="rounded-lg border bg-card px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-label font-medium text-muted-foreground">{label}</p>
        {Icon && <Icon className={cn("size-4 shrink-0 text-muted-foreground", tone && TONE_TEXT[tone])} aria-hidden />}
      </div>
      <p className={cn("text-metric font-semibold tabular text-heading", tone && TONE_TEXT[tone])}>{value}</p>
      {sub && <p className="mt-0.5 text-label text-muted-foreground">{sub}</p>}
    </div>
  );
}

export function KeyValue({ label, value, className }: { label: string; value: React.ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 truncate text-body">{value || <span className="text-muted-foreground">—</span>}</dd>
    </div>
  );
}
