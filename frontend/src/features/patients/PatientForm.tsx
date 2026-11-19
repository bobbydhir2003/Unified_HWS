import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, UserPlus } from "lucide-react";
import * as React from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { PageHeader, useUnsavedChanges } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { ApiError, get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDob } from "@/lib/format";
import type { Patient, Provider } from "@/lib/types";

const opt = z.string().trim().optional().or(z.literal(""));
export const patientSchema = z.object({
  first_name: z.string().trim().min(1, "Required"),
  middle_name: opt,
  last_name: z.string().trim().min(1, "Required"),
  preferred_name: opt,
  date_of_birth: z.string().min(1, "Required").refine((v) => !Number.isNaN(Date.parse(v)) && new Date(v) <= new Date(), "Enter a valid past date"),
  sex_at_birth: z.enum(["female", "male", "intersex", "unknown"], { error: "Select sex assigned at birth" }),
  gender_identity: opt,
  pronouns: opt,
  email: z.email("Enter a valid email").optional().or(z.literal("")),
  phone: opt.refine((v) => !v || v.replace(/\D/g, "").length >= 10, "Enter a 10-digit phone number"),
  phone_alt: opt,
  address_line1: opt,
  address_line2: opt,
  city: opt,
  state: opt,
  postal_code: opt,
  preferred_language: z.string().min(1),
  marital_status: opt,
  emergency_contact_name: opt,
  emergency_contact_relation: opt,
  emergency_contact_phone: opt,
  primary_clinic_id: opt,
  primary_provider_id: opt,
  notes: opt,
  status: z.enum(["active", "inactive", "deceased"]).optional(),
  ins_payer: opt,
  ins_plan: opt,
  ins_member: opt,
  ins_group: opt,
});
export type PatientFormValues = z.infer<typeof patientSchema>;

type Dup = { id: string; mrn: string; name: string; date_of_birth: string; phone: string | null; reasons: string[]; score: number };

function clean(v: PatientFormValues) {
  const out: Record<string, unknown> = {};
  for (const [k, val] of Object.entries(v)) {
    if (k.startsWith("ins_")) continue;
    out[k] = val === "" ? null : val;
  }
  return out;
}

export function PatientFields({ form, mode }: { form: ReturnType<typeof useForm<PatientFormValues>>; mode: "new" | "edit" }) {
  const { membership } = useAuth();
  const providers = useQuery({ queryKey: ["providers"], queryFn: () => get<Provider[]>("/providers") });
  const e = form.formState.errors;
  const r = form.register;
  return (
    <div className="grid gap-5">
      <Card>
        <CardHeader><CardTitle>Identity</CardTitle></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="First name" required error={e.first_name?.message}><Input autoFocus={mode === "new"} {...r("first_name")} /></Field>
          <Field label="Middle name"><Input {...r("middle_name")} /></Field>
          <Field label="Last name" required error={e.last_name?.message}><Input {...r("last_name")} /></Field>
          <Field label="Preferred name"><Input {...r("preferred_name")} /></Field>
          <Field label="Date of birth" required error={e.date_of_birth?.message}><Input type="date" max={new Date().toISOString().slice(0, 10)} {...r("date_of_birth")} /></Field>
          <Field label="Sex assigned at birth" required error={e.sex_at_birth?.message}>
            <NativeSelect {...r("sex_at_birth")}><option value="" disabled>Select…</option><option value="female">Female</option><option value="male">Male</option><option value="intersex">Intersex</option><option value="unknown">Unknown</option></NativeSelect>
          </Field>
          <Field label="Gender identity"><Input {...r("gender_identity")} /></Field>
          <Field label="Pronouns"><Input placeholder="e.g. she/her" {...r("pronouns")} /></Field>
          {mode === "edit" && (
            <Field label="Status">
              <NativeSelect {...r("status")}><option value="active">Active</option><option value="inactive">Inactive</option><option value="deceased">Deceased</option></NativeSelect>
            </Field>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Contact</CardTitle></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Mobile phone" error={e.phone?.message}><Input type="tel" autoComplete="off" {...r("phone")} /></Field>
          <Field label="Alternate phone"><Input type="tel" {...r("phone_alt")} /></Field>
          <Field label="Email" error={e.email?.message} className="lg:col-span-2"><Input type="email" autoComplete="off" {...r("email")} /></Field>
          <Field label="Address" className="sm:col-span-2"><Input {...r("address_line1")} /></Field>
          <Field label="Address line 2" className="sm:col-span-2"><Input {...r("address_line2")} /></Field>
          <Field label="City"><Input {...r("city")} /></Field>
          <Field label="State"><Input {...r("state")} /></Field>
          <Field label="ZIP"><Input {...r("postal_code")} /></Field>
          <Field label="Preferred language"><Input {...r("preferred_language")} /></Field>
        </CardContent>
      </Card>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Emergency contact</CardTitle></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" className="sm:col-span-2"><Input {...r("emergency_contact_name")} /></Field>
            <Field label="Relationship"><Input {...r("emergency_contact_relation")} /></Field>
            <Field label="Phone"><Input type="tel" {...r("emergency_contact_phone")} /></Field>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Care team</CardTitle></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field label="Primary location">
              <NativeSelect {...r("primary_clinic_id")}>
                <option value="">—</option>
                {membership?.clinics.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Primary provider">
              <NativeSelect {...r("primary_provider_id")}>
                <option value="">—</option>
                {providers.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Front-desk notes" className="sm:col-span-2" hint="Administrative only — not part of the medical record.">
              <Textarea rows={2} {...r("notes")} />
            </Field>
          </CardContent>
        </Card>
      </div>
      {mode === "new" && (
        <Card>
          <CardHeader><CardTitle>Primary insurance <span className="font-normal text-muted-foreground">(optional)</span></CardTitle></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Payer"><Input {...r("ins_payer")} /></Field>
            <Field label="Plan"><Input {...r("ins_plan")} /></Field>
            <Field label="Member ID"><Input {...r("ins_member")} /></Field>
            <Field label="Group #"><Input {...r("ins_group")} /></Field>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export function NewPatientPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { clinic } = useAuth();
  const form = useForm<PatientFormValues>({
    resolver: zodResolver(patientSchema),
    defaultValues: { sex_at_birth: "" as PatientFormValues["sex_at_birth"], preferred_language: "English", primary_clinic_id: clinic?.id ?? "" },
  });
  const [dups, setDups] = React.useState<Dup[] | null>(null);
  const [saving, setSaving] = React.useState(false);
  const blocker = useUnsavedChanges(form.formState.isDirty && !saving);

  const submit = async (v: PatientFormValues, confirm = false) => {
    setSaving(true);
    try {
      const insurance = v.ins_payer && v.ins_member ? { payer_name: v.ins_payer, plan_name: v.ins_plan || null, member_id: v.ins_member, group_number: v.ins_group || null } : null;
      if (v.ins_payer && !v.ins_member) { toast.error("Insurance member ID is required when a payer is entered"); setSaving(false); return; }
      const p = await post<Patient>("/patients", { ...clean(v), insurance, confirm_not_duplicate: confirm });
      qc.invalidateQueries({ queryKey: ["patients"] });
      toast.success(`${p.first_name} ${p.last_name} registered · MRN ${p.mrn}`);
      form.reset(v);
      navigate(`/patients/${p.id}`, { replace: true });
    } catch (e) {
      setSaving(false);
      if (e instanceof ApiError && e.code === "possible_duplicate") {
        setDups((e.detail as { candidates: Dup[] }).candidates);
        return;
      }
      toast.error(e instanceof Error ? e.message : "Registration failed");
    }
  };

  return (
    <form onSubmit={form.handleSubmit((v) => submit(v))} noValidate>
      {blocker}
      <PageHeader title="Register patient" description="Required fields are marked *. We'll check for possible duplicates before creating the record."
        actions={<>
          <Button type="button" variant="outline" onClick={() => navigate(-1)}>Cancel</Button>
          <Button type="submit" loading={saving}><UserPlus />Register</Button>
        </>} />
      <PatientFields form={form} mode="new" />
      <div className="mt-5 flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={() => navigate(-1)}>Cancel</Button>
        <Button type="submit" loading={saving}><UserPlus />Register patient</Button>
      </div>

      <Dialog open={!!dups} onOpenChange={(o) => !o && setDups(null)}>
        <DialogContent size="md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><AlertTriangle className="size-4 text-warning" />Possible duplicate patient</DialogTitle>
            <DialogDescription>Existing records look similar. Open the existing chart if it's the same person — duplicate charts split the medical record.</DialogDescription>
          </DialogHeader>
          <ul className="divide-y rounded-lg border">
            {dups?.map((d) => (
              <li key={d.id} className="flex items-center gap-3 p-3">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{d.name} <span className="font-mono text-xs text-muted-foreground">{d.mrn}</span></p>
                  <p className="text-xs text-muted-foreground tabular">DOB {fmtDob(d.date_of_birth)}{d.phone ? ` · ${d.phone}` : ""}</p>
                  <p className="mt-0.5 text-xs text-warning">Match: {d.reasons.join(", ")}</p>
                </div>
                <Button type="button" variant="outline" size="sm" onClick={() => { form.reset(form.getValues()); setSaving(true); navigate(`/patients/${d.id}`); }}>Open chart</Button>
              </li>
            ))}
          </ul>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDups(null)}>Go back</Button>
            <Button type="button" variant="destructive" onClick={() => { setDups(null); submit(form.getValues(), true); }}>
              Not a duplicate — create new record
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </form>
  );
}

export function EditPatientDialog({ patient, open, onOpenChange }: { patient: Patient; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const toForm = (p: Patient): PatientFormValues => {
    const o: Record<string, unknown> = {};
    for (const k of Object.keys(patientSchema.shape)) o[k] = (p as unknown as Record<string, unknown>)[k] ?? "";
    return o as PatientFormValues;
  };
  const form = useForm<PatientFormValues>({ resolver: zodResolver(patientSchema), values: toForm(patient) });
  return (
    <Dialog open={open} onOpenChange={(o) => {
      if (!o && form.formState.isDirty && !window.confirm("Discard unsaved changes?")) return;
      onOpenChange(o);
    }}>
      <DialogContent size="xl" className="bg-background">
        <DialogHeader><DialogTitle>Edit demographics</DialogTitle><DialogDescription>Changes are recorded in the audit log.</DialogDescription></DialogHeader>
        <form noValidate onSubmit={form.handleSubmit(async (v) => {
          try {
            await put(`/patients/${patient.id}`, clean(v));
            qc.invalidateQueries({ queryKey: ["patient", patient.id] });
            toast.success("Demographics updated");
            form.reset(v);
            onOpenChange(false);
          } catch (e) { toast.error(e instanceof Error ? e.message : "Update failed"); }
        })}>
          <PatientFields form={form} mode="edit" />
          <DialogFooter className="mt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" loading={form.formState.isSubmitting} disabled={!form.formState.isDirty}>Save changes</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
