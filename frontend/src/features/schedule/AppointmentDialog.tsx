import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Search, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { ApiError, get, patch, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDob, sexShort } from "@/lib/format";
import type { Appointment, AppointmentType, Provider } from "@/lib/types";
import { fromZoned, hhmm, minutesOfDay, todayIn, ymd, zoned } from "@/lib/tz";
import { cn } from "@/lib/utils";

export type PatientPick = { id: string; name: string; mrn: string; date_of_birth: string; sex_at_birth?: string };

export function PatientPicker({ value, onChange }: { value: PatientPick | null; onChange: (p: PatientPick | null) => void }) {
  const [q, setQ] = React.useState("");
  const [dq, setDq] = React.useState("");
  React.useEffect(() => { const t = setTimeout(() => setDq(q.trim()), 200); return () => clearTimeout(t); }, [q]);
  const { data, isFetching } = useQuery({ queryKey: ["search", dq], queryFn: () => get<{ patients: PatientPick[] }>("/search", { q: dq }), enabled: dq.length >= 2 });
  if (value) {
    return (
      <div className="flex items-center gap-3 rounded-lg border bg-accent/40 px-3 py-2">
        <div className="min-w-0 flex-1">
          <p className="font-medium">{value.name}</p>
          <p className="text-xs text-muted-foreground tabular">DOB {fmtDob(value.date_of_birth)}{value.sex_at_birth ? ` · ${sexShort(value.sex_at_birth)}` : ""} · MRN {value.mrn}</p>
        </div>
        <Button type="button" variant="ghost" size="icon-sm" onClick={() => onChange(null)} aria-label="Change patient"><X /></Button>
      </div>
    );
  }
  return (
    <div>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, MRN or DOB" className="pl-9" aria-label="Find patient" />
      </div>
      {dq.length >= 2 && (
        <ul className="mt-1.5 max-h-48 overflow-y-auto rounded-lg border">
          {isFetching && !data && <li className="px-3 py-2 text-table text-muted-foreground">Searching…</li>}
          {data?.patients.length === 0 && <li className="px-3 py-2 text-table text-muted-foreground">No matches.</li>}
          {data?.patients.map((p) => (
            <li key={p.id}>
              <button type="button" onClick={() => onChange(p)} className="flex w-full flex-col px-3 py-2 text-left hover:bg-muted">
                <span className="text-body font-medium">{p.name}</span>
                <span className="text-xs text-muted-foreground tabular">DOB {fmtDob(p.date_of_birth)}{p.sex_at_birth ? ` · ${sexShort(p.sex_at_birth)}` : ""} · MRN {p.mrn}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

type Props = {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  patient?: PatientPick | null;
  initialStart?: Date | null;
  initialProviderId?: string;
  editing?: Appointment | null;
  onSaved?: (a: Appointment) => void;
};

export function AppointmentDialog({ open, onOpenChange, patient: fixedPatient, initialStart, initialProviderId, editing, onSaved }: Props) {
  const { clinic, membership } = useAuth();
  const qc = useQueryClient();
  const tz = clinic?.timezone ?? "America/New_York";
  const providers = useQuery({ queryKey: ["providers"], queryFn: () => get<Provider[]>("/providers"), enabled: open });
  const types = useQuery({ queryKey: ["appointment-types"], queryFn: () => get<AppointmentType[]>("/appointment-types"), enabled: open });

  const [patient, setPatient] = React.useState<PatientPick | null>(null);
  const [providerId, setProviderId] = React.useState("");
  const [clinicId, setClinicId] = React.useState("");
  const [typeId, setTypeId] = React.useState("");
  const [date, setDate] = React.useState("");
  const [time, setTime] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [needsOverride, setNeedsOverride] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setError(null);
    setNeedsOverride(false);
    if (editing) {
      setPatient({ id: editing.patient.id, name: editing.patient.name, mrn: editing.patient.mrn, date_of_birth: editing.patient.date_of_birth, sex_at_birth: editing.patient.sex_at_birth });
      setProviderId(editing.provider.id);
      setClinicId(editing.clinic.id);
      setTypeId(editing.appointment_type?.id ?? "");
      setDate(ymd(zoned(editing.start_at, tz)));
      const m = minutesOfDay(editing.start_at, tz);
      setTime(`${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`);
      setReason(editing.reason ?? "");
      setNotes(editing.notes ?? "");
    } else {
      setPatient(fixedPatient ?? null);
      setProviderId(initialProviderId ?? membership?.provider_id ?? "");
      setClinicId(clinic?.id ?? "");
      setTypeId("");
      if (initialStart) {
        setDate(ymd(zoned(initialStart, tz)));
        const m = minutesOfDay(initialStart, tz);
        setTime(`${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`);
      } else { setDate(todayIn(tz)); setTime(""); }
      setReason("");
      setNotes("");
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    if (!typeId && types.data?.length) setTypeId(types.data.find((t) => t.name === "Follow-up")?.id ?? types.data[0].id);
  }, [types.data, typeId]);
  React.useEffect(() => {
    if (!providerId && providers.data?.length) setProviderId(providers.data[0].id);
  }, [providers.data, providerId]);

  const type = types.data?.find((t) => t.id === typeId);
  const slots = useQuery({
    queryKey: ["slots", providerId, clinicId, date, type?.duration_minutes],
    queryFn: () => get<{ slots: string[] }>(`/providers/${providerId}/slots`, { clinic_id: clinicId, day: date, duration: type?.duration_minutes ?? 20 }),
    enabled: open && !!providerId && !!clinicId && !!date,
  });

  const submit = async (override = false) => {
    if (!patient || !providerId || !clinicId || !date || !time) { setError("Patient, provider, location, date and time are required."); return; }
    setBusy(true);
    setError(null);
    const [h, m] = time.split(":").map(Number);
    const start = fromZoned(date, h * 60 + m, tz);
    const body = { provider_id: providerId, clinic_id: clinicId, appointment_type_id: typeId || null, start_at: start.toISOString(), reason: reason || null, notes: notes || null, override_availability: override };
    try {
      const a = editing
        ? await patch<Appointment>(`/appointments/${editing.id}`, body)
        : await post<Appointment>("/appointments", { ...body, patient_id: patient.id, mode: type?.is_telehealth ? "telehealth" : "in_person" });
      toast.success(editing ? "Appointment rescheduled" : `Booked ${patient.name} · ${hhmm(h * 60 + m)}`);
      qc.invalidateQueries({ queryKey: ["appointments"] });
      qc.invalidateQueries({ queryKey: ["queue"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["summary", patient.id] });
      qc.invalidateQueries({ queryKey: ["patient-appts", patient.id] });
      onSaved?.(a);
      onOpenChange(false);
    } catch (e) {
      setNeedsOverride(e instanceof ApiError && e.code === "outside_availability");
      setError(e instanceof Error ? e.message : "Couldn't save appointment");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>{editing ? "Reschedule appointment" : "Book appointment"}</DialogTitle>
          <DialogDescription>Times shown in {tz.replace("_", " ")}.</DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); submit(false); }}>
          {error && (
            <div role="alert" className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive-soft px-3 py-2 text-table text-destructive">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <div className="flex-1">
                {error}
                {needsOverride && (
                  <div className="mt-2"><Button type="button" size="xs" variant="outline" onClick={() => submit(true)}>Book anyway (override hours)</Button></div>
                )}
              </div>
            </div>
          )}
          <Field label="Patient" required>
            {fixedPatient || editing ? <div><PatientPicker value={patient} onChange={() => {}} /></div> : <div><PatientPicker value={patient} onChange={setPatient} /></div>}
          </Field>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Provider" required>
              <NativeSelect value={providerId} onChange={(e) => setProviderId(e.target.value)}>
                {providers.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Location" required>
              <NativeSelect value={clinicId} onChange={(e) => setClinicId(e.target.value)}>
                {membership?.clinics.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Visit type">
              <NativeSelect value={typeId} onChange={(e) => setTypeId(e.target.value)}>
                {types.data?.filter((t) => t.is_active).map((t) => <option key={t.id} value={t.id}>{t.name} · {t.duration_minutes}m{t.is_telehealth ? " · video" : ""}</option>)}
              </NativeSelect>
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-[1fr_1fr]">
            <Field label="Date" required><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
            <Field label="Time" required><Input type="time" step={300} value={time} onChange={(e) => setTime(e.target.value)} /></Field>
          </div>
          <div>
            <p className="mb-1.5 text-table font-medium">Open slots</p>
            {slots.isLoading ? <p className="text-xs text-muted-foreground">Loading availability…</p> : !slots.data?.slots.length ? (
              <p className="text-xs text-muted-foreground">No open slots for this provider, location and day. You can still choose a time manually.</p>
            ) : (
              <div className="flex max-h-28 flex-wrap gap-1.5 overflow-y-auto">
                {slots.data.slots.map((s) => {
                  const mins = minutesOfDay(s, tz);
                  const v = `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
                  return (
                    <button key={s} type="button" onClick={() => setTime(v)}
                      className={cn("rounded-md border px-2 py-1 text-xs tabular hover:border-primary hover:text-primary", time === v && "border-primary bg-primary text-primary-foreground hover:text-primary-foreground")}>
                      {hhmm(mins)}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          <Field label="Reason for visit"><Input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} placeholder="e.g. Follow-up on blood pressure" /></Field>
          <Field label="Scheduling notes"><Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" loading={busy}>{editing ? "Save changes" : "Book appointment"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
