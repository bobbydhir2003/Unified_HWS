import { useQuery } from "@tanstack/react-query";
import { Maximize2, Minimize2, Radio, Search } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { get } from "@/lib/api";
import { fmtTime, fromNow } from "@/lib/format";
import { useLiveStatus } from "@/lib/live";
import { cn, titleCase } from "@/lib/utils";
import { useFacilities } from "../admin/FacilitiesPage";
import { CaseDrawer, CaseRow, type CaseT, CATEGORY_LABEL, type Severity } from "../ops/ops";

type Tile = { key: string; label: string; value: number | string; link: string | null; tone: string; sub: string | null; source: string | null };
type Summary = {
  generated_at: string; date: string; tiles: Tile[]; cases_by_category: { category: string; severity: Severity; count: number }[];
  top_cases: CaseT[]; worklists: { queue: string; open: number; overdue: number }[]; appointments_by_status: Record<string, number>;
  engine: { status: string; pending_events: number; processed_24h: number; monitor_failures_24h: number; notification_failures_24h: number };
};
const SEVS: Severity[] = ["critical", "high", "medium", "low", "info"];
const TONE: Record<string, string> = {
  danger: "border-destructive/40 bg-destructive-soft/40", warning: "border-warning/40 bg-warning-soft/40", success: "border-success/30", neutral: "",
};

export function CommandCenter() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const live = useLiveStatus();
  const facs = useFacilities();
  const [wall, setWall] = React.useState(false);
  const [q, setQ] = React.useState("");
  const [openCase, setOpenCase] = React.useState<string | null>(null);
  const facility = params.get("facility") ?? "";
  const severity = params.get("severity") ?? "";
  const category = params.get("category") ?? "";
  const overdue = params.get("overdue") === "1";
  const set = (k: string, v: string | null) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };
  const s = useQuery({ queryKey: ["command", facility], queryFn: () => get<Summary>("/command/summary", { facility_id: facility || undefined }), refetchInterval: 60_000 });
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

  return (
    <div className={cn(wall && "fixed inset-0 z-50 overflow-auto bg-background p-6 text-[15px]")}>
      <PageHeader title="Command Center" description={`Live operations for ${s.data ? new Date(s.data.date + "T12:00:00").toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }) : "today"}. Every number links to its records.`}
        actions={<div className="flex items-center gap-2">
          <Badge variant={live ? "success" : "neutral"} title={live ? "Receiving live updates" : "Reconnecting — refreshing every minute"}><Radio className={cn(live && "animate-pulse")} />{live ? "Live" : "Polling"}</Badge>
          <NativeSelect className="w-52" aria-label="Facility" value={facility} onChange={(e) => set("facility", e.target.value || null)}>
            <option value="">All my facilities</option>{facs.data?.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </NativeSelect>
          <Button variant="outline" size="sm" onClick={() => { if (wall) document.exitFullscreen?.().catch(() => {}); setWall(!wall); }}>{wall ? <Minimize2 /> : <Maximize2 />}{wall ? "Exit wall display" : "Wall display"}</Button>
        </div>} />
      {s.isError ? <ErrorState error={s.error} retry={s.refetch} /> : !s.data ? <LoadingRows rows={6} /> : (
        <>
          <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">{s.data.tiles.map((t) => (
            <button key={t.key} onClick={() => t.link && navigate(t.link)} title={t.source ? `Source: ${t.source}` : undefined}
              className={cn("rounded-xl border bg-card p-4 text-left shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition hover:shadow-md focus-visible:outline-2 focus-visible:outline-primary", TONE[t.tone])}>
              <p className="text-[13px] font-medium text-muted-foreground">{t.label}</p>
              <p className={cn("mt-1 font-semibold tracking-tight tabular", wall ? "text-4xl" : "text-2xl")}>{typeof t.value === "string" ? titleCase(t.value) : t.value}</p>
              {t.sub && <p className="mt-0.5 text-xs text-muted-foreground">{t.sub}</p>}
            </button>))}</div>
          <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
            <Card className="overflow-hidden">
              <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
                <CardTitle>Problem queue</CardTitle>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative"><Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" /><Input className="h-9 w-48 pl-8" placeholder="Search cases…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search cases" /></div>
                  <NativeSelect className="h-9 w-36" aria-label="Severity" value={severity} onChange={(e) => set("severity", e.target.value || null)}><option value="">Any severity</option>{SEVS.map((x) => <option key={x} value={x}>{titleCase(x)}</option>)}</NativeSelect>
                  <NativeSelect className="h-9 w-40" aria-label="Category" value={category} onChange={(e) => set("category", e.target.value || null)}><option value="">All departments</option>{Object.keys(matrix).map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c] ?? c}</option>)}</NativeSelect>
                  <Button size="sm" variant={overdue ? "default" : "outline"} onClick={() => set("overdue", overdue ? null : "1")}>Past SLA</Button>
                </div>
              </CardHeader>
              {filtered && cases.isLoading ? <LoadingRows /> : !list.length ? <EmptyState title="No open cases match" description="Nothing needs attention for this filter." /> : (
                <ul className="divide-y border-t">{list.map((c) => <CaseRow key={c.id} c={c} onOpen={setOpenCase} />)}</ul>
              )}
              {!filtered && s.data.top_cases.length >= 12 && <div className="border-t p-3 text-center"><Link className="text-[13px] font-medium text-primary hover:underline" to="/command?severity=medium">Show more</Link></div>}
            </Card>
            <div className="space-y-4">
              <Card>
                <CardHeader><CardTitle>Open cases by department</CardTitle></CardHeader>
                <CardContent>{!Object.keys(matrix).length ? <p className="text-[13px] text-muted-foreground">No open cases.</p> : (
                  <table className="w-full text-[13px]"><thead><tr className="text-xs text-muted-foreground"><th className="py-1 text-left font-medium">Area</th>{SEVS.slice(0, 4).map((x) => <th key={x} className="font-medium">{titleCase(x)}</th>)}</tr></thead>
                    <tbody>{Object.entries(matrix).map(([cat, row]) => (
                      <tr key={cat} className="border-t"><td className="py-1.5">{CATEGORY_LABEL[cat] ?? cat}</td>{SEVS.slice(0, 4).map((x) => (
                        <td key={x} className="text-center">{row[x] ? <button className={cn("min-w-8 rounded px-1.5 py-0.5 tabular font-medium hover:ring-2 hover:ring-primary/40", x === "critical" || x === "high" ? "bg-destructive-soft text-destructive" : x === "medium" ? "bg-warning-soft" : "bg-muted")} onClick={() => { set("category", cat); set("severity", x); }}>{row[x]}</button> : <span className="text-muted-foreground/40">·</span>}</td>))}</tr>))}</tbody></table>
                )}</CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle>Department worklists</CardTitle></CardHeader>
                <CardContent>{!s.data.worklists.length ? <p className="text-[13px] text-muted-foreground">All queues clear.</p> : (
                  <ul className="space-y-1.5 text-[13px]">{s.data.worklists.slice(0, 10).map((w) => (
                    <li key={w.queue} className="flex items-center justify-between"><span>{titleCase(w.queue.replace(/_/g, " "))}</span>
                      <span className="tabular">{w.open} open{w.overdue ? <span className="ml-1 font-medium text-destructive">· {w.overdue} overdue</span> : null}</span></li>))}</ul>
                )}</CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle>Automation</CardTitle></CardHeader>
                <CardContent className="space-y-1 text-[13px]">
                  <p><Badge variant={s.data.engine.status === "healthy" ? "success" : "warning"}>{titleCase(s.data.engine.status)}</Badge> <span className="text-muted-foreground">· {s.data.engine.processed_24h} events in 24 h · {s.data.engine.pending_events} queued</span></p>
                  <p className="text-muted-foreground">{s.data.engine.monitor_failures_24h} monitor failures · {s.data.engine.notification_failures_24h} notification failures (24 h)</p>
                  <Link to="/automation/monitors" className="text-primary hover:underline">Monitors & rules</Link>
                </CardContent>
              </Card>
              <p className="text-center text-xs text-muted-foreground">Updated {fmtTime(s.data.generated_at)} ({fromNow(s.data.generated_at)})</p>
            </div>
          </div>
        </>
      )}
      <CaseDrawer caseId={openCase} onClose={() => setOpenCase(null)} />
    </div>
  );
}
