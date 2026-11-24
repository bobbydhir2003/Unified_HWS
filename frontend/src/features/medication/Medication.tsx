/**
 * Closed-loop medication UI: eMAR (patient chart › MAR) and the pharmacist medication queue (Pharmacy › Medication orders).
 * Every rule is enforced by the server; the screens show the state and the server's reason when something is blocked.
 * Barcode scanning is simulated (labelled), interaction screening is shown as unavailable (never "safe").
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Barcode, CheckCircle2, Clock, Hand, Pause, Pill, Play, ScanLine, ShieldCheck, Square, XCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState, LoadingRows, toastError } from "@/components/common";
import { DataTable } from "@/components/common/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/tabs";
import { ApiError, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import { cn, titleCase } from "@/lib/utils";

type Verification = { status: string; note: string | null; at: string; pharmacist: string | null; manual_interaction_review: boolean } | null;
export type MedOrder = {
  id: string; patient_id: string; title: string; status: string; priority: string; setting: string | null; name: string | null; dose: string; route: string | null;
  frequency: string | null; frequency_label: string | null; prn_interval_hours: number | null; prn_reason: string | null; sig: string | null; high_alert: boolean;
  signed_at: string | null; prescriber: string | null; safety_warnings: { type: string; severity: string; message: string }[]; override_reason: string | null;
  notes: string | null; status_reason: string | null; verification: Verification;
};
type Slot = { at: string; state: "scheduled" | "due" | "overdue" | "given" | "held" | "refused" | "omitted"; administration_id: string | null };
type Admin = { id: string; scheduled_for: string | null; status: string; dose: string | null; route: string | null; reason: string | null; late: boolean;
  administered_at: string; administered_by: string | null; scan: Record<string, unknown>; requires_witness: boolean; witness: { name: string; at: string } | null };
type MarRow = MedOrder & { slots: Slot[]; administrations: Admin[]; awaiting_witness: string[]; verified_at: string | null };
type Mar = { patient: { id: string; name: string; mrn: string; wristband: string }; window: { start: string; end: string; now: string }; orders: MarRow[] };

const STATE_STYLE: Record<string, { cls: string; icon: React.ElementType; label: string }> = {
  scheduled: { cls: "border-border bg-card text-muted-foreground", icon: Clock, label: "Scheduled" },
  due: { cls: "border-primary/40 bg-accent text-accent-foreground", icon: Clock, label: "Due now" },
  overdue: { cls: "border-warning/50 bg-warning-soft text-warning-foreground", icon: AlertTriangle, label: "Overdue" },
  given: { cls: "border-success/40 bg-success-soft text-success", icon: CheckCircle2, label: "Given" },
  held: { cls: "border-border bg-muted text-muted-foreground", icon: Pause, label: "Held" },
  refused: { cls: "border-border bg-muted text-muted-foreground", icon: Hand, label: "Refused" },
  omitted: { cls: "border-border bg-muted text-muted-foreground", icon: XCircle, label: "Omitted" },
};

export const MED_STATUS: Record<string, { label: string; variant: React.ComponentProps<typeof Badge>["variant"] }> = {
  pending_verification: { label: "Awaiting pharmacist", variant: "warning" }, clarification_needed: { label: "Pharmacist query", variant: "warning" },
  rejected: { label: "Rejected", variant: "danger" }, active: { label: "Active · verified", variant: "success" }, on_hold: { label: "On hold", variant: "neutral" },
  discontinued: { label: "Discontinued", variant: "neutral" }, completed: { label: "Completed", variant: "success" },
};

const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const day = (iso: string) => new Date(iso).toLocaleDateString([], { weekday: "short", day: "numeric" });

function errMessage(e: unknown) {
  return e instanceof ApiError ? e.message : "Something went wrong";
}

// ---------------------------------------------------------------------------------------------- eMAR

export function PatientMarTab({ patientId }: { patientId: string }) {
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["mar", patientId], queryFn: () => get<Mar>(`/mar/patients/${patientId}`), refetchInterval: 60_000 });
  const [give, setGive] = React.useState<{ row: MarRow; slot: Slot | null } | null>(null);
  const [action, setAction] = React.useState<{ row: MarRow; kind: "hold" | "discontinue" | "resubmit" } | null>(null);
  const qc = useQueryClient();
  const refresh = () => { qc.invalidateQueries({ queryKey: ["mar", patientId] }); qc.invalidateQueries({ queryKey: ["medications"] }); };

  if (q.isError) return <ErrorState error={q.error} retry={q.refetch} />;
  if (q.isLoading || !q.data) return <LoadingRows />;
  const m = q.data;
  const witness = async (aid: string) => {
    try { await post(`/mar/administrations/${aid}/witness`); toast.success("Witness recorded"); refresh(); } catch (e) { toastError(e); }
  };
  const resume = async (row: MarRow) => {
    try { await post(`/orders/${row.id}/hold`, { hold: false }); toast.success("Order resumed"); refresh(); } catch (e) { toastError(e); }
  };
  return (
    <div className="space-y-3" data-testid="mar">
      <div className="flex flex-wrap items-center gap-2 text-label">
        <span className="text-section font-semibold text-heading">Medication administration record</span>
        <Badge variant="neutral"><ScanLine />Barcode scanning: simulated</Badge>
        <Badge variant="warning"><AlertTriangle />Interaction screening: not available</Badge>
        <span className="ml-auto text-muted-foreground">{day(m.window.start)} {time(m.window.start)} – {day(m.window.end)} {time(m.window.end)} · wristband <code className="font-mono">{m.patient.wristband}</code></span>
      </div>
      {!m.orders.length ? <Card><EmptyState icon={Pill} title="No inpatient medication orders" description="Signed inpatient medication orders appear here after pharmacist verification." /></Card> : (
        <Card className="divide-y overflow-hidden">
          {m.orders.map((row) => {
            const st = MED_STATUS[row.status] ?? { label: titleCase(row.status), variant: "neutral" as const };
            const prn = row.frequency === "prn";
            const administrable = row.status === "active";
            return (
              <div key={row.id} className="grid gap-3 px-4 py-3 lg:grid-cols-[minmax(0,18rem)_minmax(0,1fr)_auto]" data-testid="mar-row">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-1.5 text-body font-semibold text-heading">{row.name ?? row.title}
                    {row.high_alert && <Badge variant="danger"><AlertTriangle />High alert</Badge>}</p>
                  <p className="text-table text-foreground">{row.dose} · {row.route ?? "route?"} · {row.frequency_label ?? "no schedule"}{prn && row.prn_interval_hours ? ` (min ${row.prn_interval_hours} h)` : ""}</p>
                  <p className="mt-1 flex flex-wrap items-center gap-1.5 text-label text-muted-foreground">
                    <Badge variant={st.variant}>{st.label}</Badge>
                    {row.verification && <span>{row.verification.status === "verified" ? "Verified" : titleCase(row.verification.status)} by {row.verification.pharmacist} {fmtDateTime(row.verification.at)}</span>}
                  </p>
                  {row.status_reason && ["on_hold", "discontinued", "rejected"].includes(row.status) && <p className="mt-1 text-label text-muted-foreground">Reason: {row.status_reason}</p>}
                  {row.verification?.note && row.status !== "active" && <p className="mt-1 text-label text-warning-foreground">Pharmacist: {row.verification.note}</p>}
                </div>
                <div className="min-w-0">
                  {row.status === "pending_verification" || row.status === "clarification_needed" ? (
                    <p className="flex items-center gap-2 rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-table text-warning-foreground"><Square className="size-4" />Not administrable — waiting for pharmacist verification.</p>
                  ) : prn ? (
                    <p className="text-table text-muted-foreground">As needed{row.prn_reason ? ` for ${row.prn_reason}` : ""}. {row.administrations.filter((a) => a.status === "given").length} dose(s) given in this window.</p>
                  ) : !row.slots.length ? (
                    <p className="text-table text-muted-foreground">{row.frequency ? "No doses in this window." : "This order has no schedule (it predates the eMAR) — the prescriber should re-order with a frequency."}</p>
                  ) : (
                    <ol className="flex flex-wrap gap-1.5" aria-label="Scheduled doses">
                      {row.slots.map((s) => {
                        const sty = STATE_STYLE[s.state];
                        const open = !s.administration_id && administrable && can("nursing:write");
                        return (
                          <li key={s.at}>
                            <button type="button" disabled={!open} onClick={() => setGive({ row, slot: s })} title={sty.label}
                              className={cn("inline-flex h-8 items-center gap-1 rounded-md border px-2 text-label font-medium tabular", sty.cls, open ? "hover:ring-2 hover:ring-ring/30" : "cursor-default")}
                              aria-label={`${sty.label} dose ${day(s.at)} ${time(s.at)}`}>
                              <sty.icon className="size-3.5" aria-hidden />{time(s.at)}
                            </button>
                          </li>
                        );
                      })}
                    </ol>
                  )}
                  {!!row.administrations.length && (
                    <ul className="mt-2 space-y-0.5 text-label text-muted-foreground">
                      {row.administrations.slice(-4).map((a) => (
                        <li key={a.id} className="flex flex-wrap items-center gap-1.5">
                          <span className="font-medium text-foreground">{titleCase(a.status)}</span>{a.dose && <span>{a.dose} {a.route}</span>}
                          <span>· {fmtDateTime(a.administered_at)} by {a.administered_by}</span>{a.late && <Badge variant="warning">Late</Badge>}
                          {a.reason && <span>· {a.reason}</span>}
                          {a.requires_witness && (a.witness ? <Badge variant="success"><ShieldCheck />Witnessed by {a.witness.name}</Badge>
                            : <Button size="xs" variant="outline" onClick={() => witness(a.id)}>Witness (second nurse)</Button>)}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="flex flex-wrap items-start gap-1.5 lg:justify-end">
                  {prn && administrable && can("nursing:write") && <Button size="sm" onClick={() => setGive({ row, slot: null })}><Barcode />Give PRN dose</Button>}
                  {can("orders:sign") && row.status === "active" && <Button size="sm" variant="outline" onClick={() => setAction({ row, kind: "hold" })}><Pause />Hold</Button>}
                  {can("orders:sign") && row.status === "on_hold" && <Button size="sm" variant="outline" onClick={() => resume(row)}><Play />Resume</Button>}
                  {can("orders:sign") && row.status === "clarification_needed" && <Button size="sm" variant="outline" onClick={() => setAction({ row, kind: "resubmit" })}>Answer query</Button>}
                  {can("orders:sign") && ["active", "on_hold", "pending_verification", "clarification_needed"].includes(row.status) &&
                    <Button size="sm" variant="ghost" onClick={() => setAction({ row, kind: "discontinue" })}>Discontinue</Button>}
                </div>
              </div>
            );
          })}
        </Card>
      )}
      {give && <AdministerDialog mar={m} row={give.row} slot={give.slot} onClose={() => setGive(null)} onDone={refresh} />}
      {action && <OrderActionDialog row={action.row} kind={action.kind} onClose={() => setAction(null)} onDone={refresh} />}
    </div>
  );
}

function AdministerDialog({ mar, row, slot, onClose, onDone }: { mar: Mar; row: MarRow; slot: Slot | null; onClose: () => void; onDone: () => void }) {
  const labels = useQuery({ queryKey: ["dose-labels", row.id], queryFn: () => get<{ barcode: string; item: string; lot: string; quantity: number; dispensed_at: string }[]>(`/mar/orders/${row.id}/dose-labels`) });
  const [status, setStatus] = React.useState<"given" | "held" | "refused" | "omitted">("given");
  const [pt, setPt] = React.useState("");
  const [med, setMed] = React.useState("");
  const [dose, setDose] = React.useState(row.dose);
  const [route, setRoute] = React.useState(row.route ?? "");
  const [site, setSite] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [blocked, setBlocked] = React.useState<string | null>(null);
  const submit = async () => {
    setBusy(true); setBlocked(null);
    try {
      await post("/mar/administrations", { order_id: row.id, status, scheduled_for: slot?.at ?? null, dose, route, site: site || null, reason: reason || null,
        patient_barcode: status === "given" ? pt : null, medication_barcode: status === "given" ? med : null });
      toast.success(status === "given" ? "Dose documented as given" : `Dose documented as ${status}`);
      onDone(); onClose();
    } catch (e) { setBlocked(errMessage(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>{row.name} {row.dose} · {row.route}</DialogTitle>
          <DialogDescription>{mar.patient.name} · MRN {mar.patient.mrn} · {slot ? `scheduled ${day(slot.at)} ${time(slot.at)}` : "PRN dose"}</DialogDescription>
        </DialogHeader>
        <Segmented label="Documentation" value={status} onChange={(v) => setStatus(v as typeof status)}
          options={[{ value: "given", label: "Given" }, { value: "held", label: "Held" }, { value: "refused", label: "Refused" }, { value: "omitted", label: "Omitted" }]} />
        {status === "given" && (
          <div className="space-y-3">
            <p className="flex items-center gap-2 text-label text-muted-foreground"><ScanLine className="size-3.5" />Simulated barcode scanning — the server checks patient, medication, dose and route.</p>
            <Field label="1 · Patient wristband" required>
              <div className="flex gap-2"><Input value={pt} onChange={(e) => setPt(e.target.value)} placeholder="Scan wristband" className="font-mono" aria-label="Patient wristband barcode" />
                <Button type="button" variant="outline" size="sm" onClick={() => setPt(mar.patient.wristband)}>Simulate scan</Button></div>
            </Field>
            <Field label="2 · Dose label" required hint={labels.data && !labels.data.length ? "No dose has been dispensed by the pharmacy for this order yet." : undefined}>
              <div className="flex gap-2"><Input value={med} onChange={(e) => setMed(e.target.value)} placeholder="Scan pharmacy label" className="font-mono" aria-label="Medication barcode" />
                {!!labels.data?.length && (
                  <NativeSelect className="w-auto" value="" onChange={(e) => e.target.value && setMed(e.target.value)} aria-label="Simulate scanning a dispensed label">
                    <option value="">Simulate scan…</option>
                    {labels.data.map((l) => <option key={l.barcode} value={l.barcode}>{l.item} · lot {l.lot} · ×{l.quantity}</option>)}
                  </NativeSelect>
                )}</div>
            </Field>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Dose"><Input value={dose} onChange={(e) => setDose(e.target.value)} /></Field>
              <Field label="Route"><Input value={route} onChange={(e) => setRoute(e.target.value)} /></Field>
              <Field label="Site"><Input value={site} onChange={(e) => setSite(e.target.value)} placeholder="optional" /></Field>
            </div>
            {row.high_alert && <p className="flex gap-2 text-table text-destructive"><AlertTriangle className="mt-0.5 size-4 shrink-0" />High-alert medication: a second nurse must witness this administration.</p>}
          </div>
        )}
        <Field label={status === "given" ? "Comment / reason if late" : "Reason"} required={status !== "given"}>
          <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        {blocked && <p role="alert" className="flex gap-2 rounded-lg border border-destructive/40 bg-destructive-soft p-3 text-table font-medium text-destructive" data-testid="mar-blocked"><XCircle className="mt-0.5 size-4 shrink-0" />{blocked}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={busy} disabled={status !== "given" && reason.trim().length < 3}>{status === "given" ? "Document as given" : `Document as ${status}`}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function OrderActionDialog({ row, kind, onClose, onDone }: { row: MedOrder; kind: "hold" | "discontinue" | "resubmit"; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const title = { hold: "Hold order", discontinue: "Discontinue order", resubmit: "Answer pharmacist query" }[kind];
  const submit = async () => {
    setBusy(true);
    try {
      if (kind === "hold") await post(`/orders/${row.id}/hold`, { hold: true, reason: note });
      else await post(`/orders/${row.id}/${kind}`, { note });
      toast.success(title); onDone(); onClose();
    } catch (e) { toastError(e); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="sm">
        <DialogHeader><DialogTitle>{title}</DialogTitle><DialogDescription>{row.title}{row.verification?.note && kind === "resubmit" ? ` — pharmacist asked: ${row.verification.note}` : ""}</DialogDescription></DialogHeader>
        <Field label={kind === "resubmit" ? "Your answer" : "Reason"} required><Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button variant={kind === "discontinue" ? "destructive" : "default"} onClick={submit} loading={busy} disabled={note.trim().length < 3}>{title}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------------------------- pharmacist queue

type QueueRow = MedOrder & { patient: { id: string; name: string; mrn: string }; waiting_minutes: number | null };

export function PharmacyMedicationQueue() {
  const [status, setStatus] = React.useState<"pending_verification" | "clarification_needed" | "active">("pending_verification");
  const q = useQuery({ queryKey: ["pharmacy", "med-queue", status], queryFn: () => get<QueueRow[]>("/pharmacy/medication-queue", { status }), refetchInterval: 60_000 });
  const [open, setOpen] = React.useState<QueueRow | null>(null);
  return (
    <Card className="overflow-hidden">
      <DataTable<QueueRow> label="Medication orders" rows={q.data} isLoading={q.isLoading} error={q.error} retry={q.refetch} rowKey={(r) => r.id}
        onRowClick={setOpen} selectedKey={open?.id} searchText={(r) => `${r.patient.name} ${r.patient.mrn} ${r.title} ${r.prescriber ?? ""}`}
        searchPlaceholder="Search patient, MRN, medication…" defaultSort={{ key: "waiting", dir: "desc" }}
        toolbar={<Segmented label="Queue" value={status} onChange={(v) => setStatus(v as typeof status)}
          options={[{ value: "pending_verification", label: "To verify" }, { value: "clarification_needed", label: "Queried" }, { value: "active", label: "Verified · to dispense" }]} />}
        empty={{ icon: CheckCircle2, title: status === "pending_verification" ? "No orders waiting for verification" : "Nothing here" }}
        columns={[
          { key: "patient", header: "Patient", sort: (r) => r.patient.name, cell: (r) => <><span className="font-medium text-heading">{r.patient.name}</span><span className="block font-mono text-label text-muted-foreground">{r.patient.mrn}</span></> },
          { key: "med", header: "Medication", sort: (r) => r.name ?? r.title, cell: (r) => <span className="flex flex-wrap items-center gap-1.5">{r.name} {r.dose}{r.high_alert && <Badge variant="danger">High alert</Badge>}</span> },
          { key: "sched", header: "Route · frequency", hideBelow: "md", cell: (r) => `${r.route ?? "—"} · ${r.frequency_label ?? "—"}` },
          { key: "prio", header: "Priority", sort: (r) => ({ stat: 0, urgent: 1, routine: 2 } as Record<string, number>)[r.priority] ?? 3, cell: (r) => r.priority === "routine" ? "Routine" : <Badge variant="danger">{r.priority.toUpperCase()}</Badge> },
          { key: "prescriber", header: "Prescriber", hideBelow: "lg", cell: (r) => r.prescriber ?? "—" },
          { key: "alerts", header: "Alerts", hideBelow: "md", cell: (r) => { const b = r.safety_warnings.filter((w) => w.severity !== "info"); return b.length ? <Badge variant="danger">{b.length} overridden</Badge> : <span className="text-muted-foreground">—</span>; } },
          { key: "waiting", header: "Waiting", align: "right", sort: (r) => r.waiting_minutes ?? 0, cell: (r) => r.waiting_minutes != null ? `${r.waiting_minutes} min` : "—" },
        ]} />
      {open && <VerifyDrawer row={open} onClose={() => setOpen(null)} />}
    </Card>
  );
}

function VerifyDrawer({ row, onClose }: { row: QueueRow; onClose: () => void }) {
  const qc = useQueryClient();
  const [note, setNote] = React.useState("");
  const [manual, setManual] = React.useState(false);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [dispOpen, setDispOpen] = React.useState(false);
  const screeningIncomplete = row.safety_warnings.some((w) => w.type === "screening_incomplete");
  const decide = async (decision: "verified" | "rejected" | "clarify") => {
    setBusy(decision);
    try {
      await post(`/orders/${row.id}/pharmacy-decision`, { decision, note: note || null, manual_interaction_review: manual });
      toast.success({ verified: "Order verified", rejected: "Order rejected", clarify: "Query sent to prescriber" }[decision]);
      qc.invalidateQueries({ queryKey: ["pharmacy"] }); qc.invalidateQueries({ queryKey: ["inventory", "report"] }); onClose();
    } catch (e) { toastError(e); } finally { setBusy(null); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full sm:max-w-lg">
        <div className="space-y-4 p-5">
          <div>
            <h2 className="text-lg font-semibold text-heading">{row.name} {row.dose}</h2>
            <p className="text-table text-muted-foreground">{row.patient.name} · MRN {row.patient.mrn} · ordered by {row.prescriber} {row.signed_at ? fmtDateTime(row.signed_at) : ""}</p>
          </div>
          <dl className="grid grid-cols-2 gap-3 rounded-lg border p-3 text-table">
            <div><dt className="text-label text-muted-foreground">Route</dt><dd>{row.route}</dd></div>
            <div><dt className="text-label text-muted-foreground">Frequency</dt><dd>{row.frequency_label ?? "—"}{row.prn_reason ? ` (${row.prn_reason})` : ""}</dd></div>
            <div className="col-span-2"><dt className="text-label text-muted-foreground">Directions</dt><dd>{row.sig}</dd></div>
            {row.notes && <div className="col-span-2"><dt className="text-label text-muted-foreground">Notes</dt><dd className="whitespace-pre-line">{row.notes}</dd></div>}
          </dl>
          {row.safety_warnings.map((w, i) => (
            <p key={i} className={cn("flex gap-2 rounded-lg border p-3 text-table", w.severity === "info" ? "border-warning/35 bg-warning-soft text-warning-foreground" : "border-destructive/40 bg-destructive-soft text-destructive")}>
              <AlertTriangle className="mt-0.5 size-4 shrink-0" /><span>{w.message}{w.severity !== "info" && row.override_reason ? ` — prescriber override: “${row.override_reason}”` : ""}</span>
            </p>
          ))}
          {row.status === "pending_verification" && <>
            {screeningIncomplete && (
              <label className="flex items-start gap-2 rounded-lg border p-3 text-table">
                <Checkbox checked={manual} onCheckedChange={(v) => setManual(v === true)} className="mt-0.5" />
                I reviewed this medication against the patient's active medications, allergies and conditions for interactions and contraindications manually.
              </label>
            )}
            <Field label="Note to prescriber (required to reject or query)"><Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => decide("verified")} loading={busy === "verified"} disabled={screeningIncomplete && !manual}><ShieldCheck />Verify</Button>
              <Button variant="outline" onClick={() => decide("clarify")} loading={busy === "clarify"} disabled={note.trim().length < 3}>Query prescriber</Button>
              <Button variant="destructive" onClick={() => decide("rejected")} loading={busy === "rejected"} disabled={note.trim().length < 3}>Reject</Button>
            </div>
          </>}
          {row.status === "active" && <Button onClick={() => setDispOpen(true)}><Pill />Dispense dose</Button>}
          {row.status === "clarification_needed" && <p className="text-table text-muted-foreground">Waiting for the prescriber to answer: {row.verification?.note}</p>}
        </div>
        {dispOpen && <DispenseDialog row={row} onClose={() => setDispOpen(false)} />}
      </SheetContent>
    </Dialog>
  );
}

type Item = { id: string; name: string; kind: string; strength: string | null };
type Lot = { lot_id: string; lot_number: string; location_id: string; location_name?: string; location?: string; quantity: number; expiry_date: string | null; expired?: boolean };

function DispenseDialog({ row, onClose }: { row: QueueRow; onClose: () => void }) {
  const qc = useQueryClient();
  const items = useQuery({ queryKey: ["inventory", "items"], queryFn: () => get<Item[]>("/inventory/items") });
  const base = (row.name ?? "").replace(/ IV$/, "").toLowerCase();
  const match = (items.data ?? []).filter((i) => i.kind === "medication" && i.name.toLowerCase().startsWith(base.split(" ")[0]));
  const [itemId, setItemId] = React.useState("");
  const detail = useQuery({ queryKey: ["inventory", "item", itemId], queryFn: () => get<{ lots: Lot[] }>(`/inventory/items/${itemId}`), enabled: !!itemId });
  const [lotKey, setLotKey] = React.useState("");
  const [qty, setQty] = React.useState("1");
  const [label, setLabel] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (!itemId && match.length) setItemId(match[0].id); }, [match, itemId]);
  const lots = (detail.data?.lots ?? []).filter((l) => !l.expired && l.quantity > 0);
  const lot = lots.find((l) => `${l.lot_id}:${l.location_id}` === lotKey);
  const go = async () => {
    if (!lot) return;
    setBusy(true);
    try {
      const r = await post<{ dose_label: string }>("/inventory/dispense", { lot_id: lot.lot_id, location_id: lot.location_id, quantity: Number(qty), patient_id: row.patient.id, order_id: row.id });
      setLabel(r.dose_label); qc.invalidateQueries({ queryKey: ["inventory"] }); toast.success("Dispensed");
    } catch (e) { toastError(e); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="sm">
        <DialogHeader><DialogTitle>Dispense · {row.name} {row.dose}</DialogTitle><DialogDescription>{row.patient.name} · MRN {row.patient.mrn}. Expired lots can't be dispensed.</DialogDescription></DialogHeader>
        {label ? (
          <div className="space-y-2 rounded-lg border p-4 text-center">
            <p className="text-label text-muted-foreground">Dose label (simulated barcode)</p>
            <p className="font-mono text-body font-semibold" data-testid="dose-label">{label}</p>
            <p className="text-label text-muted-foreground">The nurse scans this label on the MAR before giving the dose.</p>
          </div>
        ) : (<>
          <Field label="Stock item"><NativeSelect value={itemId} onChange={(e) => { setItemId(e.target.value); setLotKey(""); }}>
            <option value="">Select…</option>{(items.data ?? []).filter((i) => i.kind === "medication").map((i) => <option key={i.id} value={i.id}>{i.name} {i.strength ?? ""}</option>)}
          </NativeSelect></Field>
          <Field label="Lot / location"><NativeSelect value={lotKey} onChange={(e) => setLotKey(e.target.value)} disabled={!lots.length}>
            <option value="">{lots.length ? "Select…" : "No usable stock"}</option>
            {lots.map((l) => <option key={`${l.lot_id}:${l.location_id}`} value={`${l.lot_id}:${l.location_id}`}>{l.lot_number} · {l.location_name ?? l.location ?? "location"} · {l.quantity} on hand{l.expiry_date ? ` · exp ${l.expiry_date}` : ""}</option>)}
          </NativeSelect></Field>
          <Field label="Quantity (doses)"><Input inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value.replace(/\D/g, "").slice(0, 3))} /></Field>
        </>)}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{label ? "Done" : "Cancel"}</Button>
          {!label && <Button onClick={go} loading={busy} disabled={!lot || !Number(qty)}>Dispense</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
