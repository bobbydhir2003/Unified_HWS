import { useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { Activity, Plus } from "lucide-react";
import * as React from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { EmptyState, ErrorState, LoadingRows } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cToF, fmtDateTime } from "@/lib/format";
import type { Vitals } from "@/lib/types";
import { cn } from "@/lib/utils";

const RANGES = {
  systolic: [90, 139], diastolic: [60, 89], heart_rate: [50, 100], respiratory_rate: [12, 20], spo2: [94, 100], temp_f: [97, 100.3],
} as const;
const flag = (k: keyof typeof RANGES, v: number | null | undefined) => v != null && (v < RANGES[k][0] || v > RANGES[k][1]);
/** "High" / "Low" / null — abnormal values are marked with an arrow AND a word, never colour alone. */
const dir = (k: keyof typeof RANGES, v: number | null | undefined): "High" | "Low" | null =>
  v == null ? null : v < RANGES[k][0] ? "Low" : v > RANGES[k][1] ? "High" : null;

export function VitalsSummary({ v, className }: { v: Vitals; className?: string }) {
  const f = cToF(v.temperature_c);
  const lb = v.weight_kg ? Math.round(Number(v.weight_kg) * 2.20462) : null;
  const items: [string, React.ReactNode, "High" | "Low" | null][] = [
    ["BP", v.systolic ? `${v.systolic}/${v.diastolic}` : null, dir("systolic", v.systolic) ?? dir("diastolic", v.diastolic)],
    ["Heart rate", v.heart_rate, dir("heart_rate", v.heart_rate)],
    ["Resp. rate", v.respiratory_rate, dir("respiratory_rate", v.respiratory_rate)],
    ["Temp", f ? `${f} °F` : null, dir("temp_f", f)],
    ["SpO₂", v.spo2 ? `${v.spo2}%` : null, dir("spo2", v.spo2)],
    ["Weight", lb ? `${lb} lb` : null, null],
    ["BMI", v.bmi, (v.bmi ?? 0) >= 30 ? "High" : null],
    ["Pain", v.pain_score != null ? `${v.pain_score}/10` : null, (v.pain_score ?? 0) >= 7 ? "High" : null],
  ];
  return (
    <dl className={cn("grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4 xl:grid-cols-8", className)}>
      {items.map(([k, val, bad]) => (
        <div key={k}>
          <dt className="text-label font-medium text-muted-foreground">{k}</dt>
          <dd className={cn("flex flex-wrap items-baseline gap-x-1.5 text-section font-semibold tabular text-heading", bad && "text-destructive")}>
            {val ?? <span className="font-normal text-muted-foreground">—</span>}
            {bad && val != null && <span className="inline-flex items-center rounded-full border border-destructive/30 bg-destructive-soft px-1.5 text-label font-medium">{bad === "High" ? "▲" : "▼"} {bad}</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

type Form = { systolic: string; diastolic: string; heart_rate: string; respiratory_rate: string; temp_f: string; spo2: string; height_in: string; weight_lb: string; pain_score: string };
const empty: Form = { systolic: "", diastolic: "", heart_rate: "", respiratory_rate: "", temp_f: "", spo2: "", height_in: "", weight_lb: "", pain_score: "" };

export function VitalsDialog({ patientId, encounterId, open, onOpenChange }: { patientId: string; encounterId?: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const [f, setF] = React.useState<Form>(empty);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => { if (open) { setF(empty); setError(null); } }, [open]);
  const num = (s: string) => (s.trim() === "" ? null : Number(s));
  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value.replace(/[^\d.]/g, "") });
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const tf = num(f.temp_f), hin = num(f.height_in), wlb = num(f.weight_lb);
    try {
      await post(`/patients/${patientId}/vitals`, {
        encounter_id: encounterId ?? null,
        systolic: num(f.systolic), diastolic: num(f.diastolic), heart_rate: num(f.heart_rate), respiratory_rate: num(f.respiratory_rate),
        temperature_c: tf != null ? Math.round(((tf - 32) * 5 / 9) * 10) / 10 : null, spo2: num(f.spo2),
        height_cm: hin != null ? Math.round(hin * 2.54 * 10) / 10 : null, weight_kg: wlb != null ? Math.round(wlb * 0.453592 * 10) / 10 : null,
        pain_score: num(f.pain_score),
      });
      qc.invalidateQueries({ queryKey: ["vitals", patientId] });
      qc.invalidateQueries({ queryKey: ["summary", patientId] });
      if (encounterId) qc.invalidateQueries({ queryKey: ["encounter", encounterId] });
      toast.success("Vitals recorded");
      onOpenChange(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Couldn't save vitals"); }
    finally { setBusy(false); }
  };
  const inp = (k: keyof Form, label: string, unit: string, hint?: string) => (
    <Field label={<>{label} <span className="font-normal text-muted-foreground">{unit}</span></>} hint={hint}>
      <Input inputMode="decimal" value={f[k]} onChange={set(k)} className="tabular" />
    </Field>
  );
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader><DialogTitle>Record vitals</DialogTitle><DialogDescription>Enter what was measured; leave the rest blank.</DialogDescription></DialogHeader>
        <form onSubmit={submit} className="grid gap-4">
          {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive-soft px-3 py-2 text-table text-destructive">{error}</div>}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            {inp("systolic", "Systolic", "mmHg")}{inp("diastolic", "Diastolic", "mmHg")}{inp("heart_rate", "Heart rate", "bpm")}
            {inp("respiratory_rate", "Resp. rate", "/min")}{inp("temp_f", "Temperature", "°F")}{inp("spo2", "SpO₂", "%")}
            {inp("height_in", "Height", "in")}{inp("weight_lb", "Weight", "lb")}{inp("pain_score", "Pain", "0–10")}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" loading={busy}>Save vitals</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function VitalsTab({ patientId }: { patientId: string }) {
  const { can } = useAuth();
  const [open, setOpen] = React.useState(false);
  const q = useQuery({ queryKey: ["vitals", patientId], queryFn: () => get<Vitals[]>(`/patients/${patientId}/vitals`, { limit: 100 }) });
  const series = (q.data ?? []).slice().reverse().filter((v) => v.systolic || v.weight_kg).map((v) => ({
    label: format(parseISO(v.measured_at), "MMM d"), systolic: v.systolic, diastolic: v.diastolic, weight: v.weight_kg ? Math.round(Number(v.weight_kg) * 2.20462) : null,
  }));
  return (
    <div className="grid gap-5">
      <div className="flex justify-end">{can("clinical:write") && <Button onClick={() => setOpen(true)}><Plus />Record vitals</Button>}</div>
      {q.error ? <ErrorState error={q.error} retry={q.refetch} /> : q.isLoading ? <LoadingRows /> : !q.data?.length ? (
        <Card><EmptyState icon={Activity} title="No vitals recorded" /></Card>
      ) : (
        <>
          {series.length > 1 && (
            <Card>
              <CardHeader><CardTitle>Trends</CardTitle></CardHeader>
              <CardContent className="h-60">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={series} margin={{ left: -16, right: 8 }}>
                    <CartesianGrid vertical={false} stroke="var(--border)" />
                    <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} />
                    <YAxis yAxisId="bp" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} domain={[40, "auto"]} />
                    <YAxis yAxisId="wt" orientation="right" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} domain={["auto", "auto"]} />
                    <RTooltip contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} />
                    <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                    <Line yAxisId="bp" dataKey="systolic" name="Systolic" stroke="var(--primary)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                    <Line yAxisId="bp" dataKey="diastolic" name="Diastolic" stroke="var(--ai)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                    <Line yAxisId="wt" dataKey="weight" name="Weight (lb)" stroke="var(--success)" strokeWidth={2} strokeDasharray="4 3" dot={{ r: 2 }} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}
          <Card className="overflow-hidden">
            <Table>
              <THead><TR><TH>Measured</TH><TH>BP</TH><TH>HR</TH><TH>RR</TH><TH>Temp</TH><TH>SpO₂</TH><TH>Weight</TH><TH>BMI</TH><TH>Pain</TH></TR></THead>
              <TBody>
                {q.data.map((v) => (
                  <TR key={v.id} className="tabular">
                    <TD className="whitespace-nowrap text-muted-foreground">{fmtDateTime(v.measured_at)}</TD>
                    <TD className={cn((flag("systolic", v.systolic) || flag("diastolic", v.diastolic)) && "font-semibold text-destructive")}>{v.systolic ? `${v.systolic}/${v.diastolic}` : "—"}</TD>
                    <TD className={cn(flag("heart_rate", v.heart_rate) && "font-semibold text-destructive")}>{v.heart_rate ?? "—"}</TD>
                    <TD>{v.respiratory_rate ?? "—"}</TD>
                    <TD>{v.temperature_c ? `${cToF(v.temperature_c)}°F` : "—"}</TD>
                    <TD className={cn(flag("spo2", v.spo2) && "font-semibold text-destructive")}>{v.spo2 ? `${v.spo2}%` : "—"}</TD>
                    <TD>{v.weight_kg ? `${Math.round(Number(v.weight_kg) * 2.20462)} lb` : "—"}</TD>
                    <TD>{v.bmi ?? "—"}</TD>
                    <TD>{v.pain_score ?? "—"}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </Card>
        </>
      )}
      <VitalsDialog patientId={patientId} open={open} onOpenChange={setOpen} />
    </div>
  );
}
