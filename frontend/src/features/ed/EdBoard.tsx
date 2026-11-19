import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Ambulance, BedDouble, Fingerprint, HeartPulse, LogOut, Radio, Siren, Stethoscope, UserPlus } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { EmptyState, ErrorState, LoadingRows, PageHeader, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useLiveStatus } from "@/lib/live";
import { cn, titleCase } from "@/lib/utils";
import { PatientPicker } from "../inpatient/shared";

type Visit = {
  id: string; status: string; patient: { id: string; name: string; mrn: string; sex: string; dob: string; temporary: boolean; merged_into_id: string | null };
  arrival_at: string; arrival_mode: string; chief_complaint: string; esi_level: number | null; bay: { id: string; name: string } | null;
  provider: string | null; nurse: string | null; encounter_id: string | null; stay_id: string | null; minutes_in_department: number | null;
  door_to_triage: number | null; door_to_provider: number | null; boarding_minutes: number | null;
};
type Board = { facility: { id: string; name: string }; visits: Visit[]; bays: { id: string; name: string; status: string }[];
  metrics: { in_department: number; waiting: number; boarding: number; arrivals_24h: number; lwbs_24h: number; median_door_to_provider_min: number | null; median_los_min: number | null } };

const ESI_STYLE: Record<number, string> = { 1: "bg-destructive text-white", 2: "bg-destructive/80 text-white", 3: "bg-warning text-foreground", 4: "bg-primary/70 text-white", 5: "bg-muted text-foreground" };
const mins = (m: number | null) => (m == null ? "—" : m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${m % 60}m`);

export function EdBoard() {
  const { can } = useAuth();
  const live = useLiveStatus();
  const q = useQuery({ queryKey: ["ed", "board"], queryFn: () => get<Board>("/ed/board"), refetchInterval: 30_000 });
  const [arrive, setArrive] = React.useState(false);
  const [act, setAct] = React.useState<{ v: Visit; kind: "triage" | "room" | "dispo" | "reconcile" } | null>(null);
  const d = q.data;
  return (
    <>
      <PageHeader title="Emergency department" description="Live tracking board. Acuity (ESI) is assessed and recorded by nurses or physicians — the system never assigns it."
        actions={<div className="flex items-center gap-2">
          <Badge variant={live ? "success" : "neutral"}><Radio className={cn(live && "animate-pulse")} />{live ? "Live" : "Polling"}</Badge>
          {can("ed:write") && <Button onClick={() => setArrive(true)}><UserPlus />New arrival</Button>}
        </div>} />
      {q.isError ? <ErrorState error={q.error} retry={q.refetch} /> : !d ? <LoadingRows rows={8} /> : (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {[["In department", d.metrics.in_department], ["Waiting", d.metrics.waiting], ["Boarding", d.metrics.boarding], ["Arrivals 24 h", d.metrics.arrivals_24h],
              ["Median door→provider", mins(d.metrics.median_door_to_provider_min)], ["Left without being seen", d.metrics.lwbs_24h]].map(([l, v]) => (
              <div key={l as string} className="rounded-xl border bg-card px-3 py-2.5"><p className="text-xs text-muted-foreground">{l}</p><p className="text-xl font-semibold tabular">{v}</p></div>))}
          </div>
          <Card className="overflow-hidden">
            {!d.visits.length ? <EmptyState icon={Siren} title="No patients in the department" /> : (
              <Table><THead><TR><TH>ESI</TH><TH>Patient</TH><TH>Complaint</TH><TH>Bay</TH><TH>Time in ED</TH><TH>Provider / nurse</TH><TH>Status</TH><TH /></TR></THead>
                <TBody>{d.visits.map((v) => (
                  <TR key={v.id}>
                    <TD>{v.esi_level ? <span className={cn("inline-grid size-7 place-items-center rounded-md text-[13px] font-bold", ESI_STYLE[v.esi_level])} aria-label={`ESI ${v.esi_level}`}>{v.esi_level}</span> : <Badge variant="outline">Not triaged</Badge>}</TD>
                    <TD><p className="font-medium">{v.patient.name}</p><p className="text-xs text-muted-foreground">{v.patient.mrn}{v.arrival_mode === "ambulance" && <><Ambulance className="ml-1 inline size-3" /> EMS</>}</p>
                      {v.patient.temporary && <Badge variant="warning" className="mt-1"><Fingerprint />Temporary identity</Badge>}</TD>
                    <TD className="max-w-56 truncate">{v.chief_complaint}</TD>
                    <TD className="whitespace-nowrap">{v.bay?.name ?? "—"}</TD>
                    <TD className={cn("tabular", (v.minutes_in_department ?? 0) > 240 && "font-medium text-destructive")}>{mins(v.minutes_in_department)}
                      {v.status === "boarding" && <p className="text-xs text-warning">boarding {mins(v.boarding_minutes)}</p>}</TD>
                    <TD className="text-[13px]">{v.provider ?? <span className="text-muted-foreground">No provider</span>}{v.nurse && <p className="text-xs text-muted-foreground">RN {v.nurse}</p>}</TD>
                    <TD><Badge variant={v.status === "boarding" ? "warning" : v.status === "roomed" ? "primary" : "neutral"}>{titleCase(v.status)}</Badge></TD>
                    <TD><div className="flex flex-wrap justify-end gap-1">
                      {can("ed:write") && (can("nursing:write") || can("clinical:sign")) && v.status !== "boarding" && <Button size="xs" variant="outline" onClick={() => setAct({ v, kind: "triage" })}><HeartPulse />{v.esi_level ? "Re-triage" : "Triage"}</Button>}
                      {can("ed:write") && ["waiting", "triaged"].includes(v.status) && <Button size="xs" variant="outline" onClick={() => setAct({ v, kind: "room" })}><BedDouble />Room</Button>}
                      {can("ed:write") && !v.provider && can("clinical:sign") && <AssignMe v={v} />}
                      {can("orders:sign") && ["triaged", "roomed"].includes(v.status) && <Button size="xs" onClick={() => setAct({ v, kind: "dispo" })}><LogOut />Disposition</Button>}
                      {v.patient.temporary && can("patients:write") && <Button size="xs" variant="outline" onClick={() => setAct({ v, kind: "reconcile" })}><Fingerprint />Identify</Button>}
                      {v.encounter_id && <Button size="xs" variant="ghost" asChild><Link to={`/encounters/${v.encounter_id}`}><Stethoscope />Chart</Link></Button>}
                    </div></TD>
                  </TR>))}</TBody></Table>
            )}
          </Card>
          <Card className="mt-4"><CardHeader><CardTitle className="flex items-center gap-2 text-[15px]"><BedDouble className="size-4" />Bays</CardTitle></CardHeader>
            <CardContent className="flex flex-wrap gap-2">{d.bays.map((b) => <span key={b.id} className={cn("rounded-md border px-2.5 py-1 text-xs", b.status === "available" ? "border-success/40 bg-success-soft/40" : b.status === "cleaning" ? "border-warning/50 bg-warning-soft/50" : "bg-muted/60")}>{b.name} · {b.status}</span>)}</CardContent></Card>
        </>
      )}
      <ArrivalDialog open={arrive} onOpenChange={setArrive} />
      {act && d && <ActionDialog act={act} board={d} onClose={() => setAct(null)} />}
    </>
  );
}

function useRefresh() {
  const qc = useQueryClient();
  return () => { qc.invalidateQueries({ queryKey: ["ed"] }); qc.invalidateQueries({ queryKey: ["beds"] }); qc.invalidateQueries({ queryKey: ["adt"] }); };
}

function AssignMe({ v }: { v: Visit }) {
  const refresh = useRefresh();
  return <Button size="xs" variant="outline" onClick={async () => { try { await post(`/ed/visits/${v.id}/assign`, { me: true }); toast.success("You're the provider for this patient"); refresh(); } catch (e) { toastError(e); } }}>Assign me</Button>;
}

function ArrivalDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const refresh = useRefresh();
  const [patient, setPatient] = React.useState<Parameters<typeof PatientPicker>[0]["value"]>(null);
  const [unknown, setUnknown] = React.useState(false);
  const [f, setF] = React.useState({ chief_complaint: "", arrival_mode: "walk_in", sex: "unknown", approx_age: "" });
  const submit = async () => {
    try {
      await post("/ed/arrivals", { patient_id: unknown ? null : patient?.id, unidentified: unknown, sex: f.sex, approx_age: f.approx_age ? Number(f.approx_age) : null,
        chief_complaint: f.chief_complaint, arrival_mode: f.arrival_mode });
      toast.success("Patient registered in the ED"); onOpenChange(false); setPatient(null); setUnknown(false); setF({ chief_complaint: "", arrival_mode: "walk_in", sex: "unknown", approx_age: "" }); refresh();
    } catch (e) { toastError(e); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md"><DialogHeader><DialogTitle>New ED arrival</DialogTitle><DialogDescription>Quick registration. Unidentified patients get a temporary record that is merged into the real chart once identity is verified.</DialogDescription></DialogHeader>
        <label className="flex items-center gap-2 text-[13.5px]"><Checkbox checked={unknown} onCheckedChange={(x) => setUnknown(!!x)} />Patient can't be identified yet</label>
        {unknown ? (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Sex"><NativeSelect value={f.sex} onChange={(e) => setF({ ...f, sex: e.target.value })}><option value="unknown">Unknown</option><option value="female">Female</option><option value="male">Male</option></NativeSelect></Field>
            <Field label="Approximate age"><Input inputMode="numeric" value={f.approx_age} onChange={(e) => setF({ ...f, approx_age: e.target.value })} /></Field>
          </div>
        ) : <Field label="Patient" required><PatientPicker value={patient} onChange={setPatient} /></Field>}
        <Field label="Chief complaint" required><Input value={f.chief_complaint} onChange={(e) => setF({ ...f, chief_complaint: e.target.value })} /></Field>
        <Field label="Arrival"><NativeSelect value={f.arrival_mode} onChange={(e) => setF({ ...f, arrival_mode: e.target.value })}>{[["walk_in", "Walk-in"], ["ambulance", "Ambulance"], ["police", "Police"], ["transfer", "Transfer"], ["other", "Other"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect></Field>
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={f.chief_complaint.trim().length < 2 || (!unknown && !patient)} onClick={submit}>Register</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ActionDialog({ act, board, onClose }: { act: { v: Visit; kind: "triage" | "room" | "dispo" | "reconcile" }; board: Board; onClose: () => void }) {
  const refresh = useRefresh();
  const { v, kind } = act;
  const [esi, setEsi] = React.useState(String(v.esi_level ?? ""));
  const [vit, setVit] = React.useState<Record<string, string>>({});
  const [notes, setNotes] = React.useState("");
  const [bay, setBay] = React.useState("");
  const [dispo, setDispo] = React.useState({ disposition: "discharged", note: "", admit_reason: v.chief_complaint, level_of_care: "med_surg" });
  const [real, setReal] = React.useState<Parameters<typeof PatientPicker>[0]["value"]>(null);
  const [method, setMethod] = React.useState("");
  const [attest, setAttest] = React.useState(false);
  const run = async (path: string, body: unknown, ok: string) => { try { await post(path, body); toast.success(ok); refresh(); onClose(); } catch (e) { toastError(e); } };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="md">
        <DialogHeader><DialogTitle>{{ triage: "Triage", room: "Room patient", dispo: "Disposition", reconcile: "Identify patient" }[kind]} — {v.patient.name}</DialogTitle><DialogDescription>{v.chief_complaint}</DialogDescription></DialogHeader>
        {kind === "triage" && <>
          <Field label="ESI level (your clinical assessment)" required><div className="flex gap-2">{[1, 2, 3, 4, 5].map((n) => <button key={n} type="button" onClick={() => setEsi(String(n))} className={cn("size-10 rounded-lg border text-[15px] font-bold", esi === String(n) ? ESI_STYLE[n] : "hover:bg-muted")} aria-pressed={esi === String(n)}>{n}</button>)}</div></Field>
          <div className="grid grid-cols-3 gap-3">{[["heart_rate", "HR"], ["respiratory_rate", "RR"], ["spo2", "SpO₂"], ["systolic", "Systolic"], ["diastolic", "Diastolic"], ["pain_score", "Pain"]].map(([k, l]) => <Field key={k} label={l}><Input inputMode="numeric" value={vit[k] ?? ""} onChange={(e) => setVit({ ...vit, [k]: e.target.value })} /></Field>)}</div>
          <Field label="Triage notes"><Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        </>}
        {kind === "room" && <Field label="Bay"><NativeSelect value={bay} onChange={(e) => setBay(e.target.value)}><option value="">Choose…</option>{board.bays.filter((b) => b.status === "available").map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</NativeSelect></Field>}
        {kind === "dispo" && <>
          <Field label="Disposition"><NativeSelect value={dispo.disposition} onChange={(e) => setDispo({ ...dispo, disposition: e.target.value })}>{[["discharged", "Discharge home"], ["admit", "Admit to hospital"], ["transferred", "Transfer out"], ["lwbs", "Left without being seen"], ["ama", "Left against medical advice"], ["expired", "Expired"]].map(([x, l]) => <option key={x} value={x}>{l}</option>)}</NativeSelect></Field>
          {dispo.disposition === "admit" ? <>
            <Field label="Admission reason" required><Input value={dispo.admit_reason} onChange={(e) => setDispo({ ...dispo, admit_reason: e.target.value })} /></Field>
            <Field label="Level of care"><NativeSelect value={dispo.level_of_care} onChange={(e) => setDispo({ ...dispo, level_of_care: e.target.value })}>{[["med_surg", "Med-surg"], ["telemetry", "Telemetry"], ["icu", "ICU"], ["observation", "Observation"]].map(([x, l]) => <option key={x} value={x}>{l}</option>)}</NativeSelect></Field>
            <p className="text-xs text-muted-foreground">The patient stays here (boarding) until bed management assigns an inpatient bed.</p>
          </> : <Field label="Note"><Textarea rows={2} value={dispo.note} onChange={(e) => setDispo({ ...dispo, note: e.target.value })} /></Field>}
        </>}
        {kind === "reconcile" && <>
          <Field label="Verified patient record" required><PatientPicker value={real} onChange={setReal} /></Field>
          <Field label="How was identity verified?" required><Input value={method} onChange={(e) => setMethod(e.target.value)} placeholder="e.g. Driver's license checked at bedside" /></Field>
          <label className="flex items-start gap-2 text-[13px]"><Checkbox className="mt-0.5" checked={attest} onCheckedChange={(x) => setAttest(!!x)} />I verified this patient's identity. All records from the temporary identity will move to the selected chart (audited).</label>
        </>}
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button>
          {kind === "triage" && <Button disabled={!esi} onClick={() => { const vitals = Object.fromEntries(Object.entries(vit).filter(([, x]) => x.trim()).map(([k, x]) => [k, Number(x)])); run(`/ed/visits/${v.id}/triage`, { esi_level: Number(esi), notes: notes || null, vitals: Object.keys(vitals).length ? vitals : null }, `Triage recorded (ESI ${esi})`); }}>Save triage</Button>}
          {kind === "room" && <Button disabled={!bay} onClick={() => run(`/ed/visits/${v.id}/room`, { bed_id: bay }, "Patient roomed")}>Room</Button>}
          {kind === "dispo" && <Button onClick={() => run(`/ed/visits/${v.id}/disposition`, { ...dispo, note: dispo.note || null }, dispo.disposition === "admit" ? "Admission requested — patient boarding" : "Disposition recorded")}>Confirm</Button>}
          {kind === "reconcile" && <Button disabled={!real || !attest || method.trim().length < 3} onClick={() => run(`/ed/visits/${v.id}/reconcile`, { patient_id: real!.id, method, attest_identity_verified: attest }, "Records merged into the verified chart")}>Merge records</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

