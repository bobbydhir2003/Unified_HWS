/**
 * HMS Intelligence — ONE conversation panel for all ten department agents (Aurelia, Veyra, … Lucent).
 *
 * The panel sends only the agent key and a stable record reference ({type, id}); the server resolves the record and
 * re-checks access on every turn, pins the agent's tools to that record, and returns persisted messages. Every status
 * shown here (proposal pending/executed/rejected/failed, prepared action confirmed) comes from backend rows, never from
 * model text. While an approval is open the conversation is re-fetched every few seconds.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bot, CheckCircle2, ChevronDown, CircleDot, History, Loader2, Maximize2, Minimize2, Plus, Send, ShieldAlert, XCircle } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toastError } from "@/components/common";
import { ProvenanceChip } from "@/components/common/Status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogDescription, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { Tooltip } from "@/components/ui/menu";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

export type AssistContextType = "workspace" | "case" | "patient" | "stay" | "claim" | "inventory_item" | "message_thread" | "scribe_session" | "document";
export type AssistContext = { type: AssistContextType; id?: string | null };

type Cap = { tool: string; description: string; reason?: string };
export type AssistAgent = { key: string; name: string; role: string | null; previous_name: string; department: string | null; purpose: string; enabled: boolean; can_use: boolean;
  contexts: string[]; prompts: Record<string, string[]>; never: string[]; capabilities: { reads: Cap[]; proposals: Cap[]; confirm: Cap[]; unavailable: Cap[] } };
type AgentsResp = { feature_enabled: boolean; agents: AssistAgent[] };
type Citation = { id: string; type: string; title: string; date: string | null; snippet: string; link: string };
export type ApprovalCard = { type: "approval"; id: string; short_id: string; kind: string; title: string; summary: string | null; status: string;
  assigned_role: string | null; requested_by: string | null; requested_by_agent: string | null; decided_by: string | null; decided_at: string | null;
  decision_note: string | null; result: Record<string, unknown>; error: string | null; task_link: string | null; can_decide: boolean; can_retry: boolean };
export type DraftCard = { type: "draft"; id: string; kind: string; title: string; payload: Record<string, string>; status: string; result: Record<string, unknown>;
  error: string | null; can_confirm: boolean };
type Msg = { id: string; seq: number; role: "user" | "assistant" | "system"; content: string; mode: string | null; citations: Citation[];
  tool_activity: { tool: string; ok: boolean; summary: string }[]; error: string | null; actions: (ApprovalCard | DraftCard)[]; created_at: string };
export type Conversation = { id: string; agent_key: string; agent_name: string; context_type: string; context_id: string | null; context_label: string | null;
  status: string; pending_actions: boolean; messages: Msg[] };
type ConvRow = { id: string; context_label: string | null; status: string; last_message_at: string };

export function useAssistAgents() {
  const { can } = useAuth();
  return useQuery({ queryKey: ["assist", "agents"], queryFn: () => get<AgentsResp>("/assist/agents"), enabled: can("ai:use"), staleTime: 60_000 });
}

/** The agent as the current user sees it, or null when the panel must not be offered (feature off, disabled, no permission). */
export function useAssistAgent(agent: string, context?: AssistContext) {
  const q = useAssistAgents();
  const a = q.data?.agents.find((x) => x.key === agent);
  const ok = !!q.data?.feature_enabled && !!a && a.enabled && a.can_use && a.contexts.includes(context?.type ?? "workspace");
  return { agent: ok ? a! : null, loading: q.isLoading, featureEnabled: !!q.data?.feature_enabled };
}

const STATUS: Record<string, { label: string; variant: "warning" | "success" | "danger" | "neutral" | "primary"; icon: React.ElementType }> = {
  pending: { label: "Waiting for approval", variant: "warning", icon: CircleDot },
  approved: { label: "Approved — executing", variant: "primary", icon: Loader2 },
  executed: { label: "Executed", variant: "success", icon: CheckCircle2 },
  rejected: { label: "Rejected", variant: "danger", icon: XCircle },
  failed: { label: "Failed", variant: "danger", icon: AlertTriangle },
  expired: { label: "Expired", variant: "neutral", icon: XCircle },
  draft: { label: "Needs your confirmation", variant: "warning", icon: CircleDot },
  confirmed: { label: "Done", variant: "success", icon: CheckCircle2 },
  discarded: { label: "Discarded", variant: "neutral", icon: XCircle },
};

function StatusPill({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: status, variant: "neutral" as const, icon: CircleDot };
  return <Badge variant={s.variant} data-testid="action-status" data-status={status}><s.icon className={cn("size-3", status === "approved" && "animate-spin")} aria-hidden />{s.label}</Badge>;
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  if (v === null || v === undefined || v === "") return null;
  return <div className="flex gap-2"><dt className="w-24 shrink-0 text-muted-foreground">{k}</dt><dd className="min-w-0 flex-1 break-words">{v}</dd></div>;
}

export function ActionCardView({ a, onChange }: { a: ApprovalCard | DraftCard; onChange: () => void }) {
  const [busy, setBusy] = React.useState(false);
  const act = async (path: string) => {
    setBusy(true);
    try { await post(path); onChange(); } catch (e) { toastError(e); } finally { setBusy(false); }
  };
  if (a.type === "draft") {
    return (
      <div className="rounded-md border border-l-2 border-l-primary bg-card p-3 text-table" data-testid="action-card" data-kind="draft">
        <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-medium text-heading">{a.title}</p><StatusPill status={a.status} /></div>
        {a.payload.note && <p className="mt-1.5 whitespace-pre-line text-muted-foreground">“{a.payload.note}”</p>}
        {a.payload.text && <p className="mt-1.5 whitespace-pre-line text-muted-foreground"><span className="font-medium">{a.payload.section}:</span> {a.payload.text}</p>}
        {a.status === "confirmed" && Object.keys(a.result).length > 0 && <p className="mt-1.5 text-success">Result: {Object.entries(a.result).filter(([k]) => !k.endsWith("_id")).map(([k, v]) => `${k.replace(/_/g, " ")} ${Array.isArray(v) ? v.join("; ") || "none" : String(v)}`).join(" · ") || "completed"}</p>}
        {a.error && <p className="mt-1.5 text-destructive">{a.error}</p>}
        {a.status === "draft" && (
          <div className="mt-2 flex items-center gap-2">
            {a.can_confirm ? <Button size="xs" loading={busy} onClick={() => act(`/assist/drafts/${a.id}/confirm`)} data-testid="draft-confirm">Confirm</Button>
              : <span className="text-label text-muted-foreground">Your current workspace can't run this.</span>}
            <Button size="xs" variant="ghost" disabled={busy} onClick={() => act(`/assist/drafts/${a.id}/discard`)}>Discard</Button>
            <span className="text-label text-muted-foreground">Runs with your permissions only after you confirm.</span>
          </div>
        )}
      </div>
    );
  }
  const task = typeof a.result?.task_id === "string" ? (a.result.task_id as string) : null;
  return (
    <div className="rounded-md border border-l-2 border-l-warning bg-card p-3 text-table" data-testid="action-card" data-kind="approval">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="min-w-0 font-medium text-heading"><span className="font-mono text-label text-muted-foreground">#{a.short_id}</span> {a.title}</p>
        <StatusPill status={a.status} />
      </div>
      <dl className="mt-2 space-y-0.5 text-label">
        <Row k="Requested by" v={[a.requested_by, a.requested_by_agent && `via ${a.requested_by_agent}`].filter(Boolean).join(" ")} />
        <Row k="Assigned to" v={a.assigned_role?.replace(/_/g, " ")} />
        <Row k="Summary" v={a.summary} />
        <Row k="Decided by" v={a.decided_by} />
        <Row k={a.status === "rejected" ? "Reason" : "Note"} v={a.decision_note} />
        <Row k="Error" v={a.error} />
      </dl>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {a.status === "pending" && <span className="text-label text-muted-foreground">Nothing has changed yet — a different authorized person decides in My Work.</span>}
        {a.can_decide && <Button size="xs" variant="outline" asChild><Link to="/worklist?tab=approvals">Review in My Work</Link></Button>}
        {a.can_retry && <Button size="xs" variant="outline" loading={busy} onClick={() => act(`/approvals/${a.id}/retry`)}>Retry</Button>}
        {task && <Button size="xs" variant="outline" asChild><Link to={a.task_link ?? "/worklist?tab=tasks"} data-testid="open-task">Open task #{task.slice(0, 8)}</Link></Button>}
      </div>
    </div>
  );
}

function CitedText({ text, citations }: { text: string; citations: Citation[] }) {
  const byId = new Map(citations.map((c) => [c.id, c]));
  return (
    <p className="whitespace-pre-wrap leading-relaxed">
      {text.split(/(\[S\d+\])/g).map((p, i) => {
        const m = p.match(/^\[(S\d+)\]$/);
        const c = m && byId.get(m[1]);
        if (!m) return <React.Fragment key={i}>{p}</React.Fragment>;
        return c ? (
          <Tooltip key={i} content={`${c.title}${c.date ? ` · ${c.date}` : ""}`}>
            <Link to={c.link} className="mx-0.5 inline-flex rounded bg-accent px-1 align-baseline font-mono text-label font-semibold text-accent-foreground hover:underline">{m[1]}</Link>
          </Tooltip>
        ) : <span key={i} className="font-mono text-label text-muted-foreground">{p}</span>;
      })}
    </p>
  );
}

function Capabilities({ a }: { a: AssistAgent }) {
  const group = (label: string, items: Cap[]) => !items.length ? null : (
    <div><p className="font-medium text-heading">{label}</p><ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-muted-foreground">{items.map((c) => <li key={c.tool}>{c.description}</li>)}</ul></div>);
  return (
    <details className="group rounded-md border bg-subtle px-3 py-2 text-label" data-testid="assist-capabilities">
      <summary className="flex cursor-pointer list-none items-center gap-1 font-medium text-muted-foreground"><ChevronDown className="size-3.5 transition-transform group-open:rotate-180" aria-hidden />What this assistant can do</summary>
      <div className="mt-2 space-y-2">
        {group("Reads (with your permissions)", a.capabilities.reads)}
        {group("Proposes — a different authorized person approves", a.capabilities.proposals)}
        {group("Prepares — runs only after you confirm", a.capabilities.confirm)}
        {!!a.never.length && <div><p className="font-medium text-heading">Never does</p><ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-muted-foreground">{a.never.map((n) => <li key={n}>{n}</li>)}</ul></div>}
        {!!a.capabilities.unavailable.length && <p className="text-muted-foreground">Not available in your workspace: {a.capabilities.unavailable.map((c) => c.tool.replace(/_/g, " ")).join(", ")}.</p>}
      </div>
    </details>
  );
}

function MessageView({ m, chart, onChange }: { m: Msg; chart: boolean; onChange: () => void }) {
  if (m.role === "user") return <div className="ml-auto max-w-[85%] rounded-lg bg-primary px-3 py-2 text-primary-foreground" data-testid="assist-message" data-role="user">{m.content}</div>;
  if (m.role === "system") {
    return (
      <div className="space-y-1.5" data-testid="assist-message" data-role="system">
        <p className="flex items-start gap-1.5 text-label text-muted-foreground"><CircleDot className="mt-0.5 size-3 shrink-0" aria-hidden />{m.content}</p>
        {m.actions.map((a) => a.type === "approval" && a.task_link
          ? <Link key={a.id} to={a.task_link} className="ml-4 inline-block text-label font-medium text-primary hover:underline">Open task #{String(a.result.task_id).slice(0, 8)}</Link> : null)}
      </div>
    );
  }
  const refused = m.mode === "policy";
  const looked = m.tool_activity ?? [];
  return (
    <div className="space-y-2" data-testid="assist-message" data-role="assistant">
      <div className={cn("rounded-lg border px-3 py-2", refused ? "border-warning/40 bg-warning-soft" : m.error ? "border-destructive/30 bg-destructive-soft" : "bg-card")}>
        {chart && <div className="mb-1 flex items-center gap-1.5 text-label font-medium text-muted-foreground">{refused ? <ShieldAlert className="size-3.5 text-warning" aria-hidden /> : <Bot className="size-3.5 text-ai" aria-hidden />}{refused ? "Can't help with that" : "From the chart"}</div>}
        <CitedText text={m.content} citations={m.citations ?? []} />
      </div>
      {!!looked.length && (
        <details className="text-label" data-testid="tool-activity">
          <summary className="cursor-pointer text-muted-foreground">Checked {looked.length} record source{looked.length === 1 ? "" : "s"}{looked.some((t) => !t.ok) ? " · some were unavailable" : ""}</summary>
          <ul className="mt-1 space-y-0.5">{looked.map((t, i) => <li key={i} className="flex items-start gap-1.5">{t.ok ? <CheckCircle2 className="mt-0.5 size-3 shrink-0 text-success" aria-hidden /> : <XCircle className="mt-0.5 size-3 shrink-0 text-destructive" aria-hidden />}<span><span className="font-medium">{t.tool.replace(/_/g, " ")}</span> — {t.summary}</span></li>)}</ul>
        </details>
      )}
      {!!m.citations?.length && (
        <details className="text-label">
          <summary className="cursor-pointer text-muted-foreground">{m.citations.length} source{m.citations.length > 1 ? "s" : ""}</summary>
          <ul className="mt-1 space-y-1">{m.citations.map((c) => <li key={c.id}><Link to={c.link} className="block rounded-md border px-2 py-1 hover:bg-muted/50"><span className="font-mono font-semibold text-primary">{c.id}</span> {c.title}{c.date ? ` · ${c.date}` : ""}<span className="block truncate text-muted-foreground">{c.snippet}</span></Link></li>)}</ul>
        </details>
      )}
      {m.actions.map((a) => <ActionCardView key={a.id} a={a} onChange={onChange} />)}
    </div>
  );
}

/**
 * The panel itself (controlled). Opens/reuses the user's conversation for this agent + record when `open` turns true.
 * `autoAsk`: a first question sent automatically into a NEW, empty conversation (keeps the old one-click summaries).
 */
export function HMSAssistSheet({ agent, context, open, onOpenChange, autoAsk, testId = "assist-panel" }: {
  agent: AssistAgent; context: AssistContext; open: boolean; onOpenChange: (o: boolean) => void; autoAsk?: string; testId?: string;
}) {
  const qc = useQueryClient();
  const [conv, setConv] = React.useState<Conversation | null>(null);
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const [wide, setWide] = React.useState(false);
  const [showHistory, setShowHistory] = React.useState(false);
  const pane = React.useRef<HTMLDivElement>(null);
  const asked = React.useRef(false);
  const chart = agent.key === "doctor_assistant";
  const ctxKey = `${context.type}:${context.id ?? ""}`;

  const send = React.useCallback(async (c: Conversation, q: string) => {
    if (!q.trim()) return;
    setBusy(true); setErr(null);
    setConv({ ...c, messages: [...c.messages, { id: "pending", seq: 1e9, role: "user", content: q, mode: null, citations: [], tool_activity: [], error: null, actions: [], created_at: "" }] });
    try {
      const next = await post<Conversation>(`/assist/conversations/${c.id}/messages`, { text: q });
      setConv(next); setText("");
      qc.invalidateQueries({ queryKey: ["worklist"] });
    } catch (e) { setConv(c); setText(q); setErr(e instanceof Error ? e.message : "The assistant could not answer."); }
    finally { setBusy(false); }
  }, [qc]);

  const openConv = React.useCallback(async (fresh: boolean) => {
    setErr(null); setBusy(true);
    try {
      const c = await post<Conversation>("/assist/conversations", { agent_key: agent.key, context_type: context.type, context_id: context.id ?? null, new: fresh });
      setConv(c);
      setBusy(false);
      if (autoAsk && !asked.current && c.messages.length === 0) { asked.current = true; await send(c, autoAsk); }
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not open the assistant."); setBusy(false); }
  }, [agent.key, context.type, context.id, autoAsk, send]);

  React.useEffect(() => { if (open && (!conv || `${conv.context_type}:${conv.context_id ?? ""}` !== ctxKey && context.type !== "workspace")) void openConv(false); }, [open, ctxKey]); // eslint-disable-line react-hooks/exhaustive-deps
  React.useEffect(() => { pane.current?.scrollTo({ top: pane.current.scrollHeight }); }, [conv?.messages.length, busy]);

  const refresh = React.useCallback(async () => {
    if (!conv) return;
    try { setConv(await get<Conversation>(`/assist/conversations/${conv.id}`)); qc.invalidateQueries({ queryKey: ["worklist"] }); } catch { /* keep current view */ }
  }, [conv, qc]);
  // Live status: while a proposal is open, re-read the conversation (statuses come from the approval rows).
  React.useEffect(() => {
    if (!open || !conv?.pending_actions) return;
    const t = window.setInterval(() => { void refresh(); }, 4000);
    return () => window.clearInterval(t);
  }, [open, conv?.pending_actions, refresh]);

  const history = useQuery({ queryKey: ["assist", "history", agent.key, ctxKey], enabled: open && showHistory,
    queryFn: () => get<ConvRow[]>("/assist/conversations", { agent_key: agent.key, context_type: context.type, ...(context.id ? { context_id: context.id } : {}) }) });
  const prompts = agent.prompts[context.type] ?? agent.prompts.workspace ?? [];
  const lastMode = [...(conv?.messages ?? [])].reverse().find((m) => m.role === "assistant")?.mode;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <SheetContent size="lg" className={cn("bg-background", wide && "max-w-4xl")} aria-describedby="assist-context" data-testid={testId}>
        <div className="space-y-2 border-b px-4 py-3 pr-12">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <DialogTitle className="flex items-center gap-2 text-section font-semibold text-heading"><Bot className="size-4 text-primary" aria-hidden />{agent.name}</DialogTitle>
              <p className="text-label text-muted-foreground">{agent.role ?? "AI agent"} · {agent.department ?? agent.previous_name} · HMS Intelligence</p>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Button size="icon-sm" variant="ghost" aria-label="Conversation history" onClick={() => setShowHistory((v) => !v)}><History /></Button>
              <Button size="icon-sm" variant="ghost" aria-label="New conversation" disabled={busy} onClick={() => { asked.current = true; void openConv(true); }}><Plus /></Button>
              <Button size="icon-sm" variant="ghost" aria-label={wide ? "Collapse panel" : "Expand panel"} onClick={() => setWide((v) => !v)}>{wide ? <Minimize2 /> : <Maximize2 />}</Button>
            </div>
          </div>
          <DialogDescription id="assist-context" className="flex flex-wrap items-center gap-1.5 text-label" data-testid="assist-context">
            <span className="rounded border bg-subtle px-1.5 py-0.5 font-medium text-foreground">{conv?.context_label ?? (context.type === "workspace" ? "Your workspace" : "Loading record…")}</span>
            {lastMode === "openai" ? <ProvenanceChip kind="live" /> : lastMode === "rule_based" ? <ProvenanceChip kind="simulated" label="Rule-based (no AI provider)" /> : null}
          </DialogDescription>
          {showHistory && (
            <div className="rounded-md border bg-card p-2 text-label" data-testid="assist-history">
              {history.isLoading ? <p className="text-muted-foreground">Loading…</p> : !history.data?.length ? <p className="text-muted-foreground">No earlier conversations.</p> : (
                <ul className="max-h-40 space-y-0.5 overflow-y-auto">{history.data.map((h) => (
                  <li key={h.id}><button type="button" className={cn("w-full rounded px-2 py-1 text-left hover:bg-muted", h.id === conv?.id && "bg-muted font-medium")}
                    onClick={async () => { try { setConv(await get<Conversation>(`/assist/conversations/${h.id}`)); setShowHistory(false); } catch (e) { toastError(e); } }}>
                    {new Date(h.last_message_at).toLocaleString()} · {h.status}</button></li>))}</ul>)}
            </div>
          )}
        </div>
        <div ref={pane} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3 text-body" aria-live="polite">
          <Capabilities a={agent} />
          {conv && conv.messages.length === 0 && !busy && <p className="text-label text-muted-foreground">Ask a question about {conv.context_type === "workspace" ? "your work" : "this record"}, or pick a suggestion below.</p>}
          {conv?.messages.map((m) => <MessageView key={m.id} m={m} chart={chart} onChange={refresh} />)}
          {busy && <p className="flex items-center gap-2 text-table text-muted-foreground" aria-busy="true"><Loader2 className="size-4 animate-spin" aria-hidden />Working — checking records you are allowed to see…</p>}
          {err && <p role="alert" className="flex items-start gap-2 text-table text-destructive"><AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />{err}</p>}
          {conv?.status && conv.status !== "active" && <p className="text-label text-muted-foreground">This conversation is {conv.status}. Start a new one with +.</p>}
        </div>
        {!!prompts.length && conv?.status === "active" && (
          <div className="flex flex-wrap gap-1.5 border-t px-4 pt-2 pb-0.5" aria-label="Suggestions">
            {prompts.slice(0, 4).map((p) => <button key={p} type="button" disabled={busy} onClick={() => conv && send(conv, p)} className="shrink-0 rounded-full border bg-card px-2.5 py-1 text-label hover:border-primary hover:text-primary disabled:opacity-50">{p}</button>)}
          </div>
        )}
        <form className="space-y-1.5 border-t px-4 py-3" onSubmit={(e) => { e.preventDefault(); if (conv) void send(conv, text); }}>
          <div className="flex items-end gap-2">
            <Textarea rows={2} value={text} maxLength={2000} onChange={(e) => setText(e.target.value)} placeholder={`Ask ${agent.name}…`} aria-label="Question" data-testid="assist-input"
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (conv) void send(conv, text); } }} className="min-h-0 resize-none" disabled={!conv || conv.status !== "active"} />
            <Button type="submit" size="icon" aria-label="Send" disabled={!text.trim() || busy || !conv || conv.status !== "active"} data-testid="assist-send"><Send /></Button>
          </div>
          <p className="text-label text-muted-foreground">AI can be wrong — check the linked records. Nothing changes without your confirmation or an authorized approver. Conversations are not part of the chart.</p>
        </form>
      </SheetContent>
    </Dialog>
  );
}

/** Button + panel. Renders nothing when this user may not use the agent here (feature off, disabled, permission, context). */
export function HMSAssistButton({ agent, context = { type: "workspace" }, label, size = "sm", variant = "ai", autoAsk, testId, panelTestId }: {
  agent: string; context?: AssistContext; label?: string; size?: "sm" | "xs" | "default"; variant?: "ai" | "soft" | "outline" | "ghost";
  autoAsk?: string; testId?: string; panelTestId?: string;
}) {
  const { agent: a } = useAssistAgent(agent, context);
  const [open, setOpen] = React.useState(false);
  if (!a) return null;
  return (
    <>
      <Button size={size} variant={variant} onClick={() => setOpen(true)} data-testid={testId ?? `assist-open-${agent}`}><Bot />{label ?? `Ask ${a.name}`}</Button>
      {open && <HMSAssistSheet agent={a} context={context} open={open} onOpenChange={setOpen} autoAsk={autoAsk} testId={panelTestId} />}
    </>
  );
}
