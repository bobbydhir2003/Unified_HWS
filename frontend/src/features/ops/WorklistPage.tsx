import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, CheckCircle2, ChevronRight, ListChecks, ShieldCheck } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, LoadingRows, PageHeader, toastError } from "@/components/common";
import { StatusChip } from "@/components/common/Status";
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

/** Group cases that come from the same rule (e.g. 16 staffing gaps) so one row stands for many. */
function groupCases(cases: CaseT[]): (CaseT | { group: string; items: CaseT[] })[] {
  const byKind = new Map<string, CaseT[]>();
  for (const c of cases) byKind.set(c.kind, [...(byKind.get(c.kind) ?? []), c]);
  const seen = new Set<string>();
  const out: (CaseT | { group: string; items: CaseT[] })[] = [];
  for (const c of cases) {
    const items = byKind.get(c.kind)!;
    if (items.length < 3) out.push(c);
    else if (!seen.has(c.kind)) { seen.add(c.kind); out.push({ group: c.kind, items }); }
  }
  return out;
}

function CaseGroup({ items, onOpen }: { items: CaseT[]; onOpen: (id: string) => void }) {
  const [open, setOpen] = React.useState(false);
  const first = items[0];
  const overdue = items.filter((c) => c.overdue).length;
  return (
    <li>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:outline-none">
        <ChevronRight className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")} />
        <div className="min-w-0 flex-1">
          <p className="text-[13.5px] font-medium">{CATEGORY_LABEL[first.category] ?? titleCase(first.category)}: {items.length} similar alerts</p>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">Most urgent: {first.title}{overdue ? ` · ${overdue} overdue` : ""}</p>
        </div>
        <StatusChip status={overdue ? "urgent" : "not_started"} label={overdue ? `${overdue} overdue` : `${items.length} open`} />
      </button>
      {open && <ul className="divide-y border-t bg-muted/20">{items.map((c) => <CaseRow key={c.id} c={c} onOpen={onOpen} compact />)}</ul>}
    </li>
  );
}

export function WorklistPage() {
  const [params, setParams] = useSearchParams();
  const openCase = params.get("case");
  const q = useQuery({ queryKey: ["worklist"], queryFn: () => get<Worklist>("/worklist"), refetchInterval: 60_000 });
  // Open on the tab that actually has work (or the one asked for in the URL), never on an empty tab by default.
  const requested = params.get("tab");
  const counts = q.data?.counts;
  const auto = !counts ? "cases" : counts.approvals ? "approvals" : counts.cases ? "cases" : counts.tasks ? "tasks" : "cases";
  const tab = requested && ["cases", "tasks", "approvals"].includes(requested) ? requested : auto;
  const setTab = (t: string) => { const n = new URLSearchParams(params); n.set("tab", t); setParams(n, { replace: true }); };
  const [cat, setCat] = React.useState<string>("all");
  const cats = React.useMemo(() => [...new Set((q.data?.cases ?? []).map((c) => c.category))], [q.data]);
  const cases = (q.data?.cases ?? []).filter((c) => cat === "all" || c.category === cat);
  const setCase = (id: string | null) => { const n = new URLSearchParams(params); if (id) n.set("case", id); else n.delete("case"); setParams(n, { replace: true }); };
  return (
    <>
      <PageHeader title="My work" description="Everything waiting on you or your team, most urgent first. Cases are problems found automatically by rules; tasks are pieces of work assigned to you; approvals are decisions only you can make." />
      {q.isError ? <ErrorState error={q.error} retry={q.refetch} /> : (
        <Tabs value={tab} onValueChange={setTab}>
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
                <ul className="divide-y">{groupCases(cases).map((c) => "group" in c ? <CaseGroup key={c.group} items={c.items} onOpen={setCase} /> : <CaseRow key={c.id} c={c} onOpen={setCase} />)}</ul>
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

