import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarPlus, ClipboardPen, FileText, FlaskConical, Hospital, Radar, Receipt, ScanLine, ShieldCheck, Siren, Stethoscope } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import { titleCase } from "@/lib/utils";

type Pt = { date: string; value: number; lower?: number; upper?: number };
type Series = { history?: Pt[]; forecast: Pt[]; method: string };
type Forecasts = {
  label: string; shadow_mode: boolean; evaluation_note: string;
  evaluation: Record<string, { n: number; mae: number; band_coverage: number }> | null;
  series: Record<string, Series> & { no_shows: { rate_90d: number; tomorrow_appointments: number; expected_no_shows_tomorrow: number; method: string } };
};
type Metric = { ref: string; metric: string; value: number | string; detail?: string; source: string; link?: string };
type Briefing = {
  generated_at: string; narrative: string; narrative_source: "deterministic" | "ai_cited"; metrics: Metric[];
  cases: { ref: string; title: string; severity: string; category: string }[];
  discharge_bottlenecks: { item: string; owner: string; open_plans: number }[];
};

const TARGETS: [string, string][] = [["census", "Inpatient census"], ["admissions", "Admissions"], ["discharges", "Discharges"], ["ed_arrivals", "ED arrivals"]];

function ForecastChart({ s }: { s: Series }) {
  const data = [
    ...(s.history ?? []).slice(-14).map((p) => ({ date: p.date.slice(5), actual: p.value })),
    ...s.forecast.map((p) => ({ date: p.date.slice(5), forecast: p.value, band: [p.lower ?? p.value, p.upper ?? p.value] as [number, number] })),
  ];
  return (
    <ResponsiveContainer width="100%" height={180}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
        <RTooltip contentStyle={{ fontSize: 12 }} />
        <Area isAnimationActive={false} dataKey="band" stroke="none" fill="var(--primary)" fillOpacity={0.12} name="Range" />
        <Line isAnimationActive={false} dataKey="actual" stroke="var(--muted-foreground)" dot={false} strokeWidth={1.5} name="Actual" />
        <Line isAnimationActive={false} dataKey="forecast" stroke="var(--primary)" strokeDasharray="4 3" dot={false} strokeWidth={2} name="Baseline" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function InsightsPage() {
  const { can } = useAuth();
  const showBriefing = can("cases:read") && (can("command:view") || can("automation:manage"));
  const f = useQuery({ queryKey: ["insights", "forecasts"], queryFn: () => get<Forecasts>("/forecasts", { days: 7 }), enabled: can("analytics:read") });
  const b = useQuery({ queryKey: ["insights", "briefing"], queryFn: () => get<Briefing>("/reports/briefing"), enabled: showBriefing });
  return (
    <div className="space-y-6">
      <PageHeader title="Insights" description="Daily briefing from live data with sources, plus baseline forecasts for planning." />
      {showBriefing && (
        <Card>
          <CardHeader className="flex-row items-center justify-between gap-2">
            <CardTitle>Daily briefing</CardTitle>
            <div className="flex items-center gap-2">
              <Badge variant={b.data?.narrative_source === "ai_cited" ? "ai" : "neutral"}>{b.data?.narrative_source === "ai_cited" ? "AI narrative · every sentence cited" : "Generated from data (no AI)"}</Badge>
              <Button size="xs" variant="outline" onClick={() => b.refetch()} loading={b.isFetching}>Refresh</Button>
            </div>
          </CardHeader>
          <CardContent>
            {b.error ? <ErrorState error={b.error} /> : b.isLoading || !b.data ? <LoadingRows /> : (
              <div className="grid gap-5 lg:grid-cols-[1.2fr_1fr]">
                <div>
                  <p className="whitespace-pre-line text-[13.5px] leading-relaxed" data-testid="briefing-narrative">{b.data.narrative}</p>
                  <p className="mt-2 text-xs text-muted-foreground">Generated {fmtDateTime(b.data.generated_at)}. References in brackets point to the numbered metrics and cases.</p>
                  {!!b.data.discharge_bottlenecks.length && (
                    <div className="mt-4">
                      <h3 className="mb-1.5 text-[13px] font-medium">Discharge bottlenecks</h3>
                      <ul className="space-y-1 text-[13px]">
                        {b.data.discharge_bottlenecks.slice(0, 5).map((d) => (
                          <li key={d.item} className="flex justify-between gap-2"><span>{d.item} <span className="text-muted-foreground">· {titleCase(d.owner ?? "")}</span></span><span className="tabular">{d.open_plans}</span></li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
                <Table>
                  <THead><TR><TH>Ref</TH><TH>Metric</TH><TH className="text-right">Value</TH><TH>Source</TH></TR></THead>
                  <TBody>
                    {b.data.metrics.map((m) => (
                      <TR key={m.ref}>
                        <TD className="font-mono text-xs">{m.ref}</TD>
                        <TD>{m.link ? <Link to={m.link} className="hover:underline">{m.metric}</Link> : m.metric}</TD>
                        <TD className="text-right tabular">{m.value}</TD>
                        <TD className="text-xs text-muted-foreground">{m.source}</TD>
                      </TR>
                    ))}
                    {b.data.cases.map((c) => (
                      <TR key={c.ref}><TD className="font-mono text-xs">{c.ref}</TD><TD colSpan={2}>{c.title}</TD><TD><Badge variant={c.severity === "critical" ? "danger" : "warning"}>{c.severity}</Badge></TD></TR>
                    ))}
                  </TBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
      {can("analytics:read") && (
        <section className="space-y-3">
          <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 p-3 text-[13px]" data-testid="forecast-label">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <div><strong className="font-medium">Shadow mode.</strong> {f.data?.label ?? "Baseline model — not validated."} {f.data?.evaluation_note}</div>
          </div>
          {f.error ? <ErrorState error={f.error} /> : f.isLoading || !f.data ? <LoadingRows /> : (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                {TARGETS.map(([k, label]) => (
                  <Card key={k}>
                    <CardHeader className="pb-0"><CardTitle className="text-sm">{label} <span className="font-normal text-muted-foreground">· next 7 days</span></CardTitle></CardHeader>
                    <CardContent><ForecastChart s={f.data.series[k]} /><p className="text-xs text-muted-foreground">Method: {f.data.series[k].method} (same-weekday mean, ±1.5 SD range)</p></CardContent>
                  </Card>
                ))}
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <Card>
                  <CardHeader><CardTitle className="text-sm">Nurses needed (med-surg ratio)</CardTitle></CardHeader>
                  <CardContent className="flex flex-wrap gap-2">
                    {f.data.series.nurses_needed.forecast.map((p) => (
                      <div key={p.date} className="rounded-md border px-2.5 py-1.5 text-center"><div className="text-xs text-muted-foreground">{p.date.slice(5)}</div><div className="tabular font-medium">{p.value}</div></div>
                    ))}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader><CardTitle className="text-sm">No-shows</CardTitle></CardHeader>
                  <CardContent className="text-[13.5px]">
                    <p>90-day no-show rate <strong className="tabular">{(f.data.series.no_shows.rate_90d * 100).toFixed(1)}%</strong></p>
                    <p>Tomorrow: {f.data.series.no_shows.tomorrow_appointments} booked → about <strong className="tabular">{f.data.series.no_shows.expected_no_shows_tomorrow}</strong> no-shows expected</p>
                    {f.data.evaluation && (
                      <p className="mt-2 text-xs text-muted-foreground">Backtest: {Object.entries(f.data.evaluation).map(([t, e]) => `${titleCase(t)} MAE ${e.mae} (n=${e.n}, ${Math.round(e.band_coverage * 100)}% in range)`).join(" · ")}</p>
                    )}
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}

type JourneyEvent = { at: string; kind: string; title: string; detail: string | null; link: string | null; department: string | null };
const J_ICON: Record<string, typeof Stethoscope> = {
  appointment: CalendarPlus, encounter: Stethoscope, order: ClipboardPen, result: FlaskConical, imaging: ScanLine, ed: Siren, adt: Hospital,
  insurance: ShieldCheck, billing: Receipt, case: Radar,
};

export function JourneyTab({ patientId }: { patientId: string }) {
  const [filter, setFilter] = React.useState("all");
  const q = useQuery({ queryKey: ["journey", patientId], queryFn: () => get<{ events: JourneyEvent[] }>(`/patients/${patientId}/journey`) });
  const all = q.data?.events ?? [];
  const kinds = ["all", ...Array.from(new Set(all.map((e) => e.kind)))];
  const items = all.filter((e) => filter === "all" || e.kind === filter);
  return (
    <div>
      <p className="mb-3 text-[13px] text-muted-foreground">Everything that happened to this patient across departments. You only see sources your role can access.</p>
      <div className="mb-4 flex flex-wrap gap-1.5">
        {kinds.map((k) => <Button key={k} size="xs" variant={filter === k ? "default" : "outline"} onClick={() => setFilter(k)}>{k === "all" ? "All" : titleCase(k)}</Button>)}
      </div>
      {q.error ? <ErrorState error={q.error} /> : q.isLoading ? <LoadingRows /> : !items.length ? <EmptyState title="No events yet" /> : (
        <ol className="relative ml-3 border-l pl-6" data-testid="journey">
          {items.map((e, i) => {
            const Icon = J_ICON[e.kind] ?? FileText;
            const body = (
              <>
                <p className="text-[13.5px] font-medium">{e.title}{e.department && <span className="ml-2 text-xs font-normal text-muted-foreground">{e.department}</span>}</p>
                {e.detail && <p className="text-[13px] text-muted-foreground">{e.detail}</p>}
                <p className="mt-0.5 text-xs text-muted-foreground">{fmtDateTime(e.at)}</p>
              </>
            );
            return (
              <li key={`${e.kind}-${e.at}-${i}`} className="relative pb-5">
                <span className="absolute -left-[37px] top-0 grid size-6 place-items-center rounded-full border bg-card text-muted-foreground"><Icon className="size-3.5" /></span>
                {e.link ? <Link to={e.link} className="block rounded-md hover:bg-muted/40">{body}</Link> : body}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
