/** Shared operations UI: case types, severity/SLA badges, case list rows and the case drawer used by every department. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlarmClock, ArrowUpRight, Bell, Bot, CheckCircle2, CircleDot, Clock, MessageSquare, ShieldCheck, UserCheck, UserRound, XCircle } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { EmptyState, LoadingRows, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, fromNow } from "@/lib/format";
import { ROLE_LABELS, STAFF_ROLES, type Role } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";

export type CaseT = {
  id: string; number: number; category: string; kind: string; title: string; summary: string | null; severity: Severity; status: string;
  patient_id: string | null; patient_name: string | null; facility_id: string | null; department_id: string | null; subject_type: string | null;
  subject_id: string | null; link: string | null; assigned_role: Role | null; assigned_user_id: string | null; assigned_user_name: string | null;
  due_at: string | null; overdue: boolean; escalation_level: number; snoozed_until: string | null; snooze_reason: string | null;
  resolved_at: string | null; resolution_code: string | null; resolution: string | null; source: string; rule_key: string | null;
  rule_version: number | null; evidence: Record<string, unknown>; created_at: string; last_detected_at: string;
};
export type Severity = "info" | "low" | "medium" | "high" | "critical";
export type CaseEventT = { id: string; at: string; actor_id: string | null; actor_name: string | null; actor_kind: string; kind: string; message: string; data: Record<string, unknown> };
export type ApprovalT = {
  id: string; kind: string; title: string; summary: string | null; case_id: string | null; patient_id: string | null; requested_by_user_id: string | null;
  requested_by_agent: string | null; required_permission: string; payload: Record<string, unknown>; status: string; decided_at: string | null;
  decision_note: string | null; executed_at: string | null; result: Record<string, unknown>; error: string | null; created_at: string; can_decide: boolean;
};
export type TaskT = {
  id: string; title: string; description: string | null; patient_id: string | null; patient_name: string | null; assigned_role: Role | null;
  assigned_user_id: string | null; priority: string; status: string; link: string | null; source: string; created_at: string; completed_at: string | null;
  case_id: string | null; due_at: string | null; kind: string | null; acknowledged_at: string | null;
};
type DeliveryT = { id: string; channel: string; category: string; subject: string; status: string; status_reason: string | null; created_at: string; recipient_patient_id: string | null };
type CaseDetail = { case: CaseT; events: CaseEventT[]; tasks: TaskT[]; deliveries: DeliveryT[]; approvals: ApprovalT[] };

export const SEVERITY_VARIANT: Record<Severity, React.ComponentProps<typeof Badge>["variant"]> = {
  critical: "danger", high: "danger", medium: "warning", low: "info", info: "neutral",
};
export const CATEGORY_LABEL: Record<string, string> = {
  insurance: "Insurance", scheduling: "Scheduling", clinical: "Clinical", lab: "Laboratory", radiology: "Radiology", pharmacy: "Pharmacy",
  inventory: "Inventory", bed: "Beds", ed: "Emergency", discharge: "Discharge", billing: "Billing", staffing: "Staffing", or: "Operating rooms",
  equipment: "Equipment", patient_followup: "Follow-up", documents: "Documents", operations: "Operations", automation: "Automation",
};

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <Badge variant={SEVERITY_VARIANT[severity]} className={className}>
      <span className={cn("size-1.5 rounded-full", severity === "critical" ? "bg-destructive animate-pulse" : "bg-current opacity-70")} aria-hidden />
      {titleCase(severity)}
    </Badge>
  );
}

export function CaseStatusBadge({ status }: { status: string }) {
  const v: Record<string, React.ComponentProps<typeof Badge>["variant"]> = {
    open: "primary", in_progress: "info", waiting: "neutral", snoozed: "outline", escalated: "danger", resolved: "success", cancelled: "neutral",
  };
  return <Badge variant={v[status] ?? "neutral"}>{titleCase(status.replace("_", " "))}</Badge>;
}

export function SlaBadge({ c }: { c: Pick<CaseT, "due_at" | "overdue" | "status" | "snoozed_until" | "escalation_level"> }) {
  if (c.status === "snoozed" && c.snoozed_until) return <span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><AlarmClock className="size-3.5" />Snoozed until {fmtDateTime(c.snoozed_until)}</span>;
  if (!c.due_at || ["resolved", "cancelled"].includes(c.status)) return null;
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs tabular", c.overdue ? "font-medium text-destructive" : "text-muted-foreground")}>
      <Clock className="size-3.5" />{c.overdue ? `Overdue ${fromNow(c.due_at)}` : `Due ${fromNow(c.due_at)}`}
      {c.escalation_level > 0 && <Badge variant="danger" className="ml-1">Escalated L{c.escalation_level}</Badge>}
    </span>
  );
}

export function ownerLabel(c: Pick<CaseT, "assigned_user_name" | "assigned_role">) {
  return c.assigned_user_name ?? (c.assigned_role ? ROLE_LABELS[c.assigned_role] ?? titleCase(c.assigned_role) : "Unassigned");
}

export function CaseRow({ c, onOpen, compact }: { c: CaseT; onOpen: (id: string) => void; compact?: boolean }) {
  return (
    <li>
      <button onClick={() => onOpen(c.id)} className={cn("flex w-full items-start gap-3 px-4 text-left hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:outline-none", compact ? "py-2.5" : "py-3")}>
        <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", { critical: "bg-destructive", high: "bg-destructive/70", medium: "bg-warning", low: "bg-primary/60", info: "bg-muted-foreground/40" }[c.severity])} aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-[13.5px] font-medium">{c.title}</span>
            {!compact && <SeverityBadge severity={c.severity} />}
            {c.status !== "open" && <CaseStatusBadge status={c.status} />}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
            <span>#{c.number} · {CATEGORY_LABEL[c.category] ?? c.category}</span>
            <span className="inline-flex items-center gap-1"><UserRound className="size-3" />{ownerLabel(c)}</span>
            <SlaBadge c={c} />
            {c.source === "monitor" && <span className="inline-flex items-center gap-1"><Bot className="size-3" />Detected automatically</span>}
          </div>
        </div>
      </button>
    </li>
  );
}

const EVENT_ICON: Record<string, React.ElementType> = {
  created: CircleDot, assigned: UserCheck, escalated: AlarmClock, notification: Bell, comment: MessageSquare, resolved: CheckCircle2,
  cancelled: XCircle, approval: ShieldCheck, approval_requested: ShieldCheck, task: CheckCircle2,
};

/** Case detail drawer: evidence, timeline (append-only), tasks, notifications, approvals and actions. */
export function CaseDrawer({ caseId, onClose }: { caseId: string | null; onClose: () => void }) {
  const qc = useQueryClient();
  const { can, me } = useAuth();
  const q = useQuery({ queryKey: ["cases", "detail", caseId], queryFn: () => get<CaseDetail>(`/cases/${caseId}`), enabled: !!caseId });
  const [dialog, setDialog] = React.useState<null | "snooze" | "resolve" | "assign">(null);
  const [text, setText] = React.useState("");
  const [hours, setHours] = React.useState("4");
  const [role, setRole] = React.useState<string>("");
  const [comment, setComment] = React.useState("");
  const work = can("cases:work");
  const refresh = () => { qc.invalidateQueries({ queryKey: ["cases"] }); qc.invalidateQueries({ queryKey: ["worklist"] }); };
  const act = async (path: string, body: unknown, ok: string) => {
    try { await post(`/cases/${caseId}/${path}`, body); toast.success(ok); setDialog(null); setText(""); refresh(); } catch (e) { toastError(e); }
  };
  const c = q.data?.case;
  const closed = c && ["resolved", "cancelled"].includes(c.status);
  return (
    <Dialog open={!!caseId} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="max-w-xl overflow-y-auto" aria-describedby={undefined}>
        {!c ? <div className="p-6"><LoadingRows rows={6} /></div> : (
          <div className="flex flex-col">
            <div className="border-b p-5 pr-12">
              <p className="text-xs text-muted-foreground">Case #{c.number} · {CATEGORY_LABEL[c.category] ?? c.category}{c.rule_key ? ` · rule ${c.rule_key} v${c.rule_version ?? 0}` : ""}</p>
              <DialogTitle className="mt-1 text-[17px] font-semibold leading-snug">{c.title}</DialogTitle>
              <div className="mt-2 flex flex-wrap items-center gap-2"><SeverityBadge severity={c.severity} /><CaseStatusBadge status={c.status} /><SlaBadge c={c} /></div>
              {c.summary && <p className="mt-3 text-[13.5px] text-muted-foreground">{c.summary}</p>}
              <dl className="mt-3 grid grid-cols-2 gap-3 text-[13px]">
                <div><dt className="text-xs text-muted-foreground">Owner</dt><dd className="font-medium">{ownerLabel(c)}</dd></div>
                <div><dt className="text-xs text-muted-foreground">Patient</dt><dd>{c.patient_id ? <Link className="font-medium text-primary hover:underline" to={`/patients/${c.patient_id}`}>{c.patient_name ?? "Open chart"}</Link> : "—"}</dd></div>
                <div><dt className="text-xs text-muted-foreground">Detected</dt><dd>{fmtDateTime(c.created_at)}</dd></div>
                <div><dt className="text-xs text-muted-foreground">{closed ? "Closed" : "Last confirmed"}</dt><dd>{fmtDateTime(closed ? c.resolved_at : c.last_detected_at)}</dd></div>
              </dl>
              {closed && c.resolution && <p className="mt-3 rounded-lg bg-success-soft px-3 py-2 text-[13px] text-success"><CheckCircle2 className="mr-1 inline size-4" />{c.resolution}</p>}
              {work && !closed && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {c.assigned_user_id !== me?.user.id && <Button size="sm" onClick={() => act("assign", {}, "Assigned to you")}><UserCheck />Take it</Button>}
                  <Button size="sm" variant="outline" onClick={() => setDialog("assign")}>Reassign</Button>
                  {c.status !== "snoozed" && <Button size="sm" variant="outline" onClick={() => setDialog("snooze")}><AlarmClock />Snooze</Button>}
                  <Button size="sm" variant="outline" onClick={() => setDialog("resolve")}><CheckCircle2 />Resolve</Button>
                  {c.link && <Button size="sm" variant="ghost" asChild><Link to={c.link} onClick={onClose}>Open work area<ArrowUpRight /></Link></Button>}
                </div>
              )}
            </div>
            {Object.keys(c.evidence ?? {}).length > 0 && (
              <section className="border-b p-5">
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Evidence (what the rule saw)</h4>
                <Evidence data={c.evidence} />
              </section>
            )}
            {q.data!.tasks.length > 0 && (
              <section className="border-b p-5">
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Tasks</h4>
                <ul className="space-y-1.5">{q.data!.tasks.map((t) => (
                  <li key={t.id} className="flex items-center gap-2 text-[13px]">
                    {t.status === "done" ? <CheckCircle2 className="size-4 text-success" /> : <CircleDot className="size-4 text-muted-foreground" />}
                    <span className={cn("flex-1", t.status === "done" && "text-muted-foreground line-through")}>{t.title}</span>
                    <span className="text-xs text-muted-foreground">{t.assigned_role ? ROLE_LABELS[t.assigned_role] : "Assigned"}</span>
                  </li>))}</ul>
              </section>
            )}
            {q.data!.approvals.length > 0 && (
              <section className="border-b p-5">
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Approvals</h4>
                <ApprovalList items={q.data!.approvals} />
              </section>
            )}
            {q.data!.deliveries.length > 0 && (
              <section className="border-b p-5">
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Notifications</h4>
                <ul className="space-y-1 text-[13px]">{q.data!.deliveries.map((d) => (
                  <li key={d.id} className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{d.channel.replace("_", "-")}</Badge><span className="flex-1 truncate">{d.subject}</span>
                    <Badge variant={d.status === "failed" ? "danger" : d.status === "suppressed" ? "neutral" : d.status === "simulated" ? "warning" : "success"} title={d.status_reason ?? undefined}>{d.status}</Badge>
                  </li>))}</ul>
              </section>
            )}
            <section className="p-5">
              <h4 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Timeline</h4>
              <ol className="relative space-y-3 border-l pl-5">{q.data!.events.map((e) => {
                const Icon = EVENT_ICON[e.kind] ?? CircleDot;
                return (
                  <li key={e.id} className="relative">
                    <span className="absolute -left-[27px] top-0.5 grid size-[18px] place-items-center rounded-full border bg-background"><Icon className="size-3 text-muted-foreground" /></span>
                    <p className="text-[13px]">{e.message}</p>
                    <p className="text-xs text-muted-foreground">{fmtDateTime(e.at)} · {e.actor_name ?? (e.actor_kind === "agent" ? "AI agent" : e.actor_kind === "system" ? "Automation" : "Staff")}</p>
                  </li>);
              })}</ol>
              {work && (
                <form className="mt-4 flex gap-2" onSubmit={async (ev) => { ev.preventDefault(); if (!comment.trim()) return; await act("comment", { text: comment }, "Comment added"); setComment(""); }}>
                  <Input placeholder="Add a note to the timeline…" value={comment} onChange={(e) => setComment(e.target.value)} aria-label="Add a note" />
                  <Button type="submit" variant="outline" disabled={!comment.trim()}>Add</Button>
                </form>
              )}
            </section>
          </div>
        )}
      </SheetContent>
      <Dialog open={dialog !== null} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent size="sm">
          <DialogHeader><DialogTitle>{dialog === "snooze" ? "Snooze case" : dialog === "resolve" ? "Resolve case" : "Reassign case"}</DialogTitle></DialogHeader>
          {dialog === "assign" ? (
            <Field label="Assign to role"><NativeSelect value={role} onChange={(e) => setRole(e.target.value)}><option value="">Choose…</option>{STAFF_ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}</NativeSelect></Field>
          ) : dialog === "snooze" ? (
            <Field label="For how long"><NativeSelect value={hours} onChange={(e) => setHours(e.target.value)}>{[["1", "1 hour"], ["4", "4 hours"], ["24", "1 day"], ["72", "3 days"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect></Field>
          ) : null}
          {dialog !== "assign" && (
            <Field label={dialog === "snooze" ? "Justification" : "How was it resolved?"} required hint={dialog === "snooze" ? "Recorded on the case timeline and audit log." : undefined}>
              <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} />
            </Field>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(null)}>Cancel</Button>
            {dialog === "assign" && <Button disabled={!role} onClick={() => act("assign", { role }, "Reassigned")}>Reassign</Button>}
            {dialog === "snooze" && <Button disabled={text.trim().length < 5} onClick={() => act("snooze", { hours: Number(hours), reason: text }, "Snoozed")}>Snooze</Button>}
            {dialog === "resolve" && <Button disabled={text.trim().length < 3} onClick={() => act("transition", { to: "resolved", note: text }, "Case resolved")}>Resolve</Button>}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Dialog>
  );
}

function Evidence({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, v]) => v !== null && v !== undefined && v !== "");
  return (
    <dl className="grid grid-cols-1 gap-x-4 gap-y-1.5 text-[13px] sm:grid-cols-2">
      {entries.map(([k, v]) => (
        <div key={k} className={cn("min-w-0", (Array.isArray(v) || typeof v === "object") && "sm:col-span-2")}>
          <dt className="text-xs text-muted-foreground">{titleCase(k.replace(/_/g, " "))}</dt>
          <dd className="break-words">{Array.isArray(v) ? (
            <ul className="mt-0.5 space-y-0.5">{v.map((x, i) => <li key={i} className="text-xs">{typeof x === "object" ? Object.entries(x as Record<string, unknown>).map(([a, b]) => `${titleCase(a.replace(/_/g, " "))}: ${fmtVal(b)}`).join(" · ") : String(x)}</li>)}</ul>
          ) : typeof v === "object" ? (
            <span className="text-xs">{Object.entries(v as Record<string, unknown>).map(([a, b]) => `${titleCase(a.replace(/_/g, " "))}: ${fmtVal(b)}`).join(" · ")}</span>
          ) : fmtVal(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

function fmtVal(v: unknown): string {
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v)) return fmtDateTime(v);
  if (typeof v === "string") return v.replace(/_/g, " ");
  if (typeof v === "boolean") return v ? "Yes" : "No";
  return v == null ? "—" : String(v);
}

export function ApprovalList({ items, empty }: { items: ApprovalT[]; empty?: React.ReactNode }) {
  const qc = useQueryClient();
  const [rejecting, setRejecting] = React.useState<ApprovalT | null>(null);
  const [note, setNote] = React.useState("");
  const decide = async (a: ApprovalT, approve: boolean, n?: string) => {
    try {
      const r = await post<ApprovalT>(`/approvals/${a.id}/decide`, { approve, note: n ?? null });
      toast[r.status === "failed" ? "error" : "success"](r.status === "failed" ? `Execution failed: ${r.error}` : approve ? "Approved and executed" : "Rejected");
      setRejecting(null); setNote("");
      qc.invalidateQueries({ queryKey: ["approvals"] }); qc.invalidateQueries({ queryKey: ["worklist"] }); qc.invalidateQueries({ queryKey: ["cases"] });
    } catch (e) { toastError(e); }
  };
  if (!items.length) return <>{empty ?? <EmptyState icon={ShieldCheck} title="No approvals waiting" />}</>;
  return (
    <>
      <ul className="divide-y">{items.map((a) => (
        <li key={a.id} className="flex flex-wrap items-start gap-3 py-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2"><span className="text-[13.5px] font-medium">{a.title}</span>
              {a.requested_by_agent && <Badge variant="ai"><Bot />{a.requested_by_agent}</Badge>}
              {a.status !== "pending" && <Badge variant={a.status === "executed" ? "success" : a.status === "failed" ? "danger" : "neutral"}>{a.status}</Badge>}
            </div>
            {a.summary && <p className="mt-0.5 whitespace-pre-line text-[13px] text-muted-foreground">{a.summary}</p>}
            <p className="mt-0.5 text-xs text-muted-foreground">Requested {fromNow(a.created_at)} · needs <code>{a.required_permission}</code>{a.error ? ` · ${a.error}` : ""}</p>
          </div>
          {a.can_decide && (
            <div className="flex gap-2">
              <Button size="sm" onClick={() => decide(a, true)}><ShieldCheck />Approve</Button>
              <Button size="sm" variant="outline" onClick={() => setRejecting(a)}>Reject</Button>
            </div>
          )}
        </li>))}</ul>
      <Dialog open={!!rejecting} onOpenChange={(o) => !o && setRejecting(null)}>
        <DialogContent size="sm">
          <DialogHeader><DialogTitle>Reject request</DialogTitle></DialogHeader>
          <Field label="Reason" required><Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <DialogFooter><Button variant="outline" onClick={() => setRejecting(null)}>Cancel</Button><Button variant="destructive" disabled={note.trim().length < 3} onClick={() => rejecting && decide(rejecting, false, note)}>Reject</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
