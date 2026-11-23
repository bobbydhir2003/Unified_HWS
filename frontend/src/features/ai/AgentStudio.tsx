import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Play, Settings2, ShieldCheck, ThumbsDown, ThumbsUp, Wrench } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { EmptyState, LoadingRows, PageHeader, Stat, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProvenanceChip } from "@/components/common/Status";
import { RunProvenance } from "./AskAI";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Checkbox, Switch } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import { titleCase } from "@/lib/utils";

type Agent = { key: string; name: string; purpose: string; instructions: string; allowed_tools: string[]; model: string | null; trigger: string; required_permission: string;
  max_tool_calls: number; timeout_seconds: number; max_cost_usd: number; enabled: boolean; version: number; can_run: boolean; runs_30d: number; failed_30d: number; cost_30d_usd: number; demo_override?: boolean };
type ToolT = { name: string; description: string; permission: string; kind: string };
type Run = { id: string; agent_key: string; mode: string; model: string | null; status: string; input: string; output: string | null; tool_calls: { tool: string; ok: boolean; arguments: unknown; result_preview: string }[];
  approvals: string[]; cost_usd: number | null; latency_ms: number | null; error: string | null; started_at: string };

const usd = (n: number | null | undefined) => (n == null ? "—" : n > 0 && n < 0.01 ? "< $0.01" : "$" + n.toFixed(2));

export function AgentStudio() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const agents = useQuery({ queryKey: ["ai", "agents"], queryFn: () => get<Agent[]>("/agents") });
  const tools = useQuery({ queryKey: ["ai", "tools"], queryFn: () => get<ToolT[]>("/agents/tools") });
  const provider = useQuery({ queryKey: ["ai", "provider"], queryFn: () => get<{ live: boolean; active: string }>("/ai/provider") });
  const [runFor, setRunFor] = React.useState<Agent | null>(null);
  const [edit, setEdit] = React.useState<Agent | null>(null);
  const [input, setInput] = React.useState("");
  const [result, setResult] = React.useState<Run | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [draft, setDraft] = React.useState<Partial<Agent> & { note?: string }>({});
  const manage = can("ai:manage");
  return (
    <>
      <PageHeader title="Agent Studio" description="Each agent works only through backend tools, under your permissions. Anything that would change data becomes a proposal in the approval queue."
        actions={provider.data && (provider.data.live ? <ProvenanceChip kind="live" label={`Live: ${provider.data.active === "openai" ? "OpenAI" : titleCase(provider.data.active)}`} /> : <ProvenanceChip kind="simulated" label="No AI provider — rule-based summaries" />)} />
      {agents.isLoading ? <LoadingRows rows={6} /> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{agents.data?.map((a) => (
          <Card key={a.key} className="flex flex-col">
            <CardHeader className="flex-row items-start justify-between gap-2">
              <div className="flex items-center gap-2"><span className="rounded-lg bg-ai-soft p-2 text-ai"><Bot className="size-4" /></span><div><CardTitle className="text-section">{a.name}</CardTitle><p className="text-xs text-muted-foreground">v{a.version} · {a.trigger === "feature" ? "runs in its workflow" : "on demand"}{a.demo_override ? " · edited in this demo session" : ""}</p></div></div>
              {manage && <Switch checked={a.enabled} aria-label={`Enable ${a.name}`} onCheckedChange={async (v) => { try { await put(`/agents/${a.key}`, { enabled: v }); qc.invalidateQueries({ queryKey: ["ai", "agents"] }); } catch (e) { toastError(e); } }} />}
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-3 text-table">
              <p className="text-muted-foreground">{a.purpose}</p>
              <div className="flex flex-wrap gap-1">{a.allowed_tools.map((t) => <Badge key={t} variant={t.startsWith("propose") ? "warning" : "neutral"} title={t.startsWith("propose") ? "Creates an approval request — a person must approve" : "Reads data only"}>{t.startsWith("propose") ? "Proposes: " + t.replace(/^propose_/, "").replace(/_/g, " ") + " (needs approval)" : "Reads: " + t.replace(/^(get|list)_/, "").replace(/_/g, " ")}</Badge>)}
                {!a.allowed_tools.length && <span className="text-xs text-muted-foreground">Uses its feature's own pipeline</span>}</div>
              <p className="text-label text-muted-foreground">{a.runs_30d} runs in 30 days · {a.failed_30d} failed · cost {usd(a.cost_30d_usd)}</p>
              <p className="text-label text-muted-foreground">Limits: up to {a.max_tool_calls} steps, {a.timeout_seconds} s, ${a.max_cost_usd.toFixed(2)} per run</p>
              <div className="mt-auto flex gap-2">
                {a.can_run && <Button size="sm" variant="outline" onClick={() => { setRunFor(a); setInput(""); setResult(null); }}><Play />Run</Button>}
                {a.trigger === "feature" && <Button size="sm" variant="outline" asChild><Link to={a.key === "document_intelligence" ? "/documents" : a.key === "medical_scribe" ? "/encounters" : "/patients"}>Open</Link></Button>}
                {manage && <Button size="sm" variant="ghost" onClick={() => { setEdit(a); setDraft({ instructions: a.instructions, allowed_tools: a.allowed_tools, model: a.model, max_tool_calls: a.max_tool_calls, timeout_seconds: a.timeout_seconds, max_cost_usd: a.max_cost_usd }); }}><Settings2 />Configure</Button>}
              </div>
            </CardContent>
          </Card>))}</div>
      )}
      <Dialog open={!!runFor} onOpenChange={(o) => !o && setRunFor(null)}>
        <DialogContent size="lg"><DialogHeader><DialogTitle>{runFor?.name}</DialogTitle><DialogDescription>{runFor?.purpose}</DialogDescription></DialogHeader>
          <Field label="Request"><Textarea rows={3} value={input} onChange={(e) => setInput(e.target.value)} placeholder="e.g. What needs attention on Med-Surg this shift?" /></Field>
          {result && (
            <div className="space-y-2 rounded-lg border p-3 text-table">
              <div className="flex flex-wrap items-center gap-2"><Badge variant={result.status === "succeeded" ? "success" : "danger"}>{result.status}</Badge><RunProvenance run={result} />
                <span className="text-xs text-muted-foreground">{result.latency_ms} ms · {usd(result.cost_usd)}</span>
                <span className="ml-auto flex gap-1"><Button size="icon" variant="ghost" aria-label="Helpful" onClick={() => post("/ai/feedback", { agent_run_id: result.id, rating: "up" }).then(() => toast.success("Thanks"))}><ThumbsUp /></Button>
                  <Button size="icon" variant="ghost" aria-label="Not helpful" onClick={() => post("/ai/feedback", { agent_run_id: result.id, rating: "down" }).then(() => toast.success("Thanks"))}><ThumbsDown /></Button></span></div>
              <p className="whitespace-pre-wrap">{result.output ?? result.error}</p>
              <details><summary className="cursor-pointer text-xs text-muted-foreground"><Wrench className="mr-1 inline size-3" />{result.tool_calls.length} tool call(s)</summary>
                <ul className="mt-1 space-y-1 text-xs">{result.tool_calls.map((c, i) => <li key={i}><code>{c.tool}</code> {c.ok ? "✓" : "✗"} <span className="text-muted-foreground">{c.result_preview}</span></li>)}</ul></details>
              {result.approvals.length > 0 && <p className="flex items-center gap-1 text-xs"><ShieldCheck className="size-3.5 text-warning" />{result.approvals.length} proposal(s) waiting for approval in <Link className="text-primary hover:underline" to="/worklist">My work → Approvals</Link></p>}
            </div>
          )}
          <DialogFooter><Button variant="outline" onClick={() => setRunFor(null)}>Close</Button>
            <Button loading={busy} disabled={input.trim().length < 2} onClick={async () => { setBusy(true); try { setResult(await post<Run>(`/agents/${runFor!.key}/run`, { input })); qc.invalidateQueries({ queryKey: ["ai", "agents"] }); } catch (e) { toastError(e); } finally { setBusy(false); } }}><Play />Run</Button></DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)}>
        <DialogContent size="lg"><DialogHeader><DialogTitle>Configure {edit?.name}</DialogTitle><DialogDescription>Saving creates a new version (v{(edit?.version ?? 0) + 1}). Tools still check the invoking user's permissions.</DialogDescription></DialogHeader>
          <Field label="Instructions"><Textarea rows={5} value={draft.instructions ?? ""} onChange={(e) => setDraft({ ...draft, instructions: e.target.value })} /></Field>
          <Field label="Allowed tools"><div className="grid gap-1 sm:grid-cols-2">{tools.data?.map((t) => (
            <label key={t.name} className="flex items-start gap-2 text-table"><Checkbox className="mt-0.5" checked={draft.allowed_tools?.includes(t.name)} onCheckedChange={(v) => setDraft({ ...draft, allowed_tools: v ? [...(draft.allowed_tools ?? []), t.name] : (draft.allowed_tools ?? []).filter((x) => x !== t.name) })} />
              <span><code>{t.name}</code>{t.kind === "propose" && <Badge variant="warning" className="ml-1 px-1 py-0 text-label">approval</Badge>}<span className="block text-xs text-muted-foreground">{t.description} · needs {t.permission}</span></span></label>))}</div></Field>
          <div className="grid grid-cols-4 gap-3">
            <Field label="Model"><Input value={draft.model ?? ""} placeholder="default" onChange={(e) => setDraft({ ...draft, model: e.target.value || null })} /></Field>
            <Field label="Max tool calls"><Input inputMode="numeric" value={draft.max_tool_calls ?? ""} onChange={(e) => setDraft({ ...draft, max_tool_calls: Number(e.target.value) })} /></Field>
            <Field label="Timeout (s)"><Input inputMode="numeric" value={draft.timeout_seconds ?? ""} onChange={(e) => setDraft({ ...draft, timeout_seconds: Number(e.target.value) })} /></Field>
            <Field label="Cost limit ($)"><Input inputMode="decimal" value={draft.max_cost_usd ?? ""} onChange={(e) => setDraft({ ...draft, max_cost_usd: Number(e.target.value) })} /></Field>
          </div>
          <Field label="Change note"><Input value={draft.note ?? ""} onChange={(e) => setDraft({ ...draft, note: e.target.value })} /></Field>
          <DialogFooter><Button variant="outline" onClick={() => setEdit(null)}>Cancel</Button>
            <Button onClick={async () => { try { await put(`/agents/${edit!.key}`, draft); toast.success("Saved new version"); setEdit(null); qc.invalidateQueries({ queryKey: ["ai", "agents"] }); } catch (e) { toastError(e); } }}>Save version</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

type Gov = { window_days: number; active_provider: string; phi_allowed: boolean; phi_sent_externally: number;
  features: { kind: string; provider: string; calls: number; failed: number; cost_usd: number; input_tokens: number; output_tokens: number; avg_latency_ms: number | null }[];
  agents: { agent: string; mode: string; runs: number; problems: number; cost_usd: number; avg_latency_ms: number | null }[]; feedback: { up: number; down: number }; recent_problems: Run[] };

export function AIGovernancePage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["ai", "governance"], queryFn: () => get<Gov>("/ai/governance") });
  const g = q.data;
  const totalCost = (g?.features.reduce((a, f) => a + f.cost_usd, 0) ?? 0) + (g?.agents.reduce((a, f) => a + f.cost_usd, 0) ?? 0);
  return (
    <>
      <PageHeader title="AI governance" description="Usage, cost, failures, feedback and data-handling posture across every AI feature and agent." actions={<Button variant="outline" asChild><Link to="/admin/ai-settings">Provider & models</Link></Button>} />
      {!g ? <LoadingRows rows={6} /> : (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Active provider" icon={Bot} tone="ai" value={titleCase(g.active_provider)} sub={g.phi_allowed ? "Patient data allowed (BAA required)" : "Patient data blocked from external AI"} />
            <Stat label={`Cost (${g.window_days} d)`} icon={Settings2} value={usd(totalCost)} sub="From configured price table" />
            <Stat label="Patient data sent externally" icon={ShieldCheck} tone={g.phi_sent_externally ? "warning" : "success"} value={g.phi_sent_externally} sub="AI calls flagged as PHI" />
            <Stat label="Feedback" icon={ThumbsUp} value={`${g.feedback.up} 👍 · ${g.feedback.down} 👎`} />
          </div>
          <Card className="overflow-hidden"><CardHeader><CardTitle>AI features</CardTitle></CardHeader>
            {!g.features.length ? <EmptyState title="No AI activity yet" /> : <Table><THead><TR><TH>Feature</TH><TH>Provider</TH><TH className="text-right">Calls</TH><TH className="text-right">Failed</TH><TH className="text-right">Tokens in/out</TH><TH className="text-right">Avg latency</TH><TH className="text-right">Cost</TH></TR></THead>
              <TBody>{g.features.map((f) => <TR key={f.kind + f.provider}><TD>{titleCase(f.kind.replace(/_/g, " "))}</TD><TD>{f.provider}</TD><TD className="text-right tabular">{f.calls}</TD><TD className="text-right tabular">{f.failed}</TD><TD className="text-right tabular">{f.input_tokens}/{f.output_tokens}</TD><TD className="text-right tabular">{f.avg_latency_ms ?? "—"} ms</TD><TD className="text-right tabular">{usd(f.cost_usd)}</TD></TR>)}</TBody></Table>}</Card>
          <Card className="overflow-hidden"><CardHeader><CardTitle>Agents</CardTitle></CardHeader>
            {!g.agents.length ? <EmptyState title="No agent runs yet" /> : <Table><THead><TR><TH>Agent</TH><TH>Mode</TH><TH className="text-right">Runs</TH><TH className="text-right">Problems</TH><TH className="text-right">Avg latency</TH><TH className="text-right">Cost</TH></TR></THead>
              <TBody>{g.agents.map((a) => <TR key={a.agent + a.mode}><TD>{titleCase(a.agent.replace(/_/g, " "))}</TD><TD>{a.mode}</TD><TD className="text-right tabular">{a.runs}</TD><TD className="text-right tabular">{a.problems}</TD><TD className="text-right tabular">{a.avg_latency_ms ?? "—"} ms</TD><TD className="text-right tabular">{usd(a.cost_usd)}</TD></TR>)}</TBody></Table>}</Card>
          <Card><CardHeader><CardTitle>Recent failed or limited runs</CardTitle></CardHeader>
            <CardContent>{!g.recent_problems.length ? <p className="text-table text-muted-foreground">None.</p> : (
              <ul className="divide-y">{g.recent_problems.map((r) => <li key={r.id} className="flex flex-wrap items-center gap-2 py-2 text-table"><Badge variant="danger">{r.status}</Badge><span className="font-medium">{titleCase(r.agent_key.replace(/_/g, " "))}</span><span className="flex-1 truncate text-muted-foreground">{r.error ?? r.output}</span><span className="text-xs text-muted-foreground">{fmtDateTime(r.started_at)}</span>
                <Button size="xs" variant="outline" onClick={async () => { try { await post(`/agents/runs/${r.id}/retry`); toast.success("Retried"); qc.invalidateQueries({ queryKey: ["ai"] }); } catch (e) { toastError(e); } }}>Retry</Button></li>)}</ul>)}</CardContent></Card>
          <EvaluationsCard />
        </div>
      )}
    </>
  );
}

type EvalRun = { id: string; suite: string; provider: string; model: string | null; samples: number; score: number; metrics: Record<string, unknown>; cases: { id: string; passed?: boolean; correct?: number; total?: number; errors?: { field: string; expected: unknown; got: unknown }[]; failure?: string | null }[]; created_at: string };
const SUITE_LABEL: Record<string, string> = { document_extraction_v1: "Document extraction", tool_gate_v1: "Agent tool safety gate" };

function EvaluationsCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["ai", "evaluations"], queryFn: () => get<{ suites: string[]; runs: EvalRun[] }>("/ai/evaluations") });
  const [busy, setBusy] = React.useState<string | null>(null);
  const [open, setOpen] = React.useState<EvalRun | null>(null);
  const latest = (s: string) => q.data?.runs.find((r) => r.suite === s);
  const run = async (s: string) => {
    setBusy(s);
    try { await post(`/ai/evaluations/${s}`); toast.success("Evaluation finished"); qc.invalidateQueries({ queryKey: ["ai", "evaluations"] }); } catch (e) { toastError(e); } finally { setBusy(null); }
  };
  return (
    <Card>
      <CardHeader><CardTitle>Evaluations</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <p className="text-table text-muted-foreground">Runs against synthetic labeled samples only. Scores describe these samples, not clinical accuracy.</p>
        <div className="grid gap-3 md:grid-cols-2">
          {(q.data?.suites ?? []).map((s) => {
            const r = latest(s);
            return (
              <div key={s} className="rounded-lg border p-3" data-testid={`eval-${s}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-body font-medium">{SUITE_LABEL[s] ?? s}</span>
                  <Button size="xs" variant="outline" loading={busy === s} onClick={() => run(s)}>Run</Button>
                </div>
                {r ? (
                  <button type="button" className="mt-2 block w-full text-left text-table hover:underline" onClick={() => setOpen(r)}>
                    <span className="text-lg font-semibold tabular">{Math.round(r.score * 100)}%</span> <span className="text-muted-foreground">on {r.samples} samples · {r.provider}{r.model ? ` / ${r.model}` : ""} · {fmtDateTime(r.created_at)}</span>
                  </button>
                ) : <p className="mt-2 text-table text-muted-foreground">Not run yet.</p>}
              </div>
            );
          })}
        </div>
      </CardContent>
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{open ? SUITE_LABEL[open.suite] ?? open.suite : ""}</DialogTitle><DialogDescription>Per-sample results. Expected values come from the synthetic labels.</DialogDescription></DialogHeader>
          <ul className="max-h-[60vh] divide-y overflow-auto text-table">
            {open?.cases.map((c) => (
              <li key={c.id} className="py-2">
                <div className="flex items-center gap-2"><span className="font-mono text-xs">{c.id}</span>
                  {c.passed !== undefined ? <Badge variant={c.passed ? "success" : "danger"}>{c.passed ? "refused as expected" : "NOT refused"}</Badge> : <Badge variant={c.correct === c.total ? "success" : "warning"}>{c.correct}/{c.total} fields</Badge>}
                </div>
                {c.errors?.map((e) => <p key={e.field} className="text-muted-foreground">{e.field}: expected <code>{String(e.expected)}</code>, got <code>{String(e.got)}</code></p>)}
                {c.failure && <p className="text-destructive">{c.failure}</p>}
              </li>
            ))}
          </ul>
          <DialogFooter><Button variant="outline" onClick={() => setOpen(null)}>Close</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
