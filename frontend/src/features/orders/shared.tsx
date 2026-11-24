import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Ban, CheckCircle2, ClipboardCheck, FileSignature, FlaskConical, Info, Pill, ScanLine, Send, Stethoscope, TestTube } from "lucide-react";
import { Dialog as D } from "radix-ui";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { KeyValue, SimulatedBadge, toastError, useConfirm } from "@/components/common";
import { Icd10Picker } from "@/components/common/FormDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, fmtDob } from "@/lib/format";
import { cn, titleCase } from "@/lib/utils";

export type OrderType = "medication" | "lab" | "imaging" | "referral" | "procedure" | "nursing";
export type Warning = { type: string; severity: "high" | "moderate" | "low" | "info"; message: string };
export type LabResultT = { id: string; name: string; value: string; unit: string | null; reference_range: string | null; flag: string; status: string; resulted_at: string; source: string };
export type Order = {
  id: string; patient_id: string; patient: { id: string; name: string; mrn: string; date_of_birth: string }; encounter_id: string | null;
  order_type: OrderType; status: "draft" | "signed" | "transmitted" | "in_progress" | "resulted" | "completed" | "cancelled"
    | "pending_verification" | "clarification_needed" | "rejected" | "active" | "on_hold" | "discontinued";
  priority: "routine" | "urgent" | "stat"; title: string; code: string | null; details: Record<string, unknown>; indication_codes: string[];
  notes: string | null; ordered_by: string; signed_by: string | null; signed_at: string | null; safety_warnings: Warning[] | null;
  safety_override_reason: string | null; transmitted_at: string | null; transmission: { channel: string; reference: string; simulated: boolean; destination: string } | null;
  resulted_at: string | null; result_text: string | null; results: LabResultT[]; results_reviewed_at: string | null;
  released_to_patient_at: string | null; cancelled_reason: string | null; created_at: string;
};

export const TYPE_ICON: Record<OrderType, typeof Pill> = { medication: Pill, lab: TestTube, imaging: ScanLine, referral: Send, procedure: Stethoscope, nursing: ClipboardCheck };
const STATUS_VARIANT: Record<Order["status"], React.ComponentProps<typeof Badge>["variant"]> = {
  draft: "warning", signed: "info", transmitted: "info", in_progress: "primary", resulted: "ai", completed: "success", cancelled: "neutral",
  pending_verification: "warning", clarification_needed: "warning", rejected: "danger", active: "success", on_hold: "neutral", discontinued: "neutral",
};
const STATUS_LABEL: Partial<Record<Order["status"], string>> = {
  transmitted: "Sent", resulted: "Results in", in_progress: "In progress", draft: "Unsigned",
  pending_verification: "Awaiting pharmacist", clarification_needed: "Pharmacist query", active: "Active (verified)", on_hold: "On hold",
};

export function OrderStatusBadge({ o }: { o: Order }) {
  const critical = o.results.some((r) => r.flag.startsWith("critical"));
  return (
    <span className="inline-flex items-center gap-1">
      <Badge variant={critical && o.status === "resulted" ? "danger" : STATUS_VARIANT[o.status]}>{critical && o.status === "resulted" ? "Critical result" : STATUS_LABEL[o.status] ?? titleCase(o.status)}</Badge>
      {o.priority !== "routine" && <Badge variant="danger">{o.priority.toUpperCase()}</Badge>}
    </span>
  );
}

export const flagClass = (f: string) => f === "normal" ? "" : f.startsWith("critical") ? "font-bold text-destructive" : "font-semibold text-destructive";
export const flagLabel = (f: string) => ({ high: "H", low: "L", critical_high: "HH", critical_low: "LL", abnormal: "A" })[f] ?? "";

export function ResultsTable({ results }: { results: LabResultT[] }) {
  return (
    <table className="w-full text-table">
      <thead><tr className="border-b text-left text-label uppercase tracking-wide text-muted-foreground"><th className="py-1.5">Test</th><th>Result</th><th>Ref range</th><th /></tr></thead>
      <tbody>
        {results.map((r) => (
          <tr key={r.id} className="border-b last:border-0">
            <td className="py-1.5 pr-2">{r.name}</td>
            <td className={cn("pr-2 tabular", flagClass(r.flag))}>{r.value} {r.unit}</td>
            <td className="pr-2 text-muted-foreground tabular">{r.reference_range}</td>
            <td className={cn("text-xs", flagClass(r.flag))}>{flagLabel(r.flag)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------------------------------------------------

type MedCat = { name: string; strengths: string[]; form: string; route: string; default_sig: string; drug_class: string };
type LabCat = { code: string; name: string; specimen: string; components: string[] };

function CatalogSearch<T>({ path, label, render, onPick, minChars = 1 }: { path: string; label: string; render: (x: T) => React.ReactNode; onPick: (x: T) => void; minChars?: number }) {
  const [q, setQ] = React.useState("");
  const { data } = useQuery({ queryKey: ["catalog", path, q], queryFn: () => get<T[]>(path, { q }), enabled: q.length >= minChars || minChars === 0, staleTime: 60_000 });
  return (
    <div>
      <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={label} aria-label={label} />
      {!!data?.length && (
        <ul className="mt-1.5 max-h-48 overflow-y-auto rounded-lg border">
          {data.map((x, i) => <li key={i}><button type="button" className="w-full px-3 py-2 text-left text-table hover:bg-muted" onClick={() => onPick(x)}>{render(x)}</button></li>)}
        </ul>
      )}
    </div>
  );
}

export function NewOrderDialog({ open, onOpenChange, patientId, encounterId, initialIndications = [], onCreated }: {
  open: boolean; onOpenChange: (o: boolean) => void; patientId: string; encounterId?: string; initialIndications?: string[]; onCreated?: (o: Order) => void;
}) {
  const qc = useQueryClient();
  const [type, setType] = React.useState<OrderType>("medication");
  const [priority, setPriority] = React.useState<"routine" | "urgent" | "stat">("routine");
  const [indications, setIndications] = React.useState<string[]>(initialIndications);
  const [notes, setNotes] = React.useState("");
  const [med, setMed] = React.useState<MedCat | null>(null);
  const [medF, setMedF] = React.useState({ strength: "", sig: "", quantity: "30", refills: "0", days_supply: "30", pharmacy: "", setting: "auto", frequency: "", prn_interval_hours: "4", prn_reason: "" });
  const [lab, setLab] = React.useState<LabCat | null>(null);
  const [fasting, setFasting] = React.useState(false);
  const [img, setImg] = React.useState<{ code: string; name: string } | null>(null);
  const [imgF, setImgF] = React.useState({ laterality: "n/a", contrast: false, clinical_question: "" });
  const spec = useQuery({ queryKey: ["specialists"], queryFn: () => get<{ specialties: string[]; specialists: { specialty: string; name: string; organization: string; phone: string }[] }>("/catalog/specialists"), enabled: open });
  const [refF, setRefF] = React.useState({ specialty: "", specialist: "", reason: "" });
  const [procF, setProcF] = React.useState({ name: "", body_site: "", instructions: "" });
  const [nurF, setNurF] = React.useState({ instruction: "", frequency: "" });
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (open) { setMed(null); setLab(null); setImg(null); setNotes(""); setPriority("routine"); setIndications(initialIndications); setRefF({ specialty: "", specialist: "", reason: "" }); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const details = (): Record<string, unknown> | null => {
    if (type === "medication") {
      if (!med || !medF.strength || !medF.sig) return null;
      const inpatient = medF.setting === "inpatient";
      if (inpatient && !medF.frequency) return null;
      return {
        name: med.name, strength: medF.strength, dose: medF.strength, form: med.form, route: med.route, sig: medF.sig,
        quantity: inpatient ? 1 : Number(medF.quantity), refills: inpatient ? 0 : Number(medF.refills), days_supply: inpatient ? null : Number(medF.days_supply) || null,
        pharmacy: inpatient ? null : medF.pharmacy || null, setting: medF.setting === "auto" ? null : medF.setting, frequency: medF.frequency || null,
        prn_interval_hours: medF.frequency === "prn" ? Number(medF.prn_interval_hours) || 4 : null, prn_reason: medF.frequency === "prn" ? medF.prn_reason || null : null,
      };
    }
    if (type === "lab") return lab ? { code: lab.code, fasting } : null;
    if (type === "imaging") return img && imgF.clinical_question.trim().length >= 3 ? { code: img.code, ...imgF } : null;
    if (type === "procedure") return procF.name.trim().length >= 2 ? { name: procF.name, body_site: procF.body_site || null, instructions: procF.instructions || null } : null;
    if (type === "nursing") return nurF.instruction.trim().length >= 3 ? { instruction: nurF.instruction, frequency: nurF.frequency || null } : null;
    const s = spec.data?.specialists.find((x) => x.name === refF.specialist);
    return refF.specialty && refF.reason.trim().length >= 5 ? { specialty: refF.specialty, reason: refF.reason, specialist_name: s?.name ?? null, specialist_org: s?.organization ?? null, specialist_phone: s?.phone ?? null } : null;
  };
  const submit = async () => {
    const d = details();
    if (!d) return;
    setBusy(true);
    try {
      const o = await post<Order>("/orders", { patient_id: patientId, encounter_id: encounterId ?? null, order_type: type, priority, details: d, indication_codes: indications, notes: notes || null });
      toast.success(`Draft order created: ${o.title}`);
      qc.invalidateQueries({ queryKey: ["orders"] });
      onCreated?.(o);
      onOpenChange(false);
    } catch (e) { toastError(e); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader><DialogTitle>New order</DialogTitle><DialogDescription>Orders are saved as drafts. A clinician signs them to send (transmission is simulated in this environment).</DialogDescription></DialogHeader>
        <Tabs value={type} onValueChange={(v) => setType(v as OrderType)}>
          <TabsList>
            <TabsTrigger value="medication"><Pill />Medication</TabsTrigger>
            <TabsTrigger value="lab"><TestTube />Lab</TabsTrigger>
            <TabsTrigger value="imaging"><ScanLine />Imaging</TabsTrigger>
            <TabsTrigger value="referral"><Send />Referral</TabsTrigger>
            <TabsTrigger value="procedure"><Stethoscope />Procedure</TabsTrigger>
            <TabsTrigger value="nursing"><ClipboardCheck />Nursing</TabsTrigger>
          </TabsList>
          <TabsContent value="medication" className="space-y-3">
            {!med ? (
              <CatalogSearch<MedCat> path="/catalog/medications" label="Search medications" render={(m) => <><span className="font-medium">{m.name}</span> <span className="text-muted-foreground">{m.form} · {m.strengths.join(", ")}</span></>}
                onPick={(m) => { setMed(m); setMedF({ ...medF, strength: m.strengths[0], sig: m.default_sig }); }} />
            ) : (
              <div className="grid gap-3 sm:grid-cols-4">
                <div className="flex items-center justify-between rounded-lg border bg-accent/30 px-3 py-2 sm:col-span-4"><span><strong>{med.name}</strong> <span className="text-muted-foreground">{med.form} · {med.route}</span></span><Button size="xs" variant="ghost" onClick={() => setMed(null)}>Change</Button></div>
                <Field label="Setting" hint="Auto: inpatient if the patient is currently admitted">
                  <NativeSelect value={medF.setting} onChange={(e) => setMedF({ ...medF, setting: e.target.value })}>
                    <option value="auto">Auto</option><option value="inpatient">Inpatient (MAR)</option><option value="outpatient">Outpatient prescription</option>
                  </NativeSelect>
                </Field>
                <Field label="Dose"><NativeSelect value={medF.strength} onChange={(e) => setMedF({ ...medF, strength: e.target.value })}>{med.strengths.map((s) => <option key={s}>{s}</option>)}</NativeSelect></Field>
                <Field label="Frequency" required={medF.setting === "inpatient"} hint="Required for inpatient (MAR) orders">
                  <NativeSelect value={medF.frequency} onChange={(e) => setMedF({ ...medF, frequency: e.target.value })}>
                    <option value="">—</option>
                    {[["once", "Once"], ["daily", "Daily"], ["bid", "Twice daily"], ["tid", "Three times daily"], ["qid", "Four times daily"], ["q4h", "Every 4 h"], ["q6h", "Every 6 h"], ["q8h", "Every 8 h"], ["q12h", "Every 12 h"], ["prn", "As needed (PRN)"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </NativeSelect>
                </Field>
                <Field label="Route"><Input value={med.route} readOnly aria-readonly /></Field>
                {medF.frequency === "prn" && <>
                  <Field label="PRN minimum interval (h)"><Input inputMode="decimal" value={medF.prn_interval_hours} onChange={(e) => setMedF({ ...medF, prn_interval_hours: e.target.value.replace(/[^\d.]/g, "") })} /></Field>
                  <Field label="PRN reason" className="sm:col-span-3"><Input value={medF.prn_reason} onChange={(e) => setMedF({ ...medF, prn_reason: e.target.value })} placeholder="e.g. nausea" /></Field>
                </>}
                {medF.setting !== "inpatient" && <><Field label="Quantity"><Input inputMode="numeric" value={medF.quantity} onChange={(e) => setMedF({ ...medF, quantity: e.target.value.replace(/\D/g, "") })} /></Field>
                <Field label="Refills"><Input inputMode="numeric" value={medF.refills} onChange={(e) => setMedF({ ...medF, refills: e.target.value.replace(/\D/g, "").slice(0, 2) })} /></Field>
                <Field label="Days supply"><Input inputMode="numeric" value={medF.days_supply} onChange={(e) => setMedF({ ...medF, days_supply: e.target.value.replace(/\D/g, "") })} /></Field>
                <Field label="Pharmacy" className="sm:col-span-4" hint="Pharmacy directory integration is not connected yet."><Input value={medF.pharmacy} onChange={(e) => setMedF({ ...medF, pharmacy: e.target.value })} placeholder="e.g. Harbor Pharmacy (synthetic), 12 Main St" /></Field></>}
                <Field label="Sig (directions)" className="sm:col-span-4"><Input value={medF.sig} onChange={(e) => setMedF({ ...medF, sig: e.target.value })} /></Field>
              </div>
            )}
          </TabsContent>
          <TabsContent value="lab" className="space-y-3">
            {!lab ? (
              <CatalogSearch<LabCat> path="/catalog/labs" label="Search lab tests" minChars={0} render={(l) => <><span className="font-medium">{l.name}</span> <span className="font-mono text-xs text-muted-foreground">{l.code}</span></>} onPick={setLab} />
            ) : (
              <div className="space-y-2">
                <div className="flex items-center justify-between rounded-lg border bg-accent/30 px-3 py-2"><span><strong>{lab.name}</strong> <span className="text-muted-foreground">{lab.specimen}</span></span><Button size="xs" variant="ghost" onClick={() => setLab(null)}>Change</Button></div>
                <p className="text-xs text-muted-foreground">Includes: {lab.components.join(", ")}</p>
                <label className="flex items-center gap-2 text-table"><Checkbox checked={fasting} onCheckedChange={(c) => setFasting(!!c)} />Fasting specimen</label>
              </div>
            )}
          </TabsContent>
          <TabsContent value="imaging" className="space-y-3">
            {!img ? (
              <CatalogSearch<{ code: string; name: string }> path="/catalog/imaging" label="Search imaging studies" minChars={0} render={(x) => <><span className="font-medium">{x.name}</span> <span className="font-mono text-xs text-muted-foreground">CPT {x.code}</span></>} onPick={setImg} />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="flex items-center justify-between rounded-lg border bg-accent/30 px-3 py-2 sm:col-span-2"><strong>{img.name}</strong><Button size="xs" variant="ghost" onClick={() => setImg(null)}>Change</Button></div>
                <Field label="Laterality"><NativeSelect value={imgF.laterality} onChange={(e) => setImgF({ ...imgF, laterality: e.target.value })}>{["n/a", "left", "right", "bilateral"].map((x) => <option key={x}>{x}</option>)}</NativeSelect></Field>
                <label className="flex items-end gap-2 pb-2 text-table"><Checkbox checked={imgF.contrast} onCheckedChange={(c) => setImgF({ ...imgF, contrast: !!c })} />With contrast</label>
                <Field label="Clinical question" required className="sm:col-span-2"><Textarea rows={2} value={imgF.clinical_question} onChange={(e) => setImgF({ ...imgF, clinical_question: e.target.value })} /></Field>
              </div>
            )}
          </TabsContent>
          <TabsContent value="procedure" className="grid gap-3 sm:grid-cols-2">
            <Field label="Procedure" required className="sm:col-span-2" hint="Procedure codes (CPT) need an AMA licence; describe the procedure."><Input value={procF.name} onChange={(e) => setProcF({ ...procF, name: e.target.value })} /></Field>
            <Field label="Body site"><Input value={procF.body_site} onChange={(e) => setProcF({ ...procF, body_site: e.target.value })} /></Field>
            <Field label="Instructions" className="sm:col-span-2"><Textarea rows={2} value={procF.instructions} onChange={(e) => setProcF({ ...procF, instructions: e.target.value })} /></Field>
          </TabsContent>
          <TabsContent value="nursing" className="grid gap-3 sm:grid-cols-2">
            <Field label="Nursing instruction" required className="sm:col-span-2"><Input value={nurF.instruction} onChange={(e) => setNurF({ ...nurF, instruction: e.target.value })} placeholder="e.g. Neurological checks" /></Field>
            <Field label="Frequency"><Input value={nurF.frequency} onChange={(e) => setNurF({ ...nurF, frequency: e.target.value })} placeholder="e.g. Every 2 hours" /></Field>
          </TabsContent>
          <TabsContent value="referral" className="grid gap-3 sm:grid-cols-2">
            <Field label="Specialty" required><NativeSelect value={refF.specialty} onChange={(e) => setRefF({ ...refF, specialty: e.target.value, specialist: "" })}><option value="">Select…</option>{spec.data?.specialties.map((s) => <option key={s}>{s}</option>)}</NativeSelect></Field>
            <Field label="Specialist"><NativeSelect value={refF.specialist} onChange={(e) => setRefF({ ...refF, specialist: e.target.value })} disabled={!refF.specialty}><option value="">Any available</option>{spec.data?.specialists.filter((s) => s.specialty === refF.specialty).map((s) => <option key={s.name} value={s.name}>{s.name} — {s.organization}</option>)}</NativeSelect></Field>
            <Field label="Reason for referral" required className="sm:col-span-2"><Textarea rows={3} value={refF.reason} onChange={(e) => setRefF({ ...refF, reason: e.target.value })} /></Field>
          </TabsContent>
        </Tabs>
        <div className="grid gap-3 sm:grid-cols-[160px_1fr]">
          <Field label="Priority"><NativeSelect value={priority} onChange={(e) => setPriority(e.target.value as typeof priority)}><option value="routine">Routine</option><option value="urgent">Urgent</option><option value="stat">STAT</option></NativeSelect></Field>
          <Field label="Indication (ICD-10)">
            <div className="space-y-1.5">
              <Icd10Picker clearOnPick value="" placeholder="Add indication…" onPick={(c) => !indications.includes(c) && setIndications([...indications, c])} />
              <div className="flex flex-wrap gap-1">{indications.map((c) => <button key={c} type="button" onClick={() => setIndications(indications.filter((x) => x !== c))}><Badge variant="outline">{c} ×</Badge></button>)}</div>
            </div>
          </Field>
        </div>
        <Field label="Notes"><Input value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={busy} disabled={!details()}>Save draft order</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function SignOrderDialog({ order, onOpenChange, onSigned }: { order: Order | null; onOpenChange: (o: boolean) => void; onSigned?: (o: Order) => void }) {
  const qc = useQueryClient();
  const [warnings, setWarnings] = React.useState<Warning[]>([]);
  const [reason, setReason] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { setWarnings(order?.safety_warnings ?? []); setReason(""); }, [order]);
  if (!order) return null;
  const sign = async () => {
    setBusy(true);
    try {
      const o = await post<Order>(`/orders/${order.id}/sign`, { override_reason: reason || null });
      toast.success(`${o.title} signed · ${o.transmission?.channel}`);
      ["orders", "orders-counts", "medications", "summary"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      onSigned?.(o);
      onOpenChange(false);
    } catch (e) {
      if (e instanceof ApiError && e.code === "safety_warnings") setWarnings((e.detail as { warnings: Warning[] }).warnings);
      else toastError(e);
    } finally { setBusy(false); }
  };
  const blocking = warnings.filter((w) => w.severity !== "info");
  const notices = warnings.filter((w) => w.severity === "info");
  const needsReason = blocking.length > 0;
  const inpatientMed = order.order_type === "medication" && (order.details as { setting?: string }).setting !== "outpatient";
  return (
    <Dialog open={!!order} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>Sign order</DialogTitle>
          <DialogDescription>{order.title} for {order.patient.name} (DOB {order.patient.date_of_birth ? fmtDob(order.patient.date_of_birth) : "—"})</DialogDescription>
        </DialogHeader>
        <OrderSummary o={order} />
        {needsReason && (
          <div className="space-y-2 rounded-lg border border-destructive/40 bg-destructive-soft p-3">
            {blocking.map((w, i) => <p key={i} className="flex gap-2 text-table text-destructive"><AlertTriangle className="mt-0.5 size-4 shrink-0" /><span><strong className="uppercase">{w.severity}</strong> · {w.message}</span></p>)}
            <p className="text-xs text-muted-foreground">Basic allergy and duplicate checks only — not comprehensive clinical decision support.</p>
            <Field label="Override reason" required><Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
          </div>
        )}
        {notices.map((w, i) => <p key={i} className="flex gap-2 rounded-lg border border-warning/35 bg-warning-soft p-3 text-table text-warning-foreground" data-testid="screening-notice"><Info className="mt-0.5 size-4 shrink-0" />{w.message}</p>)}
        <p className="flex items-center gap-2 text-xs text-muted-foreground"><FlaskConical className="size-3.5" />
          {inpatientMed ? "Inpatient medication orders go to the pharmacist verification queue; nothing can be dispensed or given until a pharmacist verifies it."
            : "Signing transmits through a simulated channel — no pharmacy, lab or specialist receives it."}</p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={sign} loading={busy} disabled={needsReason && reason.trim().length < 5} variant={needsReason ? "destructive" : "default"}>
            <FileSignature />{needsReason ? "Override & sign" : "Sign & send"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function OrderSummary({ o }: { o: Order }) {
  const d = o.details as Record<string, string | number | boolean | null>;
  return (
    <dl className="grid grid-cols-2 gap-3 rounded-lg border p-3 text-table">
      {o.order_type === "medication" && <>
        <KeyValue label="Sig" value={String(d.sig)} className="col-span-2" />
        <KeyValue label="Quantity / refills" value={`${d.quantity} · ${d.refills} refill(s)`} />
        <KeyValue label="Pharmacy" value={d.pharmacy as string} />
      </>}
      {o.order_type === "lab" && <><KeyValue label="Specimen" value={d.specimen as string} /><KeyValue label="Fasting" value={d.fasting ? "Yes" : "No"} /></>}
      {o.order_type === "imaging" && <><KeyValue label="Clinical question" value={d.clinical_question as string} className="col-span-2" /><KeyValue label="Contrast" value={d.contrast ? "Yes" : "No"} /></>}
      {o.order_type === "referral" && <><KeyValue label="To" value={[d.specialist_name, d.specialist_org].filter(Boolean).join(" — ") || "Any available"} className="col-span-2" /><KeyValue label="Reason" value={d.reason as string} className="col-span-2" /></>}
      <KeyValue label="Indication" value={o.indication_codes.join(", ")} />
      <KeyValue label="Priority" value={titleCase(o.priority)} />
    </dl>
  );
}

export function OrderDrawer({ order, onOpenChange, showPatient = true }: { order: Order | null; onOpenChange: (o: boolean) => void; showPatient?: boolean }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const { confirm, dialog } = useConfirm();
  const [signing, setSigning] = React.useState<Order | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  const o = order;
  const refresh = () => ["orders", "orders-counts", "results", "notifications"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const act = async (k: string, path: string, body?: unknown, params?: string) => {
    setBusy(k);
    try { await post(`/orders/${o!.id}/${path}${params ?? ""}`, body ?? {}); refresh(); } catch (e) { toastError(e); } finally { setBusy(null); }
  };
  const Icon = o ? TYPE_ICON[o.order_type] : Pill;
  return (
    <>
      {dialog}
      <Dialog open={!!o} onOpenChange={onOpenChange}>
        <SheetContent className="max-w-lg" aria-describedby={undefined}>
          {o && (
            <div className="flex h-full flex-col">
              <div className="border-b px-6 py-5">
                <D.Title className="flex items-center gap-2 text-base font-semibold"><Icon className="size-4 text-muted-foreground" />{o.title}</D.Title>
                <div className="mt-2 flex flex-wrap items-center gap-2"><OrderStatusBadge o={o} />{o.transmission?.simulated && <SimulatedBadge label="Simulated transmission" />}</div>
                {showPatient && <p className="mt-2 text-table"><Link to={`/patients/${o.patient_id}`} className="font-medium text-primary hover:underline">{o.patient.name}</Link> <span className="text-muted-foreground tabular">· MRN {o.patient.mrn}</span></p>}
              </div>
              <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
                <OrderSummary o={o} />
                <dl className="grid grid-cols-2 gap-3 text-table">
                  <KeyValue label="Ordered by" value={`${o.ordered_by} · ${fmtDateTime(o.created_at)}`} className="col-span-2" />
                  {o.signed_by && <KeyValue label="Signed by" value={`${o.signed_by} · ${fmtDateTime(o.signed_at)}`} className="col-span-2" />}
                  {o.transmission && <KeyValue label="Sent via" value={`${o.transmission.channel} → ${o.transmission.destination} (${o.transmission.reference})`} className="col-span-2" />}
                  {o.safety_override_reason && <KeyValue label="Safety override" value={o.safety_override_reason} className="col-span-2" />}
                  {o.cancelled_reason && <KeyValue label="Cancelled" value={o.cancelled_reason} className="col-span-2" />}
                </dl>
                {o.results.length > 0 && (
                  <div>
                    <p className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Results · {fmtDateTime(o.resulted_at)} {o.results[0].source === "simulated" && <SimulatedBadge />}</p>
                    <ResultsTable results={o.results} />
                  </div>
                )}
                {o.result_text && <div><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{o.order_type === "referral" ? "Referral updates" : "Report"}</p><p className="whitespace-pre-wrap text-table">{o.result_text}</p></div>}
                {o.results_reviewed_at && <p className="flex items-center gap-1.5 text-table text-success"><CheckCircle2 className="size-4" />Reviewed {fmtDateTime(o.results_reviewed_at)}{o.released_to_patient_at ? " · released to patient portal" : ""}</p>}
              </div>
              <div className="flex flex-wrap gap-2 border-t px-6 py-4">
                {o.status === "draft" && can("orders:sign") && <Button size="sm" onClick={() => setSigning(o)}><FileSignature />Sign</Button>}
                {o.status === "draft" && !can("orders:sign") && <span className="text-xs text-muted-foreground">Awaiting clinician signature</span>}
                {["transmitted", "in_progress"].includes(o.status) && ["lab", "imaging"].includes(o.order_type) && (
                  <Button size="sm" variant="outline" loading={busy === "sim"} onClick={() => act("sim", "simulate-result")}><FlaskConical />Simulate result</Button>
                )}
                {o.status === "resulted" && can("orders:sign") && <>
                  <Button size="sm" loading={busy === "rev"} onClick={() => act("rev", "review")}><CheckCircle2 />Mark reviewed</Button>
                  <Button size="sm" variant="outline" loading={busy === "revrel"} onClick={() => act("revrel", "review", undefined, "?release_to_patient=true")}>Review & release to patient</Button>
                </>}
                {o.status === "completed" && o.results_reviewed_at && !o.released_to_patient_at && can("orders:sign") && <Button size="sm" variant="outline" loading={busy === "rel"} onClick={() => act("rel", "release")}>Release to patient</Button>}
                {o.order_type === "referral" && o.status === "transmitted" && <Button size="sm" variant="outline" onClick={async () => { const n = await confirm({ title: "Mark referral scheduled?", requireReason: true, reasonLabel: "Note (e.g. appointment date with specialist)", confirmLabel: "Mark scheduled" }); if (n) act("rs", "referral-status", { status: "in_progress", note: n }); }}><Stethoscope />Mark scheduled</Button>}
                {o.order_type === "referral" && ["transmitted", "in_progress"].includes(o.status) && <Button size="sm" variant="outline" onClick={async () => { const n = await confirm({ title: "Mark referral completed?", requireReason: true, reasonLabel: "Outcome note", confirmLabel: "Complete" }); if (n) act("rc", "referral-status", { status: "completed", note: n }); }}><CheckCircle2 />Complete</Button>}
                {!["resulted", "completed", "cancelled"].includes(o.status) && (o.status === "draft" || can("orders:sign")) && (
                  <Button size="sm" variant="ghost" className="ml-auto text-destructive" onClick={async () => { const r = await confirm({ title: `Cancel ${o.title}?`, requireReason: true, destructive: true, confirmLabel: "Cancel order" }); if (r) act("cancel", "cancel", { reason: r }); }}><Ban />Cancel</Button>
                )}
              </div>
            </div>
          )}
        </SheetContent>
      </Dialog>
      <SignOrderDialog order={signing} onOpenChange={(v) => !v && setSigning(null)} onSigned={() => refresh()} />
    </>
  );
}
