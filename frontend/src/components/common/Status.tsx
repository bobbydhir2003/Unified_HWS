import { AlertTriangle, ArrowUpCircle, CheckCircle2, Circle, Clock, Cog, FlaskConical, Hourglass, Loader2, PenLine, ShieldQuestion, Sparkles, XCircle, XOctagon } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * One status language for the whole app. Every state has a label AND an icon, so meaning never depends on colour.
 *   red     = clinical danger / safety / failure (urgent, blocked, failed)
 *   amber   = attention: overdue, escalated, needs approval
 *   green   = verified done
 *   blue    = active workflow (in progress)
 *   neutral = waiting, not started
 * A routine overdue task is amber ("Overdue"), never the same red as a critical clinical item ("Urgent").
 */
export type WorkStatus = "not_started" | "in_progress" | "waiting" | "blocked" | "needs_approval" | "done" | "failed" | "urgent" | "overdue" | "escalated";

const STYLE: Record<WorkStatus, { label: string; icon: React.ElementType; cls: string }> = {
  not_started: { label: "Not started", icon: Circle, cls: "bg-muted text-muted-foreground border-border" },
  in_progress: { label: "In progress", icon: Loader2, cls: "bg-info-soft text-accent-foreground border-primary/25" },
  waiting: { label: "Waiting", icon: Hourglass, cls: "bg-muted text-muted-foreground border-border" },
  blocked: { label: "Blocked", icon: XOctagon, cls: "bg-destructive-soft text-destructive border-destructive/30" },
  needs_approval: { label: "Needs approval", icon: ShieldQuestion, cls: "bg-warning-soft text-warning-foreground border-warning/35" },
  done: { label: "Done", icon: CheckCircle2, cls: "bg-success-soft text-success border-success/30" },
  failed: { label: "Failed", icon: XCircle, cls: "bg-destructive-soft text-destructive border-destructive/30" },
  urgent: { label: "Urgent", icon: AlertTriangle, cls: "bg-destructive text-on-status border-transparent" },
  overdue: { label: "Overdue", icon: Clock, cls: "bg-warning-soft text-warning-foreground border-warning/35" },
  escalated: { label: "Escalated", icon: ArrowUpCircle, cls: "bg-warning-soft text-warning-foreground border-warning/35" },
};

export function StatusChip({ status, label, className }: { status: WorkStatus; label?: string; className?: string }) {
  const s = STYLE[status];
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-label font-medium", s.cls, className)} data-status={status}>
      <s.icon className="size-3" aria-hidden />{label ?? s.label}
    </span>
  );
}

/**
 * Map existing case/task/approval statuses onto the shared set. Only CLINICAL severity ("critical") or a critical result is
 * red "Urgent"; lateness alone is amber "Overdue".
 */
export function toWorkStatus(raw: string | null | undefined, opts: { overdue?: boolean; kind?: string; severity?: string } = {}): WorkStatus {
  if (opts.kind === "approval") return "needs_approval";
  const closed = ["resolved", "done", "completed", "executed", "approved", "failed", "rejected", "cancelled"].includes(raw ?? "");
  if (!closed && (opts.severity === "critical" || opts.kind === "critical_result")) return "urgent";
  if (!closed && opts.overdue) return "overdue";
  switch (raw) {
    case "open": return "not_started";
    case "in_progress": return "in_progress";
    case "waiting": case "snoozed": case "pending": return "waiting";
    case "escalated": return "escalated";
    case "blocked": return "blocked";
    case "resolved": case "done": case "completed": case "executed": case "approved": return "done";
    case "failed": case "rejected": return "failed";
    default: return "not_started";
  }
}

/** Human-readable duration matching the server's `human_duration` ("45 min", "3 h 20 min", "3 d 18 h"). */
export function humanDuration(minutes: number): string {
  const m = Math.max(0, Math.round(minutes));
  if (m < 60) return `${m} min`;
  if (m < 24 * 60) { const h = Math.floor(m / 60), r = m % 60; return r ? `${h} h ${r} min` : `${h} h`; }
  const d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60);
  return h ? `${d} d ${h} h` : `${d} d`;
}

/** "4 d overdue" / "due in 3 h" from an ISO due time. */
export function dueLabel(due: string | null | undefined, now = Date.now()): string | null {
  if (!due) return null;
  const diff = (new Date(due).getTime() - now) / 60000;
  return diff < 0 ? `${humanDuration(-diff)} overdue` : `due in ${humanDuration(diff)}`;
}

// ---------------------------------------------------------------- AI & automation provenance
export type Provenance = "live" | "simulated" | "draft" | "rule" | "pending" | "completed";
const PROV: Record<Provenance, { label: string; icon: React.ElementType; cls: string }> = {
  live: { label: "Live AI", icon: Sparkles, cls: "bg-ai-soft text-ai border-ai/30" },
  simulated: { label: "Simulated · rule-based", icon: FlaskConical, cls: "bg-muted text-muted-foreground border-control border-dashed" },
  draft: { label: "AI draft — needs review", icon: PenLine, cls: "bg-ai-soft text-ai border-ai/40 border-dashed" },
  rule: { label: "Rule alert", icon: Cog, cls: "bg-muted text-muted-foreground border-border" },
  pending: { label: "Awaiting approval", icon: Hourglass, cls: "bg-warning-soft text-warning-foreground border-warning/35" },
  completed: { label: "Done", icon: CheckCircle2, cls: "bg-success-soft text-success border-success/30" },
};

/** Where content or an action came from: Live AI · Simulated · AI draft · Rule alert · Awaiting approval · Done. */
export function ProvenanceChip({ kind, detail, label, className }: { kind: Provenance; detail?: string | null; label?: string; className?: string }) {
  const p = PROV[kind];
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-label font-medium", p.cls, className)} data-provenance={kind}>
      <p.icon className="size-3" aria-hidden />{label ?? p.label}{detail ? ` · ${detail}` : ""}
    </span>
  );
}
