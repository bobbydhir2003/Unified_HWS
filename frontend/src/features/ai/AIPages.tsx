import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, CheckCircle2, CircleSlash, ListChecks, Phone, PhoneOff, Plus, RotateCcw, Send, ShieldCheck, Workflow, XCircle } from "lucide-react";
import * as React from "react";
import { RealtimeVoicePanel } from "./RealtimeVoice";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { EmptyState, LoadingRows, PageHeader, SimulatedBadge, Stat, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get, patch, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, fromNow } from "@/lib/format";
import { ROLE_LABELS, type Role } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";

// ======================= Tasks =======================

type TaskT = { id: string; title: string; description: string | null; patient_id: string | null; patient_name: string | null; assigned_role: Role | null; assigned_user_id: string | null; priority: string; status: string; link: string | null; source: string; created_at: string };
const PRIO: Record<string, React.ComponentProps<typeof Badge>["variant"]> = { urgent: "danger", high: "warning", normal: "neutral", low: "outline" };

export function TasksPage() {
  const qc = useQueryClient();
  const [scope, setScope] = React.useState<"mine" | "all">("mine");
  const [status, setStatus] = React.useState<"open" | "done">("open");
  const [creating, setCreating] = React.useState(false);
  const [f, setF] = React.useState({ title: "", description: "", assigned_role: "", priority: "normal" });
  const q = useQuery({ queryKey: ["tasks", scope, status], queryFn: () => get<TaskT[]>("/tasks", { scope, status }), refetchInterval: 20_000 });
  const act = async (t: TaskT, a: "complete" | "reopen") => { try { await post(`/tasks/${t.id}/${a}`); qc.invalidateQueries({ queryKey: ["tasks"] }); qc.invalidateQueries({ queryKey: ["tasks-count"] }); } catch (e) { toastError(e); } };
  return (
    <>
      <PageHeader title="Tasks" description="Your worklist — created by colleagues, automations and the AI receptionist." actions={<Button onClick={() => setCreating(true)}><Plus />New task</Button>} />
      <Card className="overflow-hidden">
        <div className="flex flex-wrap gap-2 border-b p-3">
          {(["mine", "all"] as const).map((s) => <button key={s} onClick={() => setScope(s)} className={cn("rounded-md px-2.5 py-1 text-[13px] font-medium text-muted-foreground", scope === s && "bg-accent text-accent-foreground")}>{s === "mine" ? "Mine & my roles" : "Everyone"}</button>)}
          <span className="mx-1 w-px bg-border" />
          {(["open", "done"] as const).map((s) => <button key={s} onClick={() => setStatus(s)} className={cn("rounded-md px-2.5 py-1 text-[13px] font-medium capitalize text-muted-foreground", status === s && "bg-accent text-accent-foreground")}>{s}</button>)}
        </div>
        {q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState icon={ListChecks} title={status === "open" ? "Nothing on your list" : "No completed tasks"} /> : (
          <ul className="divide-y">{q.data.map((t) => (
            <li key={t.id} className="flex items-start gap-3 px-4 py-3">
              <button onClick={() => act(t, t.status === "open" ? "complete" : "reopen")} className={cn("mt-0.5 size-5 shrink-0 rounded-full border-2", t.status === "done" ? "border-success bg-success" : "border-input hover:border-primary")} aria-label={t.status === "open" ? "Mark done" : "Reopen"}>
                {t.status === "done" && <CheckCircle2 className="size-4 text-white" />}
              </button>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  {t.link ? <Link to={t.link} className={cn("text-[13.5px] font-medium hover:underline", t.status === "done" && "line-through opacity-60")}>{t.title}</Link> : <span className="text-[13.5px] font-medium">{t.title}</span>}
                  {t.priority !== "normal" && <Badge variant={PRIO[t.priority]}>{titleCase(t.priority)}</Badge>}
                  {t.source !== "manual" && <Badge variant="ai"><Bot />{t.source === "automation" ? "Automation" : "AI receptionist"}</Badge>}
                </div>
                {t.description && <p className="text-xs text-muted-foreground">{t.description}</p>}
                <p className="text-xs text-muted-foreground">{t.assigned_role ? ROLE_LABELS[t.assigned_role] : "Assigned to a person"}{t.patient_name ? ` · ${t.patient_name}` : ""} · {fromNow(t.created_at)}</p>
              </div>
            </li>
          ))}</ul>
        )}
      </Card>
      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent size="sm">
          <DialogHeader><DialogTitle>New task</DialogTitle></DialogHeader>
          <Field label="Title" required><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field label="Details"><Textarea rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Assign to"><NativeSelect value={f.assigned_role} onChange={(e) => setF({ ...f, assigned_role: e.target.value })}><option value="">Me</option>{(["doctor", "nurse", "receptionist", "billing", "clinic_admin"] as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}</NativeSelect></Field>
            <Field label="Priority"><NativeSelect value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>{["low", "normal", "high", "urgent"].map((p) => <option key={p} value={p}>{titleCase(p)}</option>)}</NativeSelect></Field>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setCreating(false)}>Cancel</Button>
            <Button disabled={f.title.trim().length < 2} onClick={async () => { try { await post("/tasks", { ...f, assigned_role: f.assigned_role || null, description: f.description || null }); setCreating(false); setF({ title: "", description: "", assigned_role: "", priority: "normal" }); qc.invalidateQueries({ queryKey: ["tasks"] }); } catch (e) { toastError(e); } }}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ======================= Automation studio =======================

type Perm = { action: string; label: string; sensitive: boolean };
type WF = { id: string; template_key: string; name: string; description: string; trigger: string; requires_approval: boolean; is_enabled: boolean; permissions: Perm[]; stats: Record<string, number> };
type Run = { id: string; workflow: string; trigger_event: string; status: string; patient_id: string | null; patient_name: string | null; proposed_actions: { type: string; title?: string; subject?: string; body?: string; role?: string; reason?: string }[]; log: { at: string; msg: string }[]; error: string | null; created_at: string; sensitive: boolean };
const RUN_VARIANT: Record<string, React.ComponentProps<typeof Badge>["variant"]> = { succeeded: "success", failed: "danger", pending_approval: "warning", rejected: "neutral", running: "info" };

export function AutomationPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? (can("automation:manage") ? "workflows" : "approvals");
  const qc = useQueryClient();
  const wfs = useQuery({ queryKey: ["workflows"], queryFn: () => get<WF[]>("/automation/workflows"), enabled: can("automation:manage") });
  const runs = useQuery({ queryKey: ["runs", tab], queryFn: () => get<Run[]>("/automation/runs", { status: tab === "approvals" ? "pending_approval" : undefined }), enabled: tab !== "workflows", refetchInterval: 15_000 });
  const pendingCount = useQuery({ queryKey: ["runs", "pending-count"], queryFn: () => get<Run[]>("/automation/runs", { status: "pending_approval" }) });
  const [busy, setBusy] = React.useState<string | null>(null);
  const refresh = () => ["workflows", "runs", "tasks"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const runAct = async (r: Run, a: "approve" | "reject" | "retry") => {
    setBusy(r.id + a);
    try { await post(`/automation/runs/${r.id}/${a}`); toast.success(a === "approve" ? "Approved and executed" : a === "reject" ? "Rejected" : "Retried"); refresh(); } catch (e) { toastError(e); } finally { setBusy(null); }
  };
  const tabs: [string, string, boolean][] = [["workflows", "Workflows", can("automation:manage")], ["approvals", `Approvals${pendingCount.data?.length ? ` (${pendingCount.data.length})` : ""}`, true], ["activity", "Activity log", true]];
  return (
    <>
      <PageHeader title="Automation studio" description="Event-driven workflows that create tasks, route work and draft patient outreach. Anything that reaches a patient waits for staff approval." />
      <nav className="-mx-1 mb-5 flex gap-1 border-b px-1">{tabs.filter((t) => t[2]).map(([k, l]) => <button key={k} onClick={() => setParams({ tab: k })} className={cn("-mb-px border-b-2 border-transparent px-3 py-2 text-[13px] font-medium text-muted-foreground", tab === k && "border-primary text-foreground")}>{l}</button>)}</nav>
      {tab === "workflows" && (
        wfs.isLoading ? <LoadingRows /> : (
          <div className="grid gap-4 lg:grid-cols-2">{wfs.data?.map((w) => (
            <Card key={w.id} className={cn(!w.is_enabled && "opacity-70")}>
              <CardHeader className="pb-2">
                <div><CardTitle className="flex items-center gap-2"><Workflow className="size-4 text-primary" />{w.name}</CardTitle><p className="mt-0.5 font-mono text-[11.5px] text-muted-foreground">on {w.trigger}</p></div>
                <Switch checked={w.is_enabled} aria-label={`Enable ${w.name}`} onCheckedChange={async (v) => { try { await patch(`/automation/workflows/${w.id}`, { is_enabled: v }); refresh(); } catch (e) { toastError(e); } }} />
              </CardHeader>
              <CardContent className="space-y-3 text-[13px]">
                <p className="text-muted-foreground">{w.description}</p>
                <div><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Allowed actions</p>
                  <ul className="space-y-0.5">{w.permissions.map((p) => <li key={p.action} className="flex items-center gap-1.5"><ShieldCheck className="size-3.5 text-success" />{p.label}{p.sensitive && <Badge variant="warning">patient-facing</Badge>}</li>)}</ul>
                </div>
                {w.permissions.some((p) => p.sensitive) && (
                  <label className="flex items-center gap-2"><Switch checked={w.requires_approval} onCheckedChange={async (v) => { try { await patch(`/automation/workflows/${w.id}`, { requires_approval: v }); refresh(); } catch (e) { toastError(e); } }} />Require staff approval before patient-facing actions</label>
                )}
                <p className="text-xs text-muted-foreground">Last 30 days: {Object.entries(w.stats).map(([k, v]) => `${v} ${k.replace("_", " ")}`).join(" · ") || "no runs"}</p>
              </CardContent>
            </Card>
          ))}</div>
        )
      )}
      {tab !== "workflows" && (
        runs.isLoading ? <LoadingRows /> : !runs.data?.length ? <Card><EmptyState icon={tab === "approvals" ? CheckCircle2 : Workflow} title={tab === "approvals" ? "Nothing waiting for approval" : "No automation activity yet"} /></Card> : (
          <div className="space-y-3">{runs.data.map((r) => (
            <Card key={r.id}>
              <CardContent className="space-y-2 pt-4 text-[13px]">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{r.workflow}</span><Badge variant={RUN_VARIANT[r.status] ?? "neutral"}>{titleCase(r.status)}</Badge>
                  {r.patient_name && <Link to={`/patients/${r.patient_id}`} className="text-primary hover:underline">{r.patient_name}</Link>}
                  <span className="ml-auto text-xs text-muted-foreground">{fmtDateTime(r.created_at)}</span>
                </div>
                <ul className="space-y-1">{r.proposed_actions.map((a, i) => (
                  <li key={i} className="rounded-lg border bg-muted/30 px-3 py-2">
                    <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{titleCase(a.type)}{a.role ? ` → ${ROLE_LABELS[a.role as Role] ?? a.role}` : ""}</span>
                    <p>{a.title ?? a.subject}</p>{a.body && <p className="mt-1 whitespace-pre-wrap text-muted-foreground">“{a.body}”</p>}{a.reason && <p className="text-xs text-muted-foreground">{a.reason}</p>}
                  </li>
                ))}</ul>
                {r.error && <p className="text-destructive">{r.error}</p>}
                <details><summary className="cursor-pointer text-xs text-muted-foreground">Execution log ({r.log.length})</summary><ol className="mt-1 space-y-0.5 text-xs text-muted-foreground">{r.log.map((l, i) => <li key={i}>{fmtDateTime(l.at)} — {l.msg}</li>)}</ol></details>
                <div className="flex gap-2">
                  {r.status === "pending_approval" && <>
                    <Button size="sm" loading={busy === r.id + "approve"} onClick={() => runAct(r, "approve")}><Send />Approve & send</Button>
                    <Button size="sm" variant="outline" loading={busy === r.id + "reject"} onClick={() => runAct(r, "reject")}><CircleSlash />Reject</Button>
                  </>}
                  {r.status === "failed" && can("automation:manage") && <Button size="sm" variant="outline" loading={busy === r.id + "retry"} onClick={() => runAct(r, "retry")}><RotateCcw />Retry</Button>}
                </div>
              </CardContent>
            </Card>
          ))}</div>
        )
      )}
    </>
  );
}

// ======================= AI receptionist =======================

type Call = { id: string; from_number: string | null; status: string; consented: boolean; verified_patient_id: string | null; patient_name: string | null; transcript: { speaker: string; text: string; at: string }[]; intent: string | null; outcome: string | null; summary: string | null; created_at: string; stage: string | null };
const QUICK = ["Yes", "I'd like to book an appointment", "Cancel my appointment", "What are your hours?", "I need a refill", "Option 1", "Talk to a person", "That's all, bye"];

export function ReceptionistPage() {
  const qc = useQueryClient();
  const logs = useQuery({ queryKey: ["calls"], queryFn: () => get<Call[]>("/receptionist/calls") });
  const [call, setCall] = React.useState<Call | null>(null);
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [viewing, setViewing] = React.useState<Call | null>(null);
  const pane = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => { pane.current?.scrollTo({ top: pane.current.scrollHeight, behavior: "smooth" }); }, [call?.transcript.length, call?.status]);
  const send = async (t: string) => {
    if (!call || !t.trim()) return;
    setBusy(true);
    try { const c = await post<Call>(`/receptionist/calls/${call.id}/message`, { text: t }); setCall(c); setText(""); if (c.status !== "active") qc.invalidateQueries({ queryKey: ["calls"] }); }
    catch (e) { toastError(e); } finally { setBusy(false); }
  };
  const transcript = (c: Call) => (
    <ol className="space-y-2">{c.transcript.map((t, i) => (
      <li key={i} className={cn("max-w-[85%] rounded-2xl px-3.5 py-2 text-[13.5px]", t.speaker === "caller" ? "ml-auto bg-primary text-primary-foreground" : "bg-muted")}>
        <span className="mb-0.5 block text-[10.5px] font-semibold uppercase tracking-wide opacity-70">{t.speaker === "caller" ? "Caller" : "AI receptionist"}</span>{t.text}
      </li>
    ))}</ol>
  );
  return (
    <>
      <PageHeader title="AI receptionist" description="Sandbox for the phone assistant: test conversations as a caller. Telephony is not connected." actions={<SimulatedBadge label="Sandbox — no real calls" />} />
      <RealtimeVoicePanel />
      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Card className="flex h-[calc(100dvh-220px)] min-h-[480px] flex-col">
          <CardHeader className="border-b pb-3">
            <CardTitle className="flex items-center gap-2"><Phone className="size-4" />Call simulator</CardTitle>
            {call?.status === "active" ? (
              <Button size="sm" variant="destructive" onClick={async () => { try { setCall(await post<Call>(`/receptionist/calls/${call.id}/end`)); qc.invalidateQueries({ queryKey: ["calls"] }); } catch (e) { toastError(e); } }}><PhoneOff />End call</Button>
            ) : (
              <Button size="sm" onClick={async () => { try { setCall(await post<Call>("/receptionist/calls", { from_number: "+1 (555) 010-7788" })); } catch (e) { toastError(e); } }}><Phone />{call ? "New call" : "Start call"}</Button>
            )}
          </CardHeader>
          <div ref={pane} className="min-h-0 flex-1 overflow-y-auto p-4">
            {!call ? <EmptyState icon={Bot} title="Start a call to talk to the AI receptionist" description="Try booking as Elena Moreau, DOB 04/12/1986, or test the safeguards with a wrong date of birth or an emergency phrase." /> : <>
              {transcript(call)}
              {call.status !== "active" && <div className="mt-3 rounded-lg border bg-muted/40 p-3 text-[13px]"><p className="font-medium">Call {call.status}</p><p className="text-muted-foreground">{call.summary}</p></div>}
            </>}
          </div>
          {call?.status === "active" && (
            <div className="space-y-2 border-t p-3">
              <div className="flex flex-wrap gap-1.5">{QUICK.map((q) => <button key={q} onClick={() => send(q)} className="rounded-full border px-2.5 py-0.5 text-xs hover:border-primary hover:text-primary">{q}</button>)}</div>
              <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); send(text); }}>
                <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Say something as the caller…" aria-label="Caller says" autoFocus />
                <Button type="submit" loading={busy} disabled={!text.trim()}><Send /></Button>
              </form>
            </div>
          )}
        </Card>
        <Card className="overflow-hidden">
          <CardHeader className="pb-2"><CardTitle>Call log</CardTitle></CardHeader>
          {logs.isLoading ? <LoadingRows /> : !logs.data?.length ? <EmptyState title="No calls yet" /> : (
            <ul className="max-h-[calc(100dvh-300px)] divide-y overflow-y-auto">{logs.data.map((c) => (
              <li key={c.id}><button onClick={() => setViewing(c)} className="block w-full px-4 py-3 text-left hover:bg-muted/40">
                <span className="flex items-center gap-2 text-[13px] font-medium">{c.patient_name ?? "Unverified caller"}<Badge variant={c.status === "transferred" ? "warning" : c.status === "completed" ? "success" : "neutral"}>{titleCase(c.status)}</Badge><span className="ml-auto text-xs text-muted-foreground">{fmtDateTime(c.created_at)}</span></span>
                <span className="block text-xs text-muted-foreground">{c.summary ?? `${c.transcript.length} turns`}</span>
              </button></li>
            ))}</ul>
          )}
        </Card>
      </div>
      <Dialog open={!!viewing} onOpenChange={(o) => !o && setViewing(null)}>
        <DialogContent size="lg"><DialogHeader><DialogTitle>Call transcript</DialogTitle></DialogHeader>{viewing && <><p className="text-[13px] text-muted-foreground">{viewing.summary}</p><div className="max-h-[60vh] overflow-y-auto">{transcript(viewing)}</div></>}</DialogContent>
      </Dialog>
    </>
  );
}

// ======================= AI monitoring =======================

type Jobs = { provider: string; phi_allowed: boolean; phi_sent_externally_total: number; summary: Record<string, { total: number; succeeded: number; failed: number; avg_latency_ms: number | null }>; jobs: { id: string; kind: string; status: string; provider: string; model: string | null; latency_ms: number | null; input_tokens: number | null; output_tokens: number | null; phi_sent_externally: boolean; error: string | null; created_at: string; subject_type: string | null }[] };

export function AIMonitoringPage() {
  const q = useQuery({ queryKey: ["ai-jobs"], queryFn: () => get<Jobs>("/ai/jobs"), refetchInterval: 30_000 });
  if (!q.data) return <LoadingRows />;
  const d = q.data;
  const totals = Object.values(d.summary).reduce((a, s) => ({ total: a.total + s.total, failed: a.failed + (s.failed ?? 0) }), { total: 0, failed: 0 });
  return (
    <>
      <PageHeader title="AI monitoring" description="Every AI invocation is logged with provider, model, latency and whether patient data left the system." />
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Provider" value={d.provider} sub={d.provider === "simulated" ? "Local rule-based (no network)" : "External model"} icon={Bot} />
        <Stat label="AI jobs (30 days)" value={totals.total} icon={Workflow} />
        <Stat label="Failures" value={totals.failed} icon={XCircle} tone="danger" />
        <Stat label="PHI sent externally" value={d.phi_sent_externally_total} sub={d.phi_allowed ? "Allowed by configuration" : "Blocked by policy"} icon={ShieldCheck} tone={d.phi_sent_externally_total ? "warning" : "success"} />
      </div>
      <Card className="mb-5"><CardHeader><CardTitle>By feature</CardTitle></CardHeader><CardContent className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {Object.entries(d.summary).map(([k, s]) => <div key={k} className="rounded-lg border p-3 text-[13px]"><p className="font-medium">{titleCase(k)}</p><p className="text-muted-foreground">{s.total} runs · {s.failed ?? 0} failed{s.avg_latency_ms != null ? ` · ${s.avg_latency_ms} ms avg` : ""}</p></div>)}
      </CardContent></Card>
      <Card className="overflow-hidden">
        <Table><THead><TR><TH>When</TH><TH>Feature</TH><TH>Provider / model</TH><TH>Status</TH><TH className="hidden md:table-cell">Latency</TH><TH className="hidden lg:table-cell">PHI external</TH></TR></THead>
          <TBody>{d.jobs.map((j) => (
            <TR key={j.id}>
              <TD className="whitespace-nowrap text-muted-foreground">{fmtDateTime(j.created_at)}</TD>
              <TD>{titleCase(j.kind)}</TD>
              <TD className="font-mono text-xs">{j.provider}{j.model ? ` · ${j.model}` : ""}</TD>
              <TD><Badge variant={j.status === "succeeded" ? "success" : j.status === "failed" ? "danger" : "info"}>{j.status}</Badge>{j.error && <span className="block max-w-64 truncate text-xs text-destructive">{j.error}</span>}</TD>
              <TD className="hidden tabular md:table-cell">{j.latency_ms != null ? `${j.latency_ms} ms` : "—"}</TD>
              <TD className="hidden lg:table-cell">{j.phi_sent_externally ? <Badge variant="warning">Yes</Badge> : "No"}</TD>
            </TR>
          ))}</TBody>
        </Table>
      </Card>
    </>
  );
}
