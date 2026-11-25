import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, CalendarCheck2, Clock, Download, HeartPulse, Send, Timer, TrendingDown, UserX, Users } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { EmptyState, LoadingRows, PageHeader, SimulatedBadge, Stat, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDob, fmtMoney } from "@/lib/format";
import { cn, titleCase } from "@/lib/utils";

const AX = { tickLine: false, axisLine: false, tick: { fontSize: 12, fill: "var(--muted-foreground)" } } as const;
const TIP = { contentStyle: { background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 } };
const COLORS = ["var(--primary)", "var(--ai)", "var(--success)", "var(--warning)", "var(--destructive)", "#64748b"];
const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 1000) / 10}%`);

async function downloadCsv(path: string, params: Record<string, string | number | undefined>) {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]));
  const res = await api<Response>(`${path}?${qs}`, { raw: true });
  if (!res.ok) throw new Error("Export failed");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = (res.headers.get("content-disposition")?.match(/filename="(.+)"/)?.[1]) ?? "export.csv";
  a.click();
  URL.revokeObjectURL(url);
}

function ExportButton({ path, params }: { path: string; params: Record<string, string | number | undefined> }) {
  const [busy, setBusy] = React.useState(false);
  return <Button size="sm" variant="outline" loading={busy} onClick={async () => { setBusy(true); try { await downloadCsv(path, params); } catch (e) { toastError(e); } finally { setBusy(false); } }}><Download />CSV</Button>;
}

export function AnalyticsPage() {
  const { can, clinic } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "operations";
  const days = Number(params.get("days") ?? 30);
  const tabs: [string, string, boolean][] = [["operations", "Operations", true], ["providers", "Providers", true], ["population", "Population health", true],
    ["gaps", "Care gaps", true], ["quality", "Quality", true], ["financial", "Financial", can("billing:read")]];
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); n.set(k, v); setParams(n); };
  return (
    <>
      <PageHeader title="Analytics" description="Live operational, clinical and financial reporting computed from current records."
        actions={["operations", "providers", "financial"].includes(tab) && (
          <NativeSelect value={days} onChange={(e) => set("days", e.target.value)} className="w-40" aria-label="Date range">
            <option value={30}>Last 30 days</option><option value={90}>Last 90 days</option><option value={180}>Last 180 days</option><option value={365}>Last 12 months</option>
          </NativeSelect>
        )} />
      <nav className="-mx-1 mb-5 flex gap-1 overflow-x-auto border-b px-1" aria-label="Analytics sections">
        {tabs.filter((t) => t[2]).map(([k, l]) => <button key={k} onClick={() => set("tab", k)} className={cn("-mb-px shrink-0 border-b-2 border-transparent px-3 py-2 text-table font-medium text-muted-foreground hover:text-foreground", tab === k && "border-primary text-foreground")}>{l}</button>)}
      </nav>
      {tab === "operations" && <Operations days={days} clinicId={clinic?.id} />}
      {tab === "providers" && <Providers days={days} />}
      {tab === "population" && <Population />}
      {tab === "gaps" && <CareGaps />}
      {tab === "quality" && <Quality />}
      {tab === "financial" && can("billing:read") && <Financial days={Math.max(days, 30)} />}
    </>
  );
}

type Ops = { total_appointments: number; by_status: Record<string, number>; no_show_rate: number | null; cancellation_rate: number | null; kept_rate: number | null; avg_wait_minutes: number | null; avg_visit_minutes: number | null; per_day: { date: string; completed: number; no_show: number; cancelled: number; other: number }[]; by_type: { type: string; count: number }[]; booking_channels: Record<string, number>; modes: Record<string, number>; utilization: { provider: string; available_hours: number; booked_hours: number; utilization: number }[] };

function Operations({ days, clinicId }: { days: number; clinicId?: string }) {
  const [scope, setScope] = React.useState<"clinic" | "all">("clinic");
  const q = useQuery({ queryKey: ["an-ops", days, scope, clinicId], queryFn: () => get<Ops>("/analytics/operations", { days, clinic_id: scope === "clinic" ? clinicId : undefined }) });
  if (!q.data) return <LoadingRows />;
  const d = q.data;
  const channels = Object.entries(d.booking_channels).map(([k, v]) => ({ name: { staff: "Front desk", portal: "Patient portal", ai_phone: "HMS Voice Concierge" }[k] ?? titleCase(k), value: v }));
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 text-table"><span className="text-muted-foreground">Scope:</span>
        {(["clinic", "all"] as const).map((s) => <button key={s} onClick={() => setScope(s)} className={cn("rounded-md px-2.5 py-1 font-medium text-muted-foreground", scope === s && "bg-accent text-accent-foreground")}>{s === "clinic" ? "Current location" : "All locations"}</button>)}
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Appointments" value={d.total_appointments} sub={`kept ${pct(d.kept_rate)}`} icon={CalendarCheck2} />
        <Stat label="No-show rate" value={pct(d.no_show_rate)} sub={`cancellations ${pct(d.cancellation_rate)}`} icon={UserX} tone="danger" />
        <Stat label="Avg wait to room" value={d.avg_wait_minutes != null ? `${d.avg_wait_minutes} min` : "—"} icon={Clock} tone="warning" />
        <Stat label="Avg visit length" value={d.avg_visit_minutes != null ? `${d.avg_visit_minutes} min` : "—"} icon={Timer} tone="ai" />
      </div>
      <Card>
        <CardHeader><CardTitle>Daily volume</CardTitle><ExportButton path="/analytics/export/appointments.csv" params={{ days }} /></CardHeader>
        <CardContent className="h-64">
          {!d.per_day.length ? <EmptyState title="No appointments in range" /> : (
            <ResponsiveContainer><BarChart data={d.per_day} margin={{ left: -16 }}><CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis dataKey="date" {...AX} tickFormatter={(v: string) => v.slice(5)} /><YAxis {...AX} allowDecimals={false} /><RTooltip {...TIP} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="completed" name="Completed" stackId="a" fill="var(--success)" /><Bar dataKey="other" name="Scheduled / in clinic" stackId="a" fill="var(--primary)" />
              <Bar dataKey="no_show" name="No-show" stackId="a" fill="var(--destructive)" /><Bar dataKey="cancelled" name="Cancelled" stackId="a" fill="#94a3b8" radius={[3, 3, 0, 0]} />
            </BarChart></ResponsiveContainer>
          )}
        </CardContent>
      </Card>
      <div className="grid gap-5 lg:grid-cols-3">
        <Card><CardHeader><CardTitle>Visit types</CardTitle></CardHeader><CardContent className="h-56">
          <ResponsiveContainer><BarChart data={d.by_type} layout="vertical" margin={{ left: 40 }}><XAxis type="number" {...AX} allowDecimals={false} /><YAxis type="category" dataKey="type" {...AX} width={110} /><RTooltip {...TIP} /><Bar dataKey="count" fill="var(--primary)" radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer>
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Booking channel</CardTitle></CardHeader><CardContent className="h-56">
          <ResponsiveContainer><PieChart><Pie data={channels} dataKey="value" nameKey="name" innerRadius={45} outerRadius={75} paddingAngle={2}>{channels.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><RTooltip {...TIP} /><Legend wrapperStyle={{ fontSize: 12 }} /></PieChart></ResponsiveContainer>
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Provider utilization</CardTitle></CardHeader><CardContent className="space-y-3">
          {d.utilization.map((u) => (
            <div key={u.provider}><div className="mb-1 flex justify-between text-table"><span>{u.provider}</span><span className="tabular text-muted-foreground">{u.booked_hours}h / {u.available_hours}h</span></div>
              <div className="h-2 overflow-hidden rounded-full bg-muted"><div className={cn("h-full rounded-full", u.utilization > 0.9 ? "bg-warning" : "bg-primary")} style={{ width: `${Math.min(100, u.utilization * 100)}%` }} /></div></div>
          ))}
          {!d.utilization.length && <p className="text-table text-muted-foreground">No scheduled hours in range.</p>}
        </CardContent></Card>
      </div>
    </div>
  );
}

type ProvRow = { provider_id: string; provider: string; specialty: string | null; visits_completed: number; open_encounters: number; unique_patients: number; unsigned_notes: number; avg_hours_to_sign: number | null; no_shows: number; ai_scribe_notes: number };

function Providers({ days }: { days: number }) {
  const q = useQuery({ queryKey: ["an-prov", days], queryFn: () => get<{ providers: ProvRow[] }>("/analytics/providers", { days }) });
  if (!q.data) return <LoadingRows />;
  return (
    <Card className="overflow-hidden">
      <CardHeader><CardTitle>Provider productivity</CardTitle><ExportButton path="/analytics/export/providers.csv" params={{ days }} /></CardHeader>
      <Table>
        <THead><TR><TH>Provider</TH><TH className="text-right">Visits</TH><TH className="text-right">Patients</TH><TH className="text-right">Open</TH><TH className="text-right">Unsigned notes</TH><TH className="text-right">Avg time to sign</TH><TH className="text-right">No-shows</TH><TH className="text-right">AI scribe notes</TH></TR></THead>
        <TBody>{q.data.providers.map((r) => (
          <TR key={r.provider_id} className="tabular">
            <TD><span className="font-medium">{r.provider}</span><span className="block text-xs text-muted-foreground">{r.specialty}</span></TD>
            <TD className="text-right">{r.visits_completed}</TD><TD className="text-right">{r.unique_patients}</TD><TD className="text-right">{r.open_encounters}</TD>
            <TD className={cn("text-right", r.unsigned_notes > 0 && "font-semibold text-warning")}>{r.unsigned_notes}</TD>
            <TD className="text-right">{r.avg_hours_to_sign != null ? `${r.avg_hours_to_sign} h` : "—"}</TD><TD className="text-right">{r.no_shows}</TD><TD className="text-right">{r.ai_scribe_notes}</TD>
          </TR>
        ))}</TBody>
      </Table>
    </Card>
  );
}

type Pop = { active_patients: number; registries: { key: string; label: string; patients: number }[]; age_sex: { band: string; sex: string; count: number }[]; no_visit_12m: number; multiple_chronic_conditions: number };

function Population() {
  const q = useQuery({ queryKey: ["an-pop"], queryFn: () => get<Pop>("/analytics/population") });
  if (!q.data) return <LoadingRows />;
  const d = q.data;
  const bands = ["0-17", "18-39", "40-64", "65+"].map((b) => ({ band: b, Female: d.age_sex.find((x) => x.band === b && x.sex === "female")?.count ?? 0, Male: d.age_sex.find((x) => x.band === b && x.sex === "male")?.count ?? 0 }));
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Stat label="Active patients" value={d.active_patients} icon={Users} />
        <Stat label="2+ chronic conditions" value={d.multiple_chronic_conditions} icon={HeartPulse} tone="ai" />
        <Stat label="No visit in 12 months" value={d.no_visit_12m} icon={TrendingDown} tone="warning" />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card><CardHeader><CardTitle>Chronic disease registries</CardTitle></CardHeader><CardContent className="space-y-2.5">
          {d.registries.map((r) => (
            <div key={r.key}><div className="mb-1 flex justify-between text-table"><span>{r.label}</span><span className="tabular font-medium">{r.patients} <span className="font-normal text-muted-foreground">({pct(d.active_patients ? r.patients / d.active_patients : null)})</span></span></div>
              <div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${d.active_patients ? (r.patients / d.active_patients) * 100 : 0}%` }} /></div></div>
          ))}
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Age & sex</CardTitle></CardHeader><CardContent className="h-60">
          <ResponsiveContainer><BarChart data={bands} margin={{ left: -16 }}><CartesianGrid vertical={false} stroke="var(--border)" /><XAxis dataKey="band" {...AX} /><YAxis {...AX} allowDecimals={false} /><RTooltip {...TIP} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="Female" fill="var(--ai)" radius={[4, 4, 0, 0]} /><Bar dataKey="Male" fill="var(--primary)" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer>
        </CardContent></Card>
      </div>
    </div>
  );
}

type GapRow = { patient_id: string; name: string; mrn: string; date_of_birth: string; phone: string | null; pcp: string | null; detail: string; outreach_open: boolean };

function CareGaps() {
  const qc = useQueryClient();
  const summary = useQuery({ queryKey: ["an-gaps"], queryFn: () => get<{ measures: { key: string; label: string; count: number }[] }>("/analytics/care-gaps") });
  const [measure, setMeasure] = React.useState<string | null>(null);
  const active = measure ?? summary.data?.measures[0]?.key ?? null;
  const rows = useQuery({ queryKey: ["an-gap", active], queryFn: () => get<{ patients: GapRow[] }>("/analytics/care-gaps", { measure: active! }), enabled: !!active });
  const [sel, setSel] = React.useState<Set<string>>(new Set());
  const [role, setRole] = React.useState("nurse");
  React.useEffect(() => setSel(new Set()), [active]);
  if (!summary.data) return <LoadingRows />;
  const list = rows.data?.patients ?? [];
  const selectable = list.filter((r) => !r.outreach_open);
  return (
    <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
      <Card className="h-fit overflow-hidden"><ul className="divide-y">{summary.data.measures.map((m) => (
        <li key={m.key}><button onClick={() => setMeasure(m.key)} className={cn("flex w-full items-center justify-between gap-2 px-4 py-3 text-left text-table hover:bg-muted/40", active === m.key && "bg-accent/60")}>
          <span>{m.label}</span><Badge variant={m.count ? "warning" : "success"}>{m.count}</Badge></button></li>
      ))}</ul></Card>
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b p-3">
          <span className="text-table font-medium">{summary.data.measures.find((m) => m.key === active)?.label}</span>
          <div className="ml-auto flex items-center gap-2">
            {!!sel.size && <><NativeSelect value={role} onChange={(e) => setRole(e.target.value)} className="h-8 w-36" aria-label="Assign outreach to"><option value="nurse">Nurse team</option><option value="receptionist">Front desk</option></NativeSelect>
              <Button size="sm" onClick={async () => {
                try { const r = await post<{ created: number }>("/analytics/care-gaps/outreach", { measure: active, patient_ids: [...sel], role }); toast.success(`${r.created} outreach task(s) created`); setSel(new Set()); qc.invalidateQueries({ queryKey: ["an-gap"] }); }
                catch (e) { toastError(e); }
              }}><Send />Create {sel.size} outreach task{sel.size > 1 ? "s" : ""}</Button></>}
            {active && <ExportButton path="/analytics/export/care_gaps.csv" params={{ measure: active }} />}
          </div>
        </div>
        {rows.isLoading ? <LoadingRows /> : !list.length ? <EmptyState icon={Activity} title="No patients with this gap" /> : (
          <Table>
            <THead><TR><TH className="w-8"><Checkbox aria-label="Select all" checked={selectable.length > 0 && sel.size === selectable.length} onCheckedChange={(c) => setSel(c ? new Set(selectable.map((r) => r.patient_id)) : new Set())} /></TH><TH>Patient</TH><TH>Detail</TH><TH className="hidden md:table-cell">PCP</TH><TH>Outreach</TH></TR></THead>
            <TBody>{list.map((r) => (
              <TR key={r.patient_id}>
                <TD><Checkbox aria-label={`Select ${r.name}`} disabled={r.outreach_open} checked={sel.has(r.patient_id)} onCheckedChange={(c) => { const n = new Set(sel); if (c) n.add(r.patient_id); else n.delete(r.patient_id); setSel(n); }} /></TD>
                <TD><Link to={`/patients/${r.patient_id}`} className="font-medium hover:underline">{r.name}</Link><span className="block text-xs text-muted-foreground tabular">{fmtDob(r.date_of_birth)} · {r.mrn}</span></TD>
                <TD className="text-table">{r.detail}</TD><TD className="hidden md:table-cell">{r.pcp ?? "—"}</TD>
                <TD>{r.outreach_open ? <Badge variant="info">Task open</Badge> : <span className="text-xs text-muted-foreground">—</span>}</TD>
              </TR>
            ))}</TBody>
          </Table>
        )}
      </Card>
    </div>
  );
}

type QM = { key: string; name: string; modeled_on: string; numerator: number; denominator: number; rate: number | null; lower_is_better: boolean };

function Quality() {
  const q = useQuery({ queryKey: ["an-quality"], queryFn: () => get<{ measures: QM[]; disclaimer: string }>("/analytics/quality") });
  if (!q.data) return <LoadingRows />;
  return (
    <Card>
      <CardHeader><div><CardTitle>Quality measures</CardTitle><p className="mt-0.5 text-xs text-muted-foreground">{q.data.disclaimer}</p></div><ExportButton path="/analytics/export/quality.csv" params={{}} /></CardHeader>
      <CardContent className="space-y-4">{q.data.measures.map((m) => {
        const good = m.rate == null ? null : m.lower_is_better ? m.rate <= 0.2 : m.rate >= 0.7;
        return (
          <div key={m.key}>
            <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2 text-body">
              <span className="font-medium">{m.name} <Badge variant="outline" className="ml-1">{m.modeled_on}</Badge>{m.lower_is_better && <span className="ml-1 text-xs text-muted-foreground">(lower is better)</span>}</span>
              <span className="tabular"><strong className={cn(good === false && "text-destructive", good && "text-success")}>{pct(m.rate)}</strong> <span className="text-muted-foreground">{m.numerator}/{m.denominator}</span></span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-muted"><div className={cn("h-full rounded-full", good === false ? "bg-destructive" : good ? "bg-success" : "bg-warning")} style={{ width: `${(m.rate ?? 0) * 100}%` }} /></div>
          </div>
        );
      })}</CardContent>
    </Card>
  );
}

type Fin = { charges_cents: number; collections: Record<string, number>; collected_cents: number; collection_rate: number | null; denial_rate: number | null; avg_days_to_payment: number | null; by_payer: { payer: string; claims: number; charges_cents: number; paid_cents: number; denials: number }[]; monthly: { month: string; source: string; cents: number }[] };

function Financial({ days }: { days: number }) {
  const q = useQuery({ queryKey: ["an-fin", days], queryFn: () => get<Fin>("/analytics/financial", { days: Math.max(30, days) }) });
  if (!q.data) return <LoadingRows />;
  const d = q.data;
  const months = [...new Set(d.monthly.map((m) => m.month))].map((m) => ({ month: new Date(m).toLocaleDateString("en-US", { month: "short", timeZone: "UTC" }),
    Insurance: (d.monthly.find((x) => x.month === m && x.source === "insurance")?.cents ?? 0) / 100, Patient: (d.monthly.find((x) => x.month === m && x.source === "patient")?.cents ?? 0) / 100 }));
  return (
    <div className="space-y-5">
      <SimulatedBadge label="Payer responses are simulated" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Gross charges" value={fmtMoney(d.charges_cents)} icon={Activity} />
        <Stat label="Collected" value={fmtMoney(d.collected_cents)} sub={`collection rate ${pct(d.collection_rate)}`} icon={TrendingDown} tone="success" />
        <Stat label="Denial rate" value={pct(d.denial_rate)} icon={UserX} tone="danger" />
        <Stat label="Avg days to payment" value={d.avg_days_to_payment ?? "—"} icon={Clock} tone="warning" />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card><CardHeader><CardTitle>Collections by month</CardTitle></CardHeader><CardContent className="h-60">
          <ResponsiveContainer><BarChart data={months} margin={{ left: -4 }}><CartesianGrid vertical={false} stroke="var(--border)" /><XAxis dataKey="month" {...AX} /><YAxis {...AX} /><RTooltip {...TIP} formatter={(v: unknown) => fmtMoney(Math.round(Number(v ?? 0) * 100))} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="Insurance" stackId="a" fill="var(--success)" /><Bar dataKey="Patient" stackId="a" fill="var(--warning)" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer>
        </CardContent></Card>
        <Card className="overflow-hidden"><CardHeader><CardTitle>By payer</CardTitle></CardHeader>
          <Table><THead><TR><TH>Payer</TH><TH className="text-right">Claims</TH><TH className="text-right">Charges</TH><TH className="text-right">Paid</TH><TH className="text-right">Denials</TH></TR></THead>
            <TBody>{d.by_payer.map((p) => <TR key={p.payer} className="tabular"><TD>{p.payer}</TD><TD className="text-right">{p.claims}</TD><TD className="text-right">{fmtMoney(p.charges_cents)}</TD><TD className="text-right">{fmtMoney(p.paid_cents)}</TD><TD className="text-right">{p.denials}</TD></TR>)}</TBody>
          </Table>
        </Card>
      </div>
    </div>
  );
}
