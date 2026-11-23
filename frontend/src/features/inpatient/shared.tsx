/** Shared inpatient types + small components (patient picker, bed status chip, admit dialog). */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect } from "@/components/ui/input";
import { get, post } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Department } from "../admin/FacilitiesPage";

export type StayT = {
  id: string; status: string; patient: { id: string; name: string; mrn: string; dob: string; sex: string; restricted: boolean };
  facility_id: string; department: { id: string; name: string } | null; bed: { id: string; code: string; name: string } | null;
  attending: string | null; reason: string; admit_source: string; level_of_care: string; isolation: string | null; requested_at: string;
  admitted_at: string | null; waiting_hours: number | null; los_hours: number | null; expected_discharge_date: string | null;
  discharge_ordered_at: string | null; discharge_disposition: string | null; discharged_at: string | null; encounter_id: string | null;
};

export const BED_STYLE: Record<string, { label: string; tile: string; dot: string }> = {
  available: { label: "Available", tile: "border-success/40 bg-success-soft/40 hover:bg-success-soft/70", dot: "bg-success" },
  occupied: { label: "Occupied", tile: "border-primary/30 bg-card hover:bg-accent/60", dot: "bg-primary" },
  reserved: { label: "Reserved", tile: "border-info/40 bg-info-soft/60", dot: "bg-primary/50" },
  cleaning: { label: "Cleaning", tile: "border-warning/50 bg-warning-soft/60 hover:bg-warning-soft", dot: "bg-warning" },
  blocked: { label: "Blocked", tile: "border-dashed border-muted-foreground/40 bg-muted/60 text-muted-foreground", dot: "bg-muted-foreground" },
};

export function BedStatusChip({ status }: { status: string }) {
  const s = BED_STYLE[status] ?? BED_STYLE.available;
  return <span className="inline-flex items-center gap-1.5 text-xs"><span className={cn("size-2 rounded-full", s.dot)} />{s.label}</span>;
}

export function losLabel(h: number | null | undefined) {
  if (h == null) return "—";
  return h < 24 ? `${Math.round(h)} h` : `${Math.floor(h / 24)} d ${Math.round(h % 24)} h`;
}

type PatientHit = { id: string; first_name: string; last_name: string; mrn: string; date_of_birth: string };

export function PatientPicker({ value, onChange }: { value: PatientHit | null; onChange: (p: PatientHit | null) => void }) {
  const [q, setQ] = React.useState("");
  const res = useQuery({ queryKey: ["patients", "pick", q], queryFn: () => get<{ items: PatientHit[] }>("/patients", { q, page_size: 6 }), enabled: q.length >= 2 });
  if (value) return (
    <div className="flex items-center justify-between rounded-lg border px-3 py-2 text-body">
      <span><span className="font-medium">{value.first_name} {value.last_name}</span> <span className="text-xs text-muted-foreground">{value.mrn} · DOB {fmtDate(value.date_of_birth)}</span></span>
      <button className="text-xs text-primary hover:underline" onClick={() => onChange(null)}>Change</button>
    </div>
  );
  return (
    <div>
      <div className="relative"><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" /><Input className="pl-9" placeholder="Search by name or MRN…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find patient" /></div>
      {res.data?.items.length ? <ul className="mt-1 max-h-48 divide-y overflow-auto rounded-lg border">{res.data.items.map((p) => (
        <li key={p.id}><button className="w-full px-3 py-2 text-left text-table hover:bg-muted/50" onClick={() => onChange(p)}>{p.first_name} {p.last_name} <span className="text-xs text-muted-foreground">{p.mrn} · {fmtDate(p.date_of_birth)}</span></button></li>))}</ul> : null}
    </div>
  );
}

export function AdmitDialog({ open, onOpenChange, facilityId, bedId, defaultPatient }: { open: boolean; onOpenChange: (o: boolean) => void; facilityId?: string; bedId?: string; defaultPatient?: PatientHit | null }) {
  const qc = useQueryClient();
  const [patient, setPatient] = React.useState<PatientHit | null>(defaultPatient ?? null);
  const [f, setF] = React.useState({ reason: "", level_of_care: "med_surg", department_id: "", isolation: "", admit_source: "direct" });
  const depts = useQuery({ queryKey: ["departments", facilityId, "inpatient"], queryFn: () => get<Department[]>("/departments", { facility_id: facilityId }), enabled: open && !!facilityId });
  const [busy, setBusy] = React.useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await post("/adt/stays", { patient_id: patient!.id, facility_id: facilityId, reason: f.reason, level_of_care: f.level_of_care, admit_source: f.admit_source,
        department_id: f.department_id || null, isolation: f.isolation || null, bed_id: bedId ?? null });
      toast.success(bedId ? "Patient admitted" : "Admission requested — waiting for a bed");
      qc.invalidateQueries({ queryKey: ["adt"] }); onOpenChange(false);
    } catch (e) { toastError(e); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader><DialogTitle>{bedId ? "Admit to this bed" : "Request admission"}</DialogTitle><DialogDescription>Admission is recorded with the requesting clinician as attending unless changed later.</DialogDescription></DialogHeader>
        <Field label="Patient" required><PatientPicker value={patient} onChange={setPatient} /></Field>
        <Field label="Reason for admission" required><Input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} placeholder="e.g. Community-acquired pneumonia, hypoxic" /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Level of care"><NativeSelect value={f.level_of_care} onChange={(e) => setF({ ...f, level_of_care: e.target.value })}>{[["med_surg", "Med-surg"], ["telemetry", "Telemetry"], ["icu", "ICU"], ["observation", "Observation"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect></Field>
          <Field label="Requested unit"><NativeSelect value={f.department_id} onChange={(e) => setF({ ...f, department_id: e.target.value })}><option value="">Any</option>{depts.data?.filter((d) => ["inpatient", "icu"].includes(d.kind)).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</NativeSelect></Field>
          <Field label="Source"><NativeSelect value={f.admit_source} onChange={(e) => setF({ ...f, admit_source: e.target.value })}>{[["direct", "Direct"], ["ed", "Emergency department"], ["elective", "Elective"], ["transfer_in", "Transfer in"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect></Field>
          <Field label="Isolation"><NativeSelect value={f.isolation} onChange={(e) => setF({ ...f, isolation: e.target.value })}><option value="">None</option><option value="contact">Contact</option><option value="droplet">Droplet</option><option value="airborne">Airborne</option></NativeSelect></Field>
        </div>
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button loading={busy} disabled={!patient || f.reason.trim().length < 3} onClick={submit}>{bedId ? "Admit" : "Request admission"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function StayStatusBadge({ status }: { status: string }) {
  const v: Record<string, React.ComponentProps<typeof Badge>["variant"]> = { pending: "warning", admitted: "primary", discharge_ordered: "info", discharged: "success", cancelled: "neutral" };
  return <Badge variant={v[status] ?? "neutral"}>{status === "discharge_ordered" ? "Discharge ordered" : status.charAt(0).toUpperCase() + status.slice(1)}</Badge>;
}
