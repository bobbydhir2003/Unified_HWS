import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { StatusChip } from "@/components/common/Status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type AgentRow = { key: string; name: string; can_run: boolean };
type Run = { status: string; mode: "openai" | "rule_based" | string; model: string | null; output: string | null; error: string | null;
  tool_calls: { tool: string; ok: boolean }[]; approvals: string[] };

/**
 * Contextual AI: runs an existing agent (Agent Studio) with a preset question from inside a workspace.
 * Shown only when the user may run that agent (server `can_run`: ai:use + the agent's permission + enabled). The result is
 * labelled Live AI vs Simulated (rule-based); anything the agent proposes waits in My work → Approvals.
 */
export function AskAI({ agent, question, label, size = "sm", variant = "soft" }: {
  agent: string; question: string; label: string; size?: "sm" | "xs"; variant?: "soft" | "outline" | "ghost";
}) {
  const { can } = useAuth();
  const agents = useQuery({ queryKey: ["ai", "agents"], queryFn: () => get<AgentRow[]>("/agents"), enabled: can("ai:use"), staleTime: 5 * 60_000 });
  const [open, setOpen] = React.useState(false);
  const [run, setRun] = React.useState<Run | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const a = agents.data?.find((x) => x.key === agent);
  if (!can("ai:use") || !a?.can_run) return null;

  const go = async () => {
    setOpen(true); setRun(null); setErr(null); setBusy(true);
    try { setRun(await post<Run>(`/agents/${agent}/run`, { input: question })); } catch (e) { setErr(e instanceof Error ? e.message : "The assistant could not run."); }
    finally { setBusy(false); }
  };
  const live = run?.mode === "openai";
  return (
    <>
      <Button size={size} variant={variant} onClick={go} data-testid={`ask-ai-${agent}`}><Sparkles />{label}</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex flex-wrap items-center gap-2">{a.name}
              {run && (live ? <Badge variant="ai">Live AI{run.model ? ` · ${run.model}` : ""}</Badge> : <Badge variant="warning">Simulated · rule-based summary</Badge>)}
            </DialogTitle>
            <DialogDescription>{question}</DialogDescription>
          </DialogHeader>
          {busy && <p className="text-[13.5px] text-muted-foreground">Working… the assistant can only read data you are allowed to see.</p>}
          {err && <p role="alert" className="text-[13.5px] text-destructive">{err}</p>}
          {run && (
            <div className="space-y-3 text-[13.5px]">
              {run.status === "failed" ? <p role="alert" className="text-destructive">{run.error ?? "The assistant failed."}</p>
                : <p className="max-h-[50vh] overflow-auto whitespace-pre-line leading-relaxed">{run.output}</p>}
              {!!run.tool_calls?.length && <p className="text-xs text-muted-foreground">Looked at: {[...new Set(run.tool_calls.map((t) => t.tool.replace(/_/g, " ")))].join(", ")}</p>}
              {!!run.approvals?.length && (
                <p className="flex flex-wrap items-center gap-2"><StatusChip status="needs_approval" label={`${run.approvals.length} proposal(s) need approval`} />
                  <Link to="/worklist?tab=approvals" className="text-primary hover:underline">Review in My work</Link></p>
              )}
              <p className="text-xs text-muted-foreground">AI summaries can be incomplete or wrong — check the source records before acting. Nothing is changed without a person's approval.</p>
            </div>
          )}
          <DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>Close</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
