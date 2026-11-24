import { useQuery } from "@tanstack/react-query";
import { assistName } from "@/lib/assist";
import { AlertTriangle, Sparkles } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { ProvenanceChip } from "@/components/common/Status";
import { Button } from "@/components/ui/button";
import { Dialog, DialogDescription, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/misc";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type AgentRow = { key: string; name: string; can_run: boolean };
export type AgentRun = { status: string; mode: "openai" | "rule_based" | string; model: string | null; output: string | null; error: string | null;
  tool_calls: { tool: string; ok: boolean }[]; approvals: string[]; ai_source?: string | null; trigger?: string };

const SOURCE: Record<string, string> = {}; // only non-platform AI sources need a label; none remain

/** Live vs simulated is decided only by the server's `mode`; a rule-based answer is never labelled as OpenAI. */
export function RunProvenance({ run }: { run: Pick<AgentRun, "mode" | "model"> & Partial<Pick<AgentRun, "ai_source" | "status" | "error">> }) {
  const src = run.ai_source && SOURCE[run.ai_source];
  return (
    <>
      {run.mode === "openai"
        ? <ProvenanceChip kind="live" detail={[run.model, src].filter(Boolean).join(" · ")} />
        : <ProvenanceChip kind="simulated" label={run.error?.startsWith("AI provider unavailable") ? "Simulated · AI unavailable" : "Simulated · rule-based summary"} />}
      {run.status === "limit_reached" && <span className="text-label text-warning-foreground" data-testid="run-limit">Tool-call limit reached — answer uses results gathered so far</span>}
    </>
  );
}

/** The shared body of an AI result: answer, evidence (records read), proposals awaiting approval. */
export function AIRunResult({ run }: { run: AgentRun }) {
  const looked = [...new Set((run.tool_calls ?? []).map((t) => t.tool.replace(/_/g, " ")))];
  return (
    <div className="space-y-4 text-body">
      <section>
        <h3 className="mb-1 text-label font-medium text-muted-foreground">Answer</h3>
        {run.status === "failed"
          ? <p role="alert" className="flex items-start gap-2 text-destructive"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{run.error ?? "The assistant could not complete this request."}</p>
          : <p className="whitespace-pre-line leading-relaxed">{run.output}</p>}
      </section>
      {!!looked.length && (
        <section>
          <h3 className="mb-1 text-label font-medium text-muted-foreground">Evidence — records it read</h3>
          <p className="text-table text-muted-foreground">{looked.join(" · ")}</p>
        </section>
      )}
      {!!run.approvals?.length && (
        <section className="rounded-lg border border-warning/40 bg-warning-soft/40 p-3">
          <p className="flex flex-wrap items-center gap-2"><ProvenanceChip kind="pending" />
            <span className="font-medium text-heading">{run.approvals.length} proposed action{run.approvals.length === 1 ? "" : "s"}</span></p>
          <p className="mt-1 text-table text-muted-foreground">Nothing changes until a person with permission approves it.</p>
          <Link to="/worklist?tab=approvals" className="mt-2 inline-block text-table font-medium text-primary hover:underline">Review in My work</Link>
        </section>
      )}
    </div>
  );
}

/**
 * Contextual AI: runs an existing agent (Agent Studio) with a preset question from inside a workspace, in a side panel so
 * the record stays visible. Shown only when the user may run that agent (server `can_run`). Proposals wait in My work.
 */
export function AskAI({ agent, question, label, size = "sm", variant = "ai" }: {
  agent: string; question: string; label: string; size?: "sm" | "xs"; variant?: "ai" | "soft" | "outline" | "ghost";
}) {
  const { can } = useAuth();
  const agents = useQuery({ queryKey: ["ai", "agents"], queryFn: () => get<AgentRow[]>("/agents"), enabled: can("ai:use"), staleTime: 5 * 60_000 });
  const [open, setOpen] = React.useState(false);
  const [run, setRun] = React.useState<AgentRun | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const a = agents.data?.find((x) => x.key === agent);
  if (!can("ai:use") || !a?.can_run) return null;

  const go = async () => {
    setOpen(true); setRun(null); setErr(null); setBusy(true);
    try { setRun(await post<AgentRun>(`/agents/${agent}/run`, { input: question })); } catch (e) { setErr(e instanceof Error ? e.message : "The assistant could not run."); }
    finally { setBusy(false); }
  };
  return (
    <>
      <Button size={size} variant={variant} onClick={go} data-testid={`ask-ai-${agent}`}><Sparkles />{label}</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <SheetContent size="md" aria-describedby="ask-ai-question" data-testid="ai-panel">
          <div className="space-y-2 border-b px-5 py-4 pr-12">
            <DialogTitle className="flex items-center gap-2"><Sparkles className="size-4 text-ai" aria-hidden />{assistName(a.key, a.name)}</DialogTitle>
            <div className="flex flex-wrap gap-1.5">
              {run && <RunProvenance run={run} />}
              <ProvenanceChip kind="rule" label="Read-only · your permissions" />
            </div>
            <DialogDescription id="ask-ai-question" className="text-table">You asked: “{question}”</DialogDescription>
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-4">
            {busy && <div className="space-y-2" aria-busy="true" aria-label="Working"><p className="text-table text-muted-foreground">Working… the assistant can only read data you are allowed to see.</p><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-5/6" /><Skeleton className="h-4 w-2/3" /></div>}
            {err && <p role="alert" className="flex items-start gap-2 text-body text-destructive"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{err}</p>}
            {run && <AIRunResult run={run} />}
          </div>
          <div className="space-y-3 border-t bg-subtle px-5 py-3">
            <p className="text-label text-muted-foreground">AI output can be incomplete or wrong — check the source records before acting. This answer is not saved to the chart, and nothing is changed without a person’s approval.</p>
            <div className="flex justify-end gap-2">
              {run && <Button variant="outline" size="sm" onClick={go} disabled={busy}>Ask again</Button>}
              <Button variant="outline" size="sm" onClick={() => setOpen(false)}>Close</Button>
            </div>
          </div>
        </SheetContent>
      </Dialog>
    </>
  );
}
