import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, CheckCircle2, ChevronRight, ListChecks, ShieldCheck } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, LoadingRows, PageHeader, toastError } from "@/components/common";
import { dueLabel, StatusChip } from "@/components/common/Status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Segmented, TabCount, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { get, post } from "@/lib/api";
import { fromNow } from "@/lib/format";
import { ROLE_LABELS } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";
import { type ApprovalT, ApprovalList, CASE_COLS, CaseDrawer, CaseListHeader, CaseRow, type CaseT, CATEGORY_LABEL, ownerLabel, SlaBadge, type TaskT } from "./ops";

type Worklist = { cases: CaseT[]; tasks: TaskT[]; approvals: ApprovalT[]; counts: { cases: number; tasks: number; approvals: number; overdue: number } };
const PRIO: Record<string, React.ComponentProps<typeof Badge>["variant"]> = { urgent: "danger", high: "warning", normal: "neutral", low: "neutral" };

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
  const patients = [...new Set(items.map((c) => c.patient_name).filter(Boolean))];
  return (
    <li>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className={cn(CASE_COLS, "w-full bg-subtle px-4 py-(--row-y) text-left text-table hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50")}>
        <ChevronRight className={cn("mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")} aria-hidden />
        <span className="min-w-0">
          <span className="block text-body font-medium text-heading">{CATEGORY_LABEL[first.category] ?? titleCase(first.category)}: {items.length} similar alerts</span>
          <span className="block truncate text-label text-muted-foreground">Most urgent: {first.title}</span>
        </span>
        <span className="hidden min-w-0 truncate text-muted-foreground md:block">{patients.length ? `${patients.length} patient${patients.length === 1 ? "" : "s"}` : "—"}</span>
        <span className="hidden min-w-0 truncate md:block">{ownerLabel(first)}</span>
        <span className="hidden md:block">{first.due_at ? <SlaBadge c={first} /> : "—"}</span>
        <span><StatusChip status={overdue ? "overdue" : "not_started"} label={overdue ? `${overdue} overdue` : `${items.length} open`} /></span>
      </button>
      {open && <ul className="divide-y border-t">{items.map((c) => <CaseRow key={c.id} c={c} onOpen={onOpen} compact />)}</ul>}
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
      <PageHeader title="My work" description="Everything waiting on you or your team — clinical severity first, then overdue work." />
      {q.isError ? <ErrorState error={q.error} retry={q.refetch} /> : (
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="cases">Cases {q.data && <TabCount n={q.data.counts.cases} />}</TabsTrigger>
            <TabsTrigger value="tasks">Tasks {q.data && <TabCount n={q.data.counts.tasks} />}</TabsTrigger>
            <TabsTrigger value="approvals">Approvals {q.data && <TabCount n={q.data.counts.approvals} />}</TabsTrigger>
          </TabsList>
          <TabsContent value="cases">
            <Card className="overflow-hidden">
              {cats.length > 1 && (
                <div className="flex flex-wrap items-center gap-2 border-b p-3">
                  <Segmented label="Filter cases by area" value={cat} onChange={setCat}
                    options={["all", ...cats].map((c) => ({ value: c, label: c === "all" ? "All" : CATEGORY_LABEL[c] ?? c, count: c === "all" ? q.data?.cases.length : q.data?.cases.filter((x) => x.category === c).length }))} />
                </div>
              )}
              {q.isLoading ? <LoadingRows /> : !cases.length ? <EmptyState icon={CheckCircle2} title="No open cases for you" description="Automations open cases here when something needs attention." /> : (
                <ul className="divide-y"><CaseListHeader />{groupCases(cases).map((c) => "group" in c ? <CaseGroup key={c.group} items={c.items} onOpen={setCase} /> : <CaseRow key={c.id} c={c} onOpen={setCase} />)}</ul>
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
            {t.link ? <Link to={t.link} className="text-body font-medium hover:underline">{t.title}</Link> : <span className="text-body font-medium">{t.title}</span>}
            {t.priority !== "normal" && <Badge variant={PRIO[t.priority]}>{titleCase(t.priority)}</Badge>}
            {t.status === "in_progress" && <Badge variant="info">In progress</Badge>}
            {t.source !== "manual" && <Badge variant="ai"><Bot />Automation</Badge>}
          </div>
          <p className="text-label text-muted-foreground">
            Owner: {t.assigned_role ? ROLE_LABELS[t.assigned_role] : "You"}{t.patient_name ? ` · ${t.patient_name}` : ""} · created {fromNow(t.created_at)}
            {t.due_at && <> · <span className={cn("inline-flex items-center gap-1", new Date(t.due_at) < new Date() && "font-medium text-warning-foreground")}>{dueLabel(t.due_at)}</span></>}
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          {!t.acknowledged_at && <Button variant="outline" size="xs" onClick={() => act(t, "acknowledge")}>Acknowledge</Button>}
          {t.status === "open" && <Button variant="ghost" size="xs" onClick={() => act(t, "start")}>Start</Button>}
          {t.case_id && onOpenCase && <Button variant="ghost" size="xs" onClick={() => onOpenCase(t.case_id!)}>Case</Button>}
        </div>
      </li>
    ))}</ul>
  );
}

