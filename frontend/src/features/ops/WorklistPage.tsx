import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, CheckCircle2, ListChecks, ShieldCheck } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, LoadingRows, PageHeader, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { get, post } from "@/lib/api";
import { fromNow } from "@/lib/format";
import { ROLE_LABELS } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";
import { type ApprovalT, ApprovalList, CaseDrawer, CaseRow, type CaseT, CATEGORY_LABEL, type TaskT } from "./ops";

type Worklist = { cases: CaseT[]; tasks: TaskT[]; approvals: ApprovalT[]; counts: { cases: number; tasks: number; approvals: number; overdue: number } };
const PRIO: Record<string, React.ComponentProps<typeof Badge>["variant"]> = { urgent: "danger", high: "warning", normal: "neutral", low: "outline" };

export function WorklistPage() {
  const [params, setParams] = useSearchParams();
  const openCase = params.get("case");
  const q = useQuery({ queryKey: ["worklist"], queryFn: () => get<Worklist>("/worklist"), refetchInterval: 60_000 });
  const [cat, setCat] = React.useState<string>("all");
  const cats = React.useMemo(() => [...new Set((q.data?.cases ?? []).map((c) => c.category))], [q.data]);
  const cases = (q.data?.cases ?? []).filter((c) => cat === "all" || c.category === cat);
  const setCase = (id: string | null) => { const n = new URLSearchParams(params); if (id) n.set("case", id); else n.delete("case"); setParams(n, { replace: true }); };
  return (
    <>
      <PageHeader title="My work" description="Cases, tasks and approvals waiting on you or your roles — ordered by severity and time left. Updates live." />
      {q.isError ? <ErrorState error={q.error} retry={q.refetch} /> : (
        <Tabs defaultValue="cases">
          <TabsList>
            <TabsTrigger value="cases">Cases {q.data && <CountPill n={q.data.counts.cases} alert={q.data.counts.overdue > 0} />}</TabsTrigger>
            <TabsTrigger value="tasks">Tasks {q.data && <CountPill n={q.data.counts.tasks} />}</TabsTrigger>
            <TabsTrigger value="approvals">Approvals {q.data && <CountPill n={q.data.counts.approvals} alert={q.data.counts.approvals > 0} />}</TabsTrigger>
          </TabsList>
          <TabsContent value="cases">
            <Card className="overflow-hidden">
              {cats.length > 1 && (
                <div className="flex flex-wrap gap-1.5 border-b p-3">
                  {["all", ...cats].map((c) => <button key={c} onClick={() => setCat(c)} className={cn("rounded-md px-2.5 py-1 text-[13px] font-medium text-muted-foreground hover:bg-muted", cat === c && "bg-accent text-accent-foreground")}>{c === "all" ? "All" : CATEGORY_LABEL[c] ?? c}</button>)}
                </div>
              )}
              {q.isLoading ? <LoadingRows /> : !cases.length ? <EmptyState icon={CheckCircle2} title="No open cases for you" description="Automations open cases here when something needs attention." /> : (
                <ul className="divide-y">{cases.map((c) => <CaseRow key={c.id} c={c} onOpen={setCase} />)}</ul>
              )}
            </Card>
          </TabsContent>
          <TabsContent value="tasks"><Card className="overflow-hidden">{q.isLoading ? <LoadingRows /> : <TaskList tasks={q.data?.tasks ?? []} onOpenCase={setCase} />}</Card></TabsContent>
          <TabsContent value="approvals"><Card className="px-4">{q.isLoading ? <LoadingRows /> : <ApprovalList items={q.data?.approvals ?? []} empty={<EmptyState icon={ShieldCheck} title="Nothing to approve" />} />}</Card></TabsContent>
        </Tabs>
      )}
      <CaseDrawer caseId={openCase} onClose={() => setCase(null)} />
    </>
  );
}

function CountPill({ n, alert }: { n: number; alert?: boolean }) {
  return <span className={cn("ml-1.5 rounded-full px-1.5 py-px text-[11px] tabular", alert ? "bg-destructive text-white" : "bg-muted text-muted-foreground")}>{n}</span>;
}

export function TaskList({ tasks, onOpenCase }: { tasks: TaskT[]; onOpenCase?: (id: string) => void }) {
  const qc = useQueryClient();
  const act = async (t: TaskT, a: string) => {
    try { await post(`/tasks/${t.id}/${a}`); qc.invalidateQueries({ queryKey: ["worklist"] }); qc.invalidateQueries({ queryKey: ["tasks"] }); } catch (e) { toastError(e); }
  };
  if (!tasks.length) return <EmptyState icon={ListChecks} title="No open tasks" />;
  return (
    <ul className="divide-y">{tasks.map((t) => (
      <li key={t.id} className="flex items-start gap-3 px-4 py-3">
        <button onClick={() => act(t, "complete")} className="mt-0.5 size-5 shrink-0 rounded-full border-2 border-input hover:border-primary" aria-label={`Mark "${t.title}" done`} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {t.link ? <Link to={t.link} className="text-[13.5px] font-medium hover:underline">{t.title}</Link> : <span className="text-[13.5px] font-medium">{t.title}</span>}
            {t.priority !== "normal" && <Badge variant={PRIO[t.priority]}>{titleCase(t.priority)}</Badge>}
            {t.status === "in_progress" && <Badge variant="info">In progress</Badge>}
            {t.source !== "manual" && <Badge variant="ai"><Bot />Automation</Badge>}
          </div>
          <p className="text-xs text-muted-foreground">
            {t.assigned_role ? ROLE_LABELS[t.assigned_role] : "Assigned to you"}{t.patient_name ? ` · ${t.patient_name}` : ""} · created {fromNow(t.created_at)}
            {t.due_at && <> · <span className={cn(new Date(t.due_at) < new Date() && "font-medium text-destructive")}>due {fromNow(t.due_at)}</span></>}
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          {!t.acknowledged_at && <button className="rounded-md px-2 py-1 text-xs font-medium text-primary hover:bg-accent" onClick={() => act(t, "acknowledge")}>Acknowledge</button>}
          {t.status === "open" && <button className="rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted" onClick={() => act(t, "start")}>Start</button>}
          {t.case_id && onOpenCase && <button className="rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted" onClick={() => onOpenCase(t.case_id!)}>Case</button>}
        </div>
      </li>
    ))}</ul>
  );
}

