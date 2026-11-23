import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ChevronRight, Maximize2, Minimize2, Radio, Search } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, LoadingRows, MetricStrip, PageHeader, toastError } from "@/components/common";
import { StatusChip } from "@/components/common/Status";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, NativeSelect } from "@/components/ui/input";
import { get } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import { useLiveStatus } from "@/lib/live";
import { cn, titleCase } from "@/lib/utils";
import { useFacilities } from "../admin/FacilitiesPage";
import { CASE_COLS, CaseDrawer, CaseListHeader, CaseRow, type CaseT, CATEGORY_LABEL, isClinicalDanger, ownerLabel, SeverityIcon, type Severity, SlaBadge } from "../ops/ops";
import { AskAI } from "@/features/ai/AskAI";

type Tile = { key: string; label: string; value: number | string; link: string | null; tone: string; sub: string | null; source: string | null };
type Hosp = { available: boolean; tiles?: Tile[]; occupancy_by_department?: { department: string; kind: string; available: number; occupied: number; cleaning: number; blocked: number; occupancy_pct: number | null }[] };
type Handoff = { narrative: string; narrative_source: string; sections: Record<string, { ref: string; case_id: string; title: string; severity: string; overdue: boolean; escalated: boolean }[]>; open_cases: number; generated_at: string };
type Summary = {
  hospital?: Hosp;
  generated_at: string; date: string; tiles: Tile[]; cases_by_category: { category: string; severity: Severity; count: number }[];
  top_cases: CaseT[]; worklists: { queue: string; open: number; overdue: number }[]; appointments_by_status: Record<string, number>;
  engine: { status: string; pending_events: number; processed_24h: number; monitor_failures_24h: number; notification_failures_24h: number };
};
const SEVS: Severity[] = ["critical", "high", "medium", "low", "info"];

export function CommandCenter() {
  const [params, setParams] = useSearchParams();
  const live = useLiveStatus();
  const facs = useFacilities();
  const [wall, setWall] = React.useState(false);
  const [q, setQ] = React.useState("");
  const [openCase, setOpenCase] = React.useState<string | null>(null);
  const facility = params.get("facility") ?? "";
  const department = params.get("department") ?? "";
  const [handoff, setHandoff] = React.useState<Handoff | null>(null);
  const depts = useQuery({ queryKey: ["departments", "cc"], queryFn: () => get<{ id: string; name: string }[]>("/departments") });
  const severity = params.get("severity") ?? "";
  const category = params.get("category") ?? "";
  const overdue = params.get("overdue") === "1";
  const set = (k: string, v: string | null) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };
  const s = useQuery({ queryKey: ["command", facility, department], queryFn: () => get<Summary>("/command/summary", { facility_id: facility || undefined, department_id: department || undefined }), refetchInterval: 60_000 });
  const filtered = severity || category || overdue || q;
  const cases = useQuery({
    queryKey: ["cases", "command", facility, severity, category, overdue, q],
    queryFn: () => get<CaseT[]>("/cases", { facility_id: facility || undefined, severity: severity === "high" ? undefined : severity || undefined, category: category || undefined, overdue: overdue || undefined, q: q || undefined, limit: 100 }),
    enabled: !!filtered,
  });
  const list = filtered ? (cases.data ?? []).filter((c) => severity !== "high" || ["high", "critical"].includes(c.severity)) : s.data?.top_cases ?? [];
  const matrix = React.useMemo(() => {
    const m: Record<string, Partial<Record<Severity, number>>> = {};
    (s.data?.cases_by_category ?? []).forEach((r) => { (m[r.category] ??= {})[r.severity] = r.count; });
    return m;
  }, [s.data]);

  React.useEffect(() => {
    if (!wall) return;
    document.documentElement.requestFullscreen?.().catch(() => {});
    const exit = () => { if (!document.fullscreenElement) setWall(false); };
    document.addEventListener("fullscreenchange", exit);
    return () => document.removeEventListener("fullscreenchange", exit);
  }, [wall]);

  const groups = React.useMemo(() => groupByCategory(s.data?.top_cases ?? []), [s.data]);
  const statusTiles = s.data?.hospital?.available ? s.data.hospital.tiles ?? [] : (s.data?.tiles ?? []).slice(0, 6);
  const dateLabel = s.data ? new Date(s.data.date + "T12:00:00").toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }) : "today";

  return (
    <div className={cn(wall && "fixed inset-0 z-50 overflow-auto bg-background p-6")}>
      <PageHeader title="Command Center"
        eyebrow={<>Hospital operations · {dateLabel}{s.data ? ` · updated ${fmtTime(s.data.generated_at)}` : ""}</>}
        description="Status, then problems needing attention, then department detail. Every number opens its records."
        actions={<>
          <AskAI agent="hospital_operations" label="Explain bottlenecks" question="Explain today's operational bottlenecks and which teams they are waiting on, citing case references." />
          <Button variant="outline" size="sm" onClick={async () => { try { setHandoff(await get<Handoff>("/command/handoff", { facility_id: facility || undefined })); } catch (e) { toastError(e); } }}>Shift handoff</Button>
          <Button variant="outline" size="sm" onClick={() => { if (wall) document.exitFullscreen?.().catch(() => {}); setWall(!wall); }}>{wall ? <Minimize2 /> : <Maximize2 />}{wall ? "Exit wall display" : "Wall display"}</Button>
        </>}
        toolbar={<>
          <Badge variant={live ? "success" : "neutral"} title={live ? "Receiving live updates" : "Reconnecting — refreshing every minute"}><Radio className={cn(live && "animate-pulse")} />{live ? "Live" : "Polling"}</Badge>
          <NativeSelect className="h-8 w-52" aria-label="Facility" value={facility} onChange={(e) => set("facility", e.target.value || null)}>
            <option value="">All my facilities</option>{facs.data?.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </NativeSelect>
          <NativeSelect className="h-8 w-44" aria-label="Department" value={department} onChange={(e) => set("department", e.target.value || null)}>
            <option value="">All departments</option>{depts.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </NativeSelect>
        </>} />
      {s.isError ? <ErrorState error={s.error} retry={s.refetch} /> : !s.data ? <LoadingRows rows={6} /> : (
        <div className="space-y-6">
          {/* Level 1 — hospital status */}
          <section aria-labelledby="cc-status" className="space-y-2">
            <h2 id="cc-status" className="text-label font-semibold text-muted-foreground">1 · Hospital status</h2>
            <MetricStrip cols={Math.min(6, Math.max(2, statusTiles.length)) as 2 | 3 | 4 | 5 | 6}>
              {statusTiles.map((t) => <TileButton key={t.key} t={t} wall={wall} />)}
            </MetricStrip>
          </section>

          {/* Level 2 — problems requiring attention */}
          <section aria-labelledby="cc-attention" className="space-y-2">
            <h2 id="cc-attention" className="text-label font-semibold text-muted-foreground">2 · Needs attention — grouped by area, clinical risk first</h2>
            <Card className="overflow-hidden">
              <div className="flex flex-wrap items-center gap-2 border-b p-3">
                <div className="relative"><Search className="absolute left-2.5 top-2 size-4 text-muted-foreground" /><Input className="h-8 w-52 pl-8" placeholder="Search cases…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search cases" /></div>
                <NativeSelect className="h-8 w-36" aria-label="Severity" value={severity} onChange={(e) => set("severity", e.target.value || null)}><option value="">Any severity</option>{SEVS.map((x) => <option key={x} value={x}>{titleCase(x)}</option>)}</NativeSelect>
                <NativeSelect className="h-8 w-40" aria-label="Category" value={category} onChange={(e) => set("category", e.target.value || null)}><option value="">All areas</option>{Object.keys(matrix).map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c] ?? c}</option>)}</NativeSelect>
                <Button size="sm" variant={overdue ? "soft" : "outline"} aria-pressed={overdue} onClick={() => set("overdue", overdue ? null : "1")}>Past target</Button>
                {filtered && <Button size="sm" variant="ghost" onClick={() => { setQ(""); const n = new URLSearchParams(params); ["severity", "category", "overdue"].forEach((k) => n.delete(k)); setParams(n, { replace: true }); }}>Clear filters</Button>}
              </div>
              {filtered ? (cases.isLoading ? <LoadingRows /> : !list.length ? <EmptyState title="No open cases match" description="Nothing needs attention for this filter." /> : (
                <ul className="divide-y"><CaseListHeader />{list.map((c) => <CaseRow key={c.id} c={c} onOpen={setOpenCase} />)}</ul>
              )) : !groups.length ? <EmptyState icon={CheckCircle2} title="Nothing needs attention" description="No open cases right now." /> : (
                <ul className="divide-y"><CaseListHeader />{groups.map((g) => <AttentionGroup key={g.category} g={g} onOpen={setOpenCase} />)}</ul>
              )}
              {!filtered && s.data.top_cases.length >= 12 && <div className="border-t p-3 text-center"><Link className="text-table font-medium text-primary hover:underline" to="/command?severity=medium">Show more</Link></div>}
            </Card>
          </section>

          {/* Level 3 — department detail */}
          <section aria-labelledby="cc-detail" className="space-y-2">
            <h2 id="cc-detail" className="text-label font-semibold text-muted-foreground">3 · Department detail</h2>
            <Card className="px-4 pb-4 pt-2">
              <Tabs defaultValue="activity">
                <TabsList>
                  <TabsTrigger value="activity">Activity</TabsTrigger>
                  {!!s.data.hospital?.occupancy_by_department?.length && <TabsTrigger value="capacity">Capacity</TabsTrigger>}
                  <TabsTrigger value="worklists">Department worklists</TabsTrigger>
                  <TabsTrigger value="automation">Automation</TabsTrigger>
                </TabsList>
                <TabsContent value="activity">
                  <MetricStrip cols={4}>{s.data.tiles.map((t) => <TileButton key={t.key} t={t} wall={wall} />)}</MetricStrip>
                </TabsContent>
                {!!s.data.hospital?.occupancy_by_department?.length && (
                  <TabsContent value="capacity"><OccupancyTable rows={s.data.hospital.occupancy_by_department} /></TabsContent>
                )}
                <TabsContent value="worklists">{!s.data.worklists.length ? <p className="text-body text-muted-foreground">All queues clear.</p> : (
                  <Table><THead><TR><TH>Queue</TH><TH className="num">Open</TH><TH className="num">Overdue</TH></TR></THead>
                    <TBody>{s.data.worklists.slice(0, 12).map((w) => (
                      <TR key={w.queue}><TD className="font-medium text-heading">{titleCase(w.queue.replace(/_/g, " "))}</TD><TD className="num">{w.open}</TD>
                        <TD className={cn("num", w.overdue > 0 && "font-medium text-warning-foreground")}>{w.overdue}</TD></TR>))}</TBody></Table>
                )}</TabsContent>
                <TabsContent value="automation">
                  <div className="space-y-1 text-body">
                    <p className="flex flex-wrap items-center gap-2"><Badge variant={s.data.engine.status === "healthy" ? "success" : "warning"}>{s.data.engine.status === "healthy" ? <CheckCircle2 /> : <AlertTriangle />}{titleCase(s.data.engine.status)}</Badge>
                      <span className="text-muted-foreground">{s.data.engine.processed_24h} events in 24 h · {s.data.engine.pending_events} queued</span></p>
                    <p className="text-muted-foreground">{s.data.engine.monitor_failures_24h} monitor failures · {s.data.engine.notification_failures_24h} notification failures (24 h)</p>
                    <Link to="/automation/monitors" className="text-primary hover:underline">Monitors & rules</Link>
                  </div>
                </TabsContent>
              </Tabs>
            </Card>
          </section>
        </div>
      )}
      <CaseDrawer caseId={openCase} onClose={() => setOpenCase(null)} />
      <Dialog open={!!handoff} onOpenChange={(o) => !o && setHandoff(null)}>
        <DialogContent size="lg"><DialogHeader><DialogTitle>Shift handoff</DialogTitle><DialogDescription>{handoff?.narrative_source === "ai_cited" ? "Narrative drafted by the Hospital Operations agent; every sentence cites a case." : "Built directly from open cases."}</DialogDescription></DialogHeader>
          <p className="whitespace-pre-wrap rounded-lg border bg-muted/30 p-3 text-table">{handoff?.narrative}</p>
          <div className="max-h-72 space-y-3 overflow-auto">{Object.entries(handoff?.sections ?? {}).map(([cat, items]) => (
            <div key={cat}><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{CATEGORY_LABEL[cat] ?? cat}</p>
              <ul className="space-y-1">{items.map((i) => <li key={i.ref}><button className="text-left text-table hover:underline" onClick={() => { setHandoff(null); setOpenCase(i.case_id); }}><span className="font-mono text-xs text-muted-foreground">[{i.ref}]</span> {i.title}{i.overdue ? " · overdue" : ""}{i.escalated ? " · escalated" : ""}</button></li>)}</ul></div>))}</div>
          <DialogFooter><Button variant="outline" onClick={() => setHandoff(null)}>Close</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** A metric that opens its records (keyboard-operable button). Tone only when the server marks it. */
function TileButton({ t, wall }: { t: Tile; wall: boolean }) {
  const navigate = useNavigate();
  const tone = t.tone === "danger" ? "text-destructive" : t.tone === "warning" ? "text-warning-foreground" : "text-heading";
  return (
    <button type="button" onClick={() => t.link && navigate(t.link)} title={t.source ? `Source: ${t.source}` : undefined} disabled={!t.link}
      className="min-w-0 bg-card px-4 py-3 text-left hover:bg-muted/60 focus-visible:relative focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60 disabled:cursor-default disabled:hover:bg-card">
      <span className="block truncate text-label font-medium text-muted-foreground">{t.label}</span>
      <span className={cn("block font-semibold tabular", tone, wall ? "text-4xl" : "text-metric")}>
        {(t.tone === "danger" || t.tone === "warning") && <AlertTriangle className="mr-1 inline size-4 align-[-2px]" aria-label="Needs attention" />}
        {typeof t.value === "string" ? titleCase(t.value) : t.value}
      </span>
      {t.sub && <span className="block truncate text-label text-muted-foreground">{t.sub}</span>}
    </button>
  );
}

const SEV_RANK: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
type CatGroup = { category: string; items: CaseT[]; worst: CaseT };
function groupByCategory(cases: CaseT[]): CatGroup[] {
  const m = new Map<string, CaseT[]>();
  for (const c of cases) m.set(c.category, [...(m.get(c.category) ?? []), c]);
  return [...m.entries()].map(([category, items]) => {
    const sorted = [...items].sort((a, b) => (Number(isClinicalDanger(b)) - Number(isClinicalDanger(a))) || (SEV_RANK[a.severity] - SEV_RANK[b.severity]) || (Number(b.overdue) - Number(a.overdue)));
    return { category, items: sorted, worst: sorted[0] };
  }).sort((a, b) => (Number(isClinicalDanger(b.worst)) - Number(isClinicalDanger(a.worst))) || (SEV_RANK[a.worst.severity] - SEV_RANK[b.worst.severity]) || b.items.length - a.items.length);
}

function AttentionGroup({ g, onOpen }: { g: CatGroup; onOpen: (id: string) => void }) {
  const [open, setOpen] = React.useState(false);
  const overdue = g.items.filter((c) => c.overdue).length;
  const owners = [...new Set(g.items.map((c) => ownerLabel(c)))];
  const oldest = g.items.map((c) => c.due_at).filter(Boolean).sort()[0];
  if (g.items.length === 1) return <CaseRow c={g.worst} onOpen={onOpen} />;
  return (
    <li>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className={cn(CASE_COLS, "w-full px-4 py-(--row-y) text-left text-table hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50")}>
        <SeverityIcon c={g.worst} />
        <span className="min-w-0">
          <span className="flex items-center gap-1.5 text-body font-medium text-heading"><ChevronRight className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")} aria-hidden />
            {CATEGORY_LABEL[g.category] ?? titleCase(g.category)} · {g.items.length} open</span>
          <span className="block truncate text-label text-muted-foreground">Most urgent: {g.worst.title}</span>
        </span>
        <span className="hidden truncate text-muted-foreground md:block">{new Set(g.items.map((c) => c.patient_name).filter(Boolean)).size || "—"}{new Set(g.items.map((c) => c.patient_name).filter(Boolean)).size ? " patients" : ""}</span>
        <span className="hidden truncate md:block">{owners.slice(0, 2).join(", ")}{owners.length > 2 ? ` +${owners.length - 2}` : ""}</span>
        <span className="hidden md:block">{oldest ? <SlaBadge c={{ ...g.items.find((c) => c.due_at === oldest)! }} /> : "—"}</span>
        <span><StatusChip status={overdue ? "overdue" : "not_started"} label={overdue ? `${overdue} overdue` : `${g.items.length} open`} /></span>
      </button>
      {open && <ul className="divide-y border-t bg-subtle/60">{g.items.map((c) => <CaseRow key={c.id} c={c} onOpen={onOpen} compact />)}</ul>}
    </li>
  );
}

function OccupancyTable({ rows }: { rows: NonNullable<Hosp["occupancy_by_department"]> }) {
  return (
    <Table><THead><TR><TH>Unit</TH><TH className="num">Occupied</TH><TH className="num">Available</TH><TH className="num">Cleaning</TH><TH className="num">Blocked</TH><TH className="w-64">Occupancy</TH></TR></THead>
      <TBody>{rows.map((d) => (
        <TR key={d.department}><TD className="font-medium text-heading">{d.department}</TD><TD className="num">{d.occupied}</TD><TD className="num">{d.available}</TD><TD className="num">{d.cleaning}</TD><TD className="num">{d.blocked}</TD>
          <TD><span className="flex items-center gap-2"><span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted"><span className={cn("block h-full", (d.occupancy_pct ?? 0) >= 90 ? "bg-destructive" : (d.occupancy_pct ?? 0) >= 80 ? "bg-warning" : "bg-primary")} style={{ width: `${d.occupancy_pct ?? 0}%` }} /></span>
            <span className="w-10 text-right tabular">{d.occupancy_pct ?? "—"}%</span></span></TD></TR>))}</TBody></Table>
  );
}
