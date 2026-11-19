import { AlertTriangle, FlaskConical, Inbox, type LucideIcon, RefreshCw, Sparkles } from "lucide-react";
import * as React from "react";
import { useBlocker } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { ApiError } from "@/lib/api";
import type { AppointmentStatus } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";

export function PageHeader({
  title, description, actions, children, className,
}: { title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; children?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight sm:text-[22px]">{title}</h1>
        {description && <p className="mt-1 text-[13px] text-muted-foreground">{description}</p>}
        {children}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({
  icon: Icon = Inbox, title, description, action, className,
}: { icon?: LucideIcon; title: string; description?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 px-6 py-12 text-center", className)}>
      <div className="mb-1 rounded-full bg-muted p-3 text-muted-foreground"><Icon className="size-5" /></div>
      <p className="font-medium">{title}</p>
      {description && <p className="max-w-sm text-[13px] text-muted-foreground">{description}</p>}
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
      <p className="max-w-md text-[13px] text-muted-foreground">{msg}</p>
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

const APPT_STATUS: Record<AppointmentStatus, { label: string; variant: React.ComponentProps<typeof Badge>["variant"] }> = {
  scheduled: { label: "Scheduled", variant: "neutral" },
  confirmed: { label: "Confirmed", variant: "info" },
  checked_in: { label: "Checked in", variant: "warning" },
  roomed: { label: "Roomed", variant: "primary" },
  in_progress: { label: "With provider", variant: "ai" },
  completed: { label: "Visit done", variant: "success" },
  checked_out: { label: "Checked out", variant: "success" },
  cancelled: { label: "Cancelled", variant: "danger" },
  no_show: { label: "No-show", variant: "danger" },
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
    <Badge variant="warning" className={className} title="No real external system is contacted">
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
            <label className="text-[13px] font-medium" htmlFor="confirm-reason">{state.reasonLabel ?? "Reason"}</label>
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

export function Stat({ label, value, sub, icon: Icon, tone = "primary" }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; icon?: LucideIcon; tone?: "primary" | "success" | "warning" | "ai" | "danger";
}) {
  const tones = {
    primary: "bg-accent text-accent-foreground", success: "bg-success-soft text-success",
    warning: "bg-warning-soft text-warning", ai: "bg-ai-soft text-ai", danger: "bg-destructive-soft text-destructive",
  };
  return (
    <div className="rounded-xl border bg-card p-4 shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
      <div className="flex items-center justify-between">
        <p className="text-[13px] font-medium text-muted-foreground">{label}</p>
        {Icon && <span className={cn("rounded-lg p-1.5", tones[tone])}><Icon className="size-4" /></span>}
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight tabular">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

export function KeyValue({ label, value, className }: { label: string; value: React.ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 truncate text-[13.5px]">{value || <span className="text-muted-foreground">—</span>}</dd>
    </div>
  );
}
