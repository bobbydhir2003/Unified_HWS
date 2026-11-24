import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, CheckCircle2, ChevronRight, ListChecks, Search, ShieldCheck } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, LoadingRows, PageHeader, toastError } from "@/components/common";
import { WorkPanel } from "@/components/common/DataTable";
import { Input, NativeSelect } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/misc";
import { dueLabel, StatusChip } from "@/components/common/Status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TabCount, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { get, post } from "@/lib/api";
import { fromNow } from "@/lib/format";
import { ROLE_LABELS } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";
import { type ApprovalT, ApprovalList, OtherApprovalList, type OtherApprovalT, CaseDrawer, type CaseT, CATEGORY_LABEL, ownerLabel, SeverityIcon, SlaBadge, type TaskT } from "./ops";

type Worklist = { cases: CaseT[]; tasks: TaskT[]; approvals: ApprovalT[]; other_approvals?: OtherApprovalT[]; counts: { cases: number; tasks: number; approvals: number; overdue: number } };
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

function CaseGroup({ items, onOpen, openId }: { items: CaseT[]; onOpen: (id: string) => void; openId: string | null }) {
  const [open, setOpen] = React.useState(false);
  const first = items[0];
  const overdue = items.filter((c) => c.overdue).length;
  return (
    <li>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="flex w-full items-start gap-2.5 bg-subtle px-3 py-2 text-left hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50">
        <ChevronRight className={cn("mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block text-body font-medium text-heading">{CATEGORY_LABEL[first.category] ?? titleCase(first.category)}: {items.length} similar alerts</span>
          <span className="block truncate text-label text-muted-foreground">Most urgent: {first.title}</span>
        </span>
        <StatusChip status={overdue ? "overdue" : "not_started"} label={overdue ? `${overdue} overdue` : `${items.length} open`} />
      </button>
      {open && <ul className="divide-y border-t">{items.map((c) => <CaseLine key={c.id} c={c} onOpen={onOpen} active={openId === c.id} />)}</ul>}
    </li>
  );
}

function useWide(query = "(min-width: 1280px)") {
  const [wide, setWide] = React.useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  React.useEffect(() => {
    const m = window.matchMedia(query);
    const on = () => setWide(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [query]);
  return wide;
}

type Panel = "cases" | "tasks" | "approvals";
const PANELS: { key: Panel; title: string }[] = [{ key: "cases", title: "Cases" }, { key: "tasks", title: "Tasks" }, { key: "approvals", title: "Approvals" }];

/** One compact two-line case row for the side-by-side console. */
function CaseLine({ c, onOpen, active }: { c: CaseT; onOpen: (id: string) => void; active: boolean }) {
  return (
    <li>
      <button type="button" onClick={() => onOpen(c.id)} aria-current={active ? "true" : undefined} data-testid="work-case"
        className={cn("flex w-full items-start gap-2.5 px-3 py-2 text-left hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50", active && "bg-accent/60")}>
        <SeverityIcon c={c} />
        <span className="min-w-0 flex-1">
          <span className="flex items-start justify-between gap-2">
            <span className="line-clamp-2 text-body font-medium text-heading">{c.title}</span>
            <span className="shrink-0 text-label tabular text-muted-foreground">C{c.number}</span>
          </span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-label text-muted-foreground">
            {c.patient_name && <span className="font-medium text-foreground">{c.patient_name}</span>}
            <span>{ownerLabel(c)}</span>
            {c.due_at && <SlaBadge c={c} />}
            {c.stage === "waiting_approval" && <StatusChip status="needs_approval" />}
          </span>
        </span>
      </button>
    </li>
  );
}

export function WorklistPage() {
  const [params, setParams] = useSearchParams();
  const openCase = params.get("case");
  const wide = useWide();
  const q = useQuery({ queryKey: ["worklist"], queryFn: () => get<Worklist>("/worklist"), refetchInterval: 60_000 });
  const counts = q.data?.counts;
  const auto: Panel = !counts ? "cases" : counts.approvals ? "approvals" : counts.cases ? "cases" : counts.tasks ? "tasks" : "cases";
  const requested = params.get("tab") as Panel | null;
  const tab: Panel = requested && ["cases", "tasks", "approvals"].includes(requested) ? requested : auto;
  const focus = params.get("focus") as Panel | null;
  const set = (k: string, v: string | null) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };
  const [search, setSearch] = React.useState("");
  const [cat, setCat] = React.useState("all");
  const [sev, setSev] = React.useState("all");
  const [overdueOnly, setOverdueOnly] = React.useState(false);
  const needle = search.trim().toLowerCase();
  const match = (...xs: (string | null | undefined)[]) => !needle || xs.some((x) => x?.toLowerCase().includes(needle));
  const cats = React.useMemo(() => [...new Set((q.data?.cases ?? []).map((c) => c.category))], [q.data]);
  const cases = (q.data?.cases ?? []).filter((c) => (cat === "all" || c.category === cat) && (sev === "all" || c.severity === sev)
    && (!overdueOnly || c.overdue) && match(c.title, c.patient_name, c.summary, `c${c.number}`));
  const tasks = (q.data?.tasks ?? []).filter((t) => (!overdueOnly || (t.due_at && new Date(t.due_at) < new Date())) && match(t.title, t.patient_name));
  const approvals = (q.data?.approvals ?? []).filter((a) => match(a.title, a.summary));
  const others = (q.data?.other_approvals ?? []).filter((a) => match(a.title));
  const n: Record<Panel, number> = { cases: cases.length, tasks: tasks.length, approvals: approvals.length + others.length };

  const body = (p: Panel) => {
    if (q.isLoading) return <LoadingRows />;
    if (p === "cases") {
      return !cases.length ? <EmptyState compact icon={CheckCircle2} title={needle || cat !== "all" || sev !== "all" || overdueOnly ? "No matching cases" : "No open cases for you"} /> : (
        <ul className="divide-y">{groupCases(cases).map((c) => "group" in c
          ? <CaseGroup key={c.group} items={c.items} onOpen={(id) => set("case", id)} openId={openCase} />
          : <CaseLine key={c.id} c={c} onOpen={(id) => set("case", id)} active={openCase === c.id} />)}</ul>
      );
    }
    if (p === "tasks") return <TaskList tasks={tasks} onOpenCase={(id) => set("case", id)} />;
    return (
      <div className="px-3">
        <ApprovalList items={approvals} empty={others.length ? <></> : <EmptyState compact icon={ShieldCheck} title="Nothing to approve" />} />
        <OtherApprovalList items={others} />
      </div>
    );
  };

  const filters = (
    <div className="mb-3 flex flex-wrap items-center gap-2" role="search" aria-label="Filter my work">
      <div className="relative w-full sm:w-72">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search cases, tasks, approvals, patients…" className="h-8 pl-8" aria-label="Search my work" />
      </div>
      <NativeSelect value={sev} onChange={(e) => setSev(e.target.value)} className="h-8 w-auto" aria-label="Severity">
        <option value="all">All severities</option>
        {["critical", "high", "medium", "low", "info"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
      </NativeSelect>
      {cats.length > 1 && (
        <NativeSelect value={cat} onChange={(e) => setCat(e.target.value)} className="h-8 w-auto" aria-label="Area">
          <option value="all">All areas</option>
          {cats.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c] ?? titleCase(c)}</option>)}
        </NativeSelect>
      )}
      <label className="inline-flex h-8 items-center gap-2 rounded-md border border-control px-2.5 text-table">
        <Checkbox checked={overdueOnly} onCheckedChange={(v) => setOverdueOnly(v === true)} aria-label="Overdue only" />Overdue only
      </label>
      {q.dataUpdatedAt > 0 && <span className="ml-auto text-label text-muted-foreground">Updated {fromNow(new Date(q.dataUpdatedAt).toISOString())}</span>}
    </div>
  );

  return (
    <>
      <PageHeader title="My work" description="Cases, tasks and approvals waiting on you or your roles — clinical severity first, then overdue work." />
      {q.isError ? <ErrorState error={q.error} retry={q.refetch} /> : (
        <>
          {filters}
          {wide ? (
            <div className={cn("grid h-[calc(100dvh-14rem)] min-h-[28rem] gap-3", focus ? "grid-cols-1" : "grid-cols-3")} data-testid="work-console">
              {PANELS.filter((p) => !focus || p.key === focus).map((p) => (
                <WorkPanel key={p.key} id={`panel-${p.key}`} title={p.title} count={n[p.key]} maximized={focus === p.key}
                  onToggleMax={() => set("focus", focus === p.key ? null : p.key)}>{body(p.key)}</WorkPanel>
              ))}
            </div>
          ) : (
            <Tabs value={tab} onValueChange={(t) => set("tab", t)}>
              <TabsList>{PANELS.map((p) => <TabsTrigger key={p.key} value={p.key}>{p.title} {q.data && <TabCount n={n[p.key]} />}</TabsTrigger>)}</TabsList>
              {PANELS.map((p) => <TabsContent key={p.key} value={p.key}><Card className="overflow-hidden">{body(p.key)}</Card></TabsContent>)}
            </Tabs>
          )}
        </>
      )}
      <CaseDrawer caseId={openCase} onClose={() => set("case", null)} />
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

