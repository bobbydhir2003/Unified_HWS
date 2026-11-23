import { AlertOctagon, CheckCircle2, Circle, Clock, Hourglass, Loader2, ShieldQuestion, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

/** One status language for the whole app. Every state has a label AND an icon, so meaning never depends on colour. */
export type WorkStatus = "not_started" | "in_progress" | "waiting" | "blocked" | "needs_approval" | "done" | "failed" | "urgent";

const STYLE: Record<WorkStatus, { label: string; icon: React.ElementType; cls: string }> = {
  not_started: { label: "Not started", icon: Circle, cls: "bg-muted text-muted-foreground border-border" },
  in_progress: { label: "In progress", icon: Loader2, cls: "bg-info-soft text-primary border-primary/30" },
  waiting: { label: "Waiting", icon: Hourglass, cls: "bg-warning-soft text-foreground border-warning/50" },
  blocked: { label: "Blocked", icon: AlertOctagon, cls: "bg-destructive-soft text-destructive border-destructive/30" },
  needs_approval: { label: "Needs approval", icon: ShieldQuestion, cls: "bg-ai-soft text-ai border-ai/30" },
  done: { label: "Done", icon: CheckCircle2, cls: "bg-success-soft text-success border-success/30" },
  failed: { label: "Failed", icon: XCircle, cls: "bg-destructive-soft text-destructive border-destructive/30" },
  urgent: { label: "Urgent", icon: Clock, cls: "bg-destructive text-white border-transparent" },
};

export function StatusChip({ status, label, className }: { status: WorkStatus; label?: string; className?: string }) {
  const s = STYLE[status];
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11.5px] font-medium", s.cls, className)}>
      <s.icon className="size-3" aria-hidden />{label ?? s.label}
    </span>
  );
}

/** Map existing case/task/approval statuses onto the shared set. */
export function toWorkStatus(raw: string | null | undefined, opts: { overdue?: boolean; kind?: string } = {}): WorkStatus {
  if (opts.kind === "approval") return "needs_approval";
  if (opts.overdue) return "urgent";
  switch (raw) {
    case "open": return "not_started";
    case "in_progress": return "in_progress";
    case "waiting": case "snoozed": case "pending": return "waiting";
    case "escalated": return "urgent";
    case "blocked": return "blocked";
    case "resolved": case "done": case "completed": case "executed": case "approved": return "done";
    case "failed": case "rejected": return "failed";
    default: return "not_started";
  }
}
