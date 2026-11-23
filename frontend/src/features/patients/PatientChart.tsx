import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, CalendarPlus, ClipboardList, ClipboardPen, FileStack, Receipt, TestTube, FileText, HeartPulse, History, Lock, Pencil, Phone, Pill, Plus, Route, ShieldAlert,
  Sparkles, Stethoscope, StickyNote, Trash2, Users, Info,
} from "lucide-react";
import * as React from "react";
import { Link, NavLink, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { AppointmentStatusBadge, EmptyState, ErrorState, KeyValue, LoadingRows, SimulatedBadge, toastError, useConfirm } from "@/components/common";
import { FormDialog } from "@/components/common/FormDialog";
import { useCrumb } from "@/components/layout/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { Tooltip } from "@/components/ui/menu";
import { Avatar, Skeleton } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ChartAssistant } from "@/features/ai/ChartAssistant";
import { PatientBillingTab } from "@/features/billing/BillingPage";
import { PatientDocumentsTab } from "@/features/documents/DocumentReview";
import { PatientOrdersTab, PatientResultsTab } from "@/features/orders/OrdersPages";
import { AppointmentDialog } from "@/features/schedule/AppointmentDialog";
import { ApiError, del, get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, fmtDob, sexShort } from "@/lib/format";
import { JourneyTab } from "@/features/insights/InsightsPages";
import { CoveragePanel } from "@/features/insurance/InsuranceGuardian";
import type { Allergy, Appointment, Encounter, Insurance, Medication, Patient, Problem, Vitals } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";
import { AllergiesTab, HistoryTab, MedicationsTab, ProblemsTab, SEVERITY_VARIANT } from "./ClinicalLists";
import { EditPatientDialog } from "./PatientForm";
import { VitalsSummary, VitalsTab } from "./Vitals";

export type Summary = {
  clinical_access: boolean;
  upcoming_appointments: { id: string; start_at: string; provider: string; type: string | null; status: Appointment["status"] }[];
  allergies?: Allergy[];
  problems?: Problem[];
  medications?: Medication[];
  last_vitals?: Vitals | null;
  last_encounter?: Encounter | null;
};

export function usePatient(id: string) {
  return useQuery({ queryKey: ["patient", id], queryFn: () => get<Patient>(`/patients/${id}`), retry: false });
}

function BreakGlass({ patientId, onDone }: { patientId: string; onDone: () => void }) {
  const { can } = useAuth();
  const [reason, setReason] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  return (
    <Card className="mx-auto mt-10 max-w-lg border-warning/40">
      <CardContent className="space-y-4 pt-6">
        <div className="flex items-start gap-3">
          <span className="rounded-full bg-warning-soft p-2.5 text-warning"><Lock className="size-5" /></span>
          <div>
            <h2 className="text-base font-semibold">Restricted chart</h2>
            <p className="mt-1 text-table text-muted-foreground">
              This patient's record is restricted. Emergency ("break-the-glass") access is granted for 4 hours, is logged with your reason, and is reviewed by compliance.
            </p>
          </div>
        </div>
        {can("clinical:read") ? (
          <form className="space-y-3" onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try { const r = await post<{ message: string }>(`/patients/${patientId}/break-glass`, { reason }); toast.warning(r.message); onDone(); }
            catch (err) { toastError(err); } finally { setBusy(false); }
          }}>
            <Field label="Clinical reason for access" required hint="Minimum 10 characters.">
              <Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
            </Field>
            <div className="flex justify-end gap-2">
              <Button variant="outline" type="button" asChild><Link to="/patients">Cancel</Link></Button>
              <Button variant="destructive" type="submit" loading={busy} disabled={reason.trim().length < 10}><ShieldAlert />Break the glass</Button>
            </div>
          </form>
        ) : <p className="text-table text-muted-foreground">Contact the patient's care team for access.</p>}
      </CardContent>
    </Card>
  );
}

export function AllergyStrip({ summary }: { summary?: Summary }) {
  if (!summary) return <Skeleton className="h-6 w-40" />;
  if (!summary.clinical_access) return <span className="text-label text-muted-foreground">Allergies: clinical access required</span>;
  const list = summary.allergies ?? [];
  // Patient safety: an empty list is NOT a documented "no known allergies". Never show a negative finding nobody recorded.
  if (!list.length) {
    return (
      <Tooltip content="No allergy has been recorded for this patient. This is not a confirmed “no known allergies” — review with the patient.">
        <span className="inline-flex items-center gap-1 rounded-full border border-control bg-card px-2 py-0.5 text-label font-medium text-foreground" data-testid="allergy-none-recorded">
          <Info className="size-3 text-muted-foreground" aria-hidden />Allergies: none recorded
        </span>
      </Tooltip>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="Allergies">
      <span className="flex items-center gap-1 text-xs font-semibold text-destructive"><AlertTriangle className="size-3.5" />Allergies</span>
      {list.map((a) => (
        <Tooltip key={a.id} content={`${a.reaction ?? "Reaction not recorded"} · ${titleCase(a.severity)}`}>
          <Badge variant={SEVERITY_VARIANT[a.severity]} className={cn(a.severity === "life_threatening" && "ring-1 ring-destructive")}>{a.substance}</Badge>
        </Tooltip>
      ))}
    </div>
  );
}

function PatientBanner({ p, summary, onEdit, onBook, onStartVisit, onAsk, starting }: {
  p: Patient; summary?: Summary; onEdit: () => void; onBook: () => void; onStartVisit: () => void; onAsk: () => void; starting: boolean;
}) {
  const { can, membership } = useAuth();
  const ins = p.insurances.find((i) => i.is_active && i.priority === "primary");
  return (
    <Card className="sticky top-16 z-20 mb-4 overflow-hidden" data-testid="patient-banner">
      <div className="flex flex-col gap-3 px-4 py-3 lg:flex-row lg:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-3.5">
          <Avatar name={`${p.first_name} ${p.last_name}`} className="size-11 text-table" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              {/* Patient-banner convention: FAMILY name in capitals, then given name — reduces wrong-patient errors. */}
              <h1 className="text-metric font-semibold tracking-tight text-heading"><span className="uppercase">{p.last_name}</span>, {p.first_name} {p.middle_name?.[0] ? `${p.middle_name[0]}.` : ""}</h1>
              {p.preferred_name && <span className="text-table text-muted-foreground">“{p.preferred_name}”</span>}
              {p.status !== "active" && <Badge variant="danger">{titleCase(p.status)}</Badge>}
              {p.is_restricted && <Badge variant="warning"><Lock />Restricted</Badge>}
            </div>
            <p className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-table text-muted-foreground tabular">
              <span><strong className="font-medium text-foreground">{sexShort(p.sex_at_birth)}</strong> · DOB {fmtDob(p.date_of_birth)}</span>
              <span>MRN <span className="font-mono font-medium text-foreground">{p.mrn}</span></span>
              {p.phone && <span className="inline-flex items-center gap-1"><Phone className="size-3" />{p.phone}</span>}
              {p.pronouns && <span>{p.pronouns}</span>}
              {ins && <span>{ins.payer_name}</span>}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {can("ai:use") && can("clinical:read") && <Button variant="ai" size="sm" onClick={onAsk}><Sparkles />Ask AI about this chart</Button>}
          {can("patients:write") && <Button variant="outline" size="sm" onClick={onEdit}><Pencil />Edit</Button>}
          {can("schedule:write") && <Button variant="outline" size="sm" onClick={onBook} disabled={p.status !== "active"}><CalendarPlus />Book</Button>}
          {can("clinical:write") && membership?.provider_id && (
            <Button size="sm" onClick={onStartVisit} loading={starting} disabled={p.status !== "active"}><Stethoscope />Start visit</Button>
          )}
        </div>
      </div>
      <div className="border-t bg-subtle px-4 py-2"><AllergyStrip summary={summary} /></div>
    </Card>
  );
}

const TABS = [
  { key: "", label: "Overview", icon: ClipboardList },
  { key: "visits", label: "Visits", icon: Stethoscope, clinical: true },
  { key: "problems", label: "Problems", icon: FileText, clinical: true },
  { key: "medications", label: "Medications", icon: Pill, clinical: true },
  { key: "allergies", label: "Allergies", icon: AlertTriangle, clinical: true },
  { key: "history", label: "History", icon: Users, clinical: true },
  { key: "vitals", label: "Vitals", icon: HeartPulse, clinical: true },
  { key: "orders", label: "Orders", icon: ClipboardPen, clinical: true },
  { key: "results", label: "Results", icon: TestTube, clinical: true },
  { key: "timeline", label: "Timeline", icon: History, clinical: true },
  { key: "journey", label: "Journey", icon: Route },
  { key: "documents", label: "Documents", icon: FileStack, docs: true },
  { key: "appointments", label: "Appointments", icon: CalendarPlus },
  { key: "billing", label: "Billing", icon: Receipt, billing: true },
  { key: "demographics", label: "Demographics", icon: Users },
  { key: "notes", label: "Front-desk notes", icon: StickyNote },
];

/** Six top-level groups (sections keep their own URLs, so deep links still work). */
const GROUPS: { label: string; icon: React.ElementType; keys: string[] }[] = [
  { label: "Overview", icon: ClipboardList, keys: [""] },
  { label: "Clinical", icon: HeartPulse, keys: ["problems", "medications", "allergies", "history", "vitals"] },
  { label: "Visits", icon: Stethoscope, keys: ["visits", "appointments"] },
  { label: "Orders & results", icon: ClipboardPen, keys: ["orders", "results"] },
  { label: "Care journey", icon: Route, keys: ["journey", "timeline"] },
  { label: "Documents & details", icon: FileStack, keys: ["documents", "demographics", "notes", "billing"] },
];

export function PatientChart() {
  const { patientId = "", "*": tab = "" } = useParams();
  const { can } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const pq = usePatient(patientId);
  const summary = useQuery({ queryKey: ["summary", patientId], queryFn: () => get<Summary>(`/patients/${patientId}/summary`), enabled: !!pq.data });
  const [editOpen, setEditOpen] = React.useState(false);
  const [bookOpen, setBookOpen] = React.useState(false);
  const [starting, setStarting] = React.useState(false);
  const [askOpen, setAskOpen] = React.useState(false);
  useCrumb(pq.data ? `${pq.data.first_name} ${pq.data.last_name}` : null);

  if (pq.error instanceof ApiError && pq.error.code === "restricted_chart") {
    return <BreakGlass patientId={patientId} onDone={() => qc.invalidateQueries({ queryKey: ["patient", patientId] })} />;
  }
  if (pq.error) return <ErrorState error={pq.error} retry={pq.refetch} />;
  if (!pq.data) return <div className="space-y-4"><Skeleton className="h-28 rounded-xl" /><Skeleton className="h-9 w-2/3" /><LoadingRows /></div>;
  const p = pq.data;
  const clinical = can("clinical:read");
  const tabs = TABS.filter((t) => (!t.clinical || clinical) && (!("docs" in t) || can("documents:read")) && (!("billing" in t) || can("billing:read")));

  const startVisit = async () => {
    setStarting(true);
    try {
      // Prefer today's arrived appointment so the encounter links to it.
      const appts = await get<Appointment[]>(`/patients/${p.id}/appointments`);
      const today = new Date().toDateString();
      const appt = appts.find((a) => new Date(a.start_at).toDateString() === today && ["checked_in", "roomed", "confirmed", "scheduled", "in_progress"].includes(a.status));
      if (appt?.encounter_id) { navigate(`/encounters/${appt.encounter_id}`); return; }
      const enc = await post<{ id: string }>("/encounters", { patient_id: p.id, appointment_id: appt?.id ?? null, clinic_id: p.primary_clinic_id });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      navigate(`/encounters/${enc.id}`);
    } catch (e) { toastError(e); } finally { setStarting(false); }
  };

  return (
    <>
      <PatientBanner p={p} summary={summary.data} onEdit={() => setEditOpen(true)} onBook={() => setBookOpen(true)} onStartVisit={startVisit} onAsk={() => setAskOpen(true)} starting={starting} />
      {(() => {
        const visible = new Set(tabs.map((t) => t.key));
        const groups = GROUPS.map((g) => ({ ...g, keys: g.keys.filter((k) => visible.has(k)) })).filter((g) => g.keys.length);
        const current = groups.find((g) => g.keys.includes(tab)) ?? groups[0];
        const url = (k: string) => `/patients/${p.id}${k ? `/${k}` : ""}`;
        return (
          <div className="mb-5 space-y-3">
            <nav className="flex max-w-full items-end gap-6 overflow-x-auto border-b scrollbar-thin" aria-label="Chart sections">
              {groups.map((g) => {
                const active = g === current;
                return (
                  <NavLink key={g.label} to={url(g.keys[0])} end aria-current={active ? "page" : undefined}
                    className={cn("-mb-px flex shrink-0 items-center gap-1.5 border-b-2 border-transparent px-0.5 pb-2.5 pt-1.5 text-body font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
                      active && "border-primary font-semibold text-heading")}>
                    <g.icon className="size-4" />{g.label}
                  </NavLink>
                );
              })}
            </nav>
            {current.keys.length > 1 && (
              <nav className="inline-flex max-w-full flex-wrap overflow-hidden rounded-md border border-control bg-card" aria-label={`${current.label} sections`}>
                {current.keys.map((k) => {
                  const t = tabs.find((x) => x.key === k)!;
                  return (
                    <NavLink key={k} to={url(k)} end className={({ isActive }) => cn("inline-flex h-8 items-center gap-1.5 border-r border-control px-3 text-table font-medium text-muted-foreground last:border-r-0 hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50",
                      isActive && "bg-accent font-semibold text-accent-foreground hover:bg-accent hover:text-accent-foreground")}>
                      <t.icon className="size-3.5" />{t.label}
                    </NavLink>
                  );
                })}
              </nav>
            )}
          </div>
        );
      })()}
      <div className="animate-in">
        {tab === "" && <Overview p={p} summary={summary.data} />}
        {tab === "visits" && clinical && <VisitsTab patientId={p.id} />}
        {tab === "problems" && clinical && <ProblemsTab patientId={p.id} />}
        {tab === "medications" && clinical && <MedicationsTab patientId={p.id} />}
        {tab === "allergies" && clinical && <AllergiesTab patientId={p.id} />}
        {tab === "history" && clinical && <HistoryTab patientId={p.id} />}
        {tab === "vitals" && clinical && <VitalsTab patientId={p.id} />}
        {tab === "orders" && clinical && <PatientOrdersTab patientId={p.id} />}
        {tab === "results" && clinical && <PatientResultsTab patientId={p.id} />}
        {tab === "timeline" && clinical && <TimelineTab patientId={p.id} />}
        {tab === "journey" && <JourneyTab patientId={p.id} />}
        {tab === "documents" && can("documents:read") && <PatientDocumentsTab patientId={p.id} />}
        {tab === "appointments" && <AppointmentsTab patientId={p.id} />}
        {tab === "billing" && can("billing:read") && <PatientBillingTab patientId={p.id} />}
        {tab === "demographics" && <DemographicsTab p={p} />}
        {tab === "notes" && <AdminNotesTab patientId={p.id} />}
      </div>
      <EditPatientDialog patient={p} open={editOpen} onOpenChange={setEditOpen} />
      <ChartAssistant patientId={p.id} patientName={`${p.first_name} ${p.last_name}`} open={askOpen} onOpenChange={setAskOpen} />
      <AppointmentDialog open={bookOpen} onOpenChange={setBookOpen} patient={{ id: p.id, name: `${p.first_name} ${p.last_name}`, mrn: p.mrn, date_of_birth: p.date_of_birth }} />
    </>
  );
}

function Section({ title, to, children, className, sub, link = "View all" }: { title: string; to?: string; children: React.ReactNode; className?: string; sub?: string; link?: string }) {
  return (
    <Card className={className}>
      <CardHeader className="items-center pb-2">
        <div><CardTitle>{title}</CardTitle>{sub && <p className="text-label text-muted-foreground">{sub}</p>}</div>
        {to && <Link to={to} className="text-table font-medium text-primary hover:underline">{link}</Link>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function Overview({ p, summary }: { p: Patient; summary?: Summary }) {
  if (!summary) return <LoadingRows />;
  const base = `/patients/${p.id}`;
  const none = (t: string) => <p className="text-table text-muted-foreground">{t}</p>;
  return (
    <div className="space-y-4">
      {summary.clinical_access && (
        <Section title="Latest vitals" to={`${base}/vitals`} sub={summary.last_vitals ? `Measured ${fmtDateTime(summary.last_vitals.measured_at)}` : undefined} link="Trends">
          {summary.last_vitals ? <VitalsSummary v={summary.last_vitals} /> : none("No vitals recorded.")}
        </Section>
      )}
      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {summary.clinical_access ? (
            <Section title="Problems and medications" to={`${base}/problems`} link="Clinical">
              <dl className="divide-y text-table">
                <div className="grid gap-1 py-2 first:pt-0 sm:grid-cols-[8rem_1fr]">
                  <dt className="text-label font-medium text-muted-foreground">Active problems</dt>
                  <dd>{summary.problems?.length ? <ul className="space-y-1">{summary.problems.map((x) => (
                    <li key={x.id} className="flex items-start justify-between gap-2"><span className="font-medium text-heading">{x.description}</span><span className="font-mono text-label text-muted-foreground">{x.code}</span></li>
                  ))}</ul> : none("None recorded.")}</dd>
                </div>
                <div className="grid gap-1 py-2 sm:grid-cols-[8rem_1fr]">
                  <dt className="text-label font-medium text-muted-foreground">Medications</dt>
                  <dd>{summary.medications?.length ? <ul className="space-y-1">{summary.medications.map((m) => (
                    <li key={m.id}><span className="font-medium text-heading">{m.name}</span> <span className="text-muted-foreground">{[m.dose, m.frequency].filter(Boolean).join(" · ")}</span></li>
                  ))}</ul> : none("None recorded.")}</dd>
                </div>
                <div className="grid gap-1 pt-2 sm:grid-cols-[8rem_1fr]">
                  <dt className="text-label font-medium text-muted-foreground">Allergies</dt>
                  <dd><AllergyStrip summary={summary} /></dd>
                </div>
              </dl>
            </Section>
          ) : (
            <Card><EmptyState icon={Lock} title="Clinical details hidden" description="Your role can view demographics and scheduling only." /></Card>
          )}
        </div>
        <div className="space-y-4">
          {summary.clinical_access && (
            <Section title="Last visit" to={`${base}/visits`} link="All visits">
              {summary.last_encounter ? (
                <Link to={`/encounters/${summary.last_encounter.id}`} className="-m-1 block rounded-md p-1 hover:bg-muted/60">
                  <p className="font-medium text-heading">{summary.last_encounter.chief_complaint ?? titleCase(summary.last_encounter.encounter_type)}</p>
                  <p className="text-label text-muted-foreground">{fmtDate(summary.last_encounter.started_at)} · {summary.last_encounter.provider.name}</p>
                  <div className="mt-2 flex flex-wrap gap-1">{summary.last_encounter.diagnoses.map((d) => <Badge key={d.id} variant="outline">{d.code}</Badge>)}</div>
                </Link>
              ) : none("No visits yet.")}
            </Section>
          )}
          <Section title="Upcoming appointments" to={`${base}/appointments`}>
            {summary.upcoming_appointments.length ? (
              <ul className="divide-y">{summary.upcoming_appointments.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-2 py-2 text-table first:pt-0 last:pb-0">
                  <span><span className="font-medium text-heading">{fmtDateTime(a.start_at)}</span><span className="block text-label text-muted-foreground">{[a.type, a.provider].filter(Boolean).join(" · ")}</span></span>
                  <AppointmentStatusBadge status={a.status} />
                </li>
              ))}</ul>
            ) : none("Nothing scheduled.")}
          </Section>
        </div>
      </div>
    </div>
  );
}

function VisitsTab({ patientId }: { patientId: string }) {
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["encounters", patientId], queryFn: () => get<Encounter[]>(`/patients/${patientId}/encounters`) });
  return (
    <Card className="overflow-hidden">
      {q.error ? <ErrorState error={q.error} /> : q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState icon={Stethoscope} title="No visits yet" /> : (
        <Table>
          <THead><TR><TH>Date</TH><TH>Visit</TH><TH>Provider</TH><TH>Diagnoses</TH><TH>Note</TH></TR></THead>
          <TBody>
            {q.data.map((e) => (
              <TR key={e.id} data-clickable tabIndex={0} onClick={() => navigate(`/encounters/${e.id}`)} onKeyDown={(ev) => ev.key === "Enter" && navigate(`/encounters/${e.id}`)}>
                <TD className="whitespace-nowrap tabular">{fmtDate(e.started_at)}</TD>
                <TD><span className="font-medium">{e.chief_complaint ?? titleCase(e.encounter_type)}</span><span className="block text-xs text-muted-foreground">{titleCase(e.encounter_type)}</span></TD>
                <TD>{e.provider.name}</TD>
                <TD><div className="flex flex-wrap gap-1">{e.diagnoses.map((d) => <Tooltip key={d.id} content={d.description}><Badge variant="outline">{d.code}</Badge></Tooltip>)}</div></TD>
                <TD>
                  {e.status === "in_progress" ? <Badge variant="primary">In progress</Badge>
                    : e.note_status === "signed" ? <Badge variant="success">Signed</Badge> : <Badge variant="warning">{e.note_status ? "Unsigned" : "No note"}</Badge>}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </Card>
  );
}

type TimelineItem = { type: string; id: string; at: string; title: string; detail: string | null; status?: string; by?: string; encounter_id?: string };
const TL_ICON: Record<string, typeof Stethoscope> = { document: FileStack, encounter: Stethoscope, note: FileText, vitals: HeartPulse, appointment: CalendarPlus, problem: ClipboardList, allergy: AlertTriangle };

function TimelineTab({ patientId }: { patientId: string }) {
  const [filter, setFilter] = React.useState<string>("all");
  const q = useQuery({ queryKey: ["timeline", patientId], queryFn: () => get<TimelineItem[]>(`/patients/${patientId}/timeline`) });
  const items = (q.data ?? []).filter((i) => filter === "all" || i.type === filter);
  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-1.5">
        {["all", "encounter", "note", "vitals", "document", "appointment", "problem", "allergy"].map((f) => (
          <Button key={f} size="xs" variant={filter === f ? "default" : "outline"} onClick={() => setFilter(f)}>{f === "all" ? "All" : titleCase(f)}</Button>
        ))}
      </div>
      {q.error ? <ErrorState error={q.error} /> : q.isLoading ? <LoadingRows /> : !items.length ? <EmptyState title="Nothing here yet" /> : (
        <ol className="relative ml-3 border-l pl-6">
          {items.map((i) => {
            const Icon = TL_ICON[i.type] ?? FileText;
            const href = i.type === "document" ? `/documents/${i.id}` : i.type === "encounter" ? `/encounters/${i.id}` : i.type === "note" && i.encounter_id ? `/encounters/${i.encounter_id}` : null;
            const body = (
              <>
                <p className="text-body font-medium">{i.title}{i.status && <span className="ml-2 text-xs font-normal text-muted-foreground">{titleCase(i.status)}</span>}</p>
                {i.detail && <p className="text-table text-muted-foreground">{i.detail}</p>}
                <p className="mt-0.5 text-xs text-muted-foreground">{fmtDateTime(i.at)}{i.by ? ` · ${i.by}` : ""}</p>
              </>
            );
            return (
              <li key={`${i.type}-${i.id}`} className="relative pb-5">
                <span className="absolute -left-[37px] top-0 grid size-6 place-items-center rounded-full border bg-card text-muted-foreground"><Icon className="size-3.5" /></span>
                {href ? <Link to={href} className="block rounded-md hover:bg-muted/40">{body}</Link> : body}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

function AppointmentsTab({ patientId }: { patientId: string }) {
  const q = useQuery({ queryKey: ["patient-appts", patientId], queryFn: () => get<Appointment[]>(`/patients/${patientId}/appointments`) });
  return (
    <Card className="overflow-hidden">
      {q.error ? <ErrorState error={q.error} /> : q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState title="No appointments" /> : (
        <Table>
          <THead><TR><TH>When</TH><TH>Type</TH><TH>Provider</TH><TH className="hidden md:table-cell">Location</TH><TH>Status</TH></TR></THead>
          <TBody>
            {q.data.map((a) => (
              <TR key={a.id}>
                <TD className="whitespace-nowrap tabular">{fmtDateTime(a.start_at)}</TD>
                <TD>{a.appointment_type?.name ?? "—"}<span className="block text-xs text-muted-foreground">{a.reason}</span></TD>
                <TD>{a.provider.name}</TD>
                <TD className="hidden md:table-cell">{a.clinic.name}</TD>
                <TD><AppointmentStatusBadge status={a.status} />{a.cancel_reason && <span className="block text-xs text-muted-foreground">{a.cancel_reason}</span>}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </Card>
  );
}

const ELIG = { active: "success", inactive: "danger", unverified: "neutral" } as const;

function DemographicsTab({ p }: { p: Patient }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [insEdit, setInsEdit] = React.useState<Insurance | "new" | null>(null);
  const [checking, setChecking] = React.useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["patient", p.id] });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader><CardTitle>Demographics</CardTitle></CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-4">
            <KeyValue label="Legal name" value={[p.first_name, p.middle_name, p.last_name].filter(Boolean).join(" ")} />
            <KeyValue label="Preferred name" value={p.preferred_name} />
            <KeyValue label="Date of birth" value={fmtDob(p.date_of_birth)} />
            <KeyValue label="Sex at birth" value={titleCase(p.sex_at_birth)} />
            <KeyValue label="Gender identity" value={p.gender_identity} />
            <KeyValue label="Pronouns" value={p.pronouns} />
            <KeyValue label="Language" value={p.preferred_language} />
            <KeyValue label="Portal access" value={p.has_portal_access ? "Enabled" : "Not enrolled"} />
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Contact</CardTitle></CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-4">
            <KeyValue label="Mobile" value={p.phone} />
            <KeyValue label="Alternate" value={p.phone_alt} />
            <KeyValue label="Email" value={p.email} className="col-span-2" />
            <KeyValue label="Address" value={[p.address_line1, p.address_line2, [p.city, p.state].filter(Boolean).join(", "), p.postal_code].filter(Boolean).join(" · ")} className="col-span-2" />
            <KeyValue label="Emergency contact" value={p.emergency_contact_name ? `${p.emergency_contact_name}${p.emergency_contact_relation ? ` (${p.emergency_contact_relation})` : ""}` : null} />
            <KeyValue label="Emergency phone" value={p.emergency_contact_phone} />
          </dl>
        </CardContent>
      </Card>
      <Card className="lg:col-span-2">
        <CardHeader>
          <div><CardTitle>Insurance</CardTitle></div>
          {can("patients:write") && <Button size="sm" variant="outline" onClick={() => setInsEdit("new")}><Plus />Add coverage</Button>}
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          {!p.insurances.length && <p className="text-table text-muted-foreground">Self-pay — no coverage on file.</p>}
          {p.insurances.map((i) => (
            <div key={i.id} className={cn("rounded-lg border p-3.5", !i.is_active && "opacity-60")}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-medium">{i.payer_name}</p>
                  <p className="text-xs text-muted-foreground">{titleCase(i.priority)}{i.plan_name ? ` · ${i.plan_name}` : ""}</p>
                </div>
                <Badge variant={ELIG[i.eligibility_status as keyof typeof ELIG] ?? "neutral"}>{titleCase(i.eligibility_status)}</Badge>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-2 text-table">
                <KeyValue label="Member ID" value={<span className="font-mono">{i.member_id}</span>} />
                <KeyValue label="Group" value={i.group_number} />
                <KeyValue label="Subscriber" value={i.subscriber_name ? `${i.subscriber_name} (${i.subscriber_relation})` : i.subscriber_relation} />
                <KeyValue label="Last verified" value={i.eligibility_checked_at ? fmtDateTime(i.eligibility_checked_at) : "Never"} />
              </dl>
              {can("patients:write") && (
                <div className="mt-3 flex items-center gap-2">
                  <Button size="xs" variant="outline" loading={checking === i.id} onClick={async () => {
                    setChecking(i.id);
                    try { const r = await post<Insurance>(`/patients/${p.id}/insurances/${i.id}/eligibility`); toast.info(`Eligibility: ${r.eligibility_status} (simulated)`); refresh(); }
                    catch (e) { toastError(e); } finally { setChecking(null); }
                  }}>Check eligibility</Button>
                  <SimulatedBadge />
                  <Button size="xs" variant="ghost" className="ml-auto" onClick={() => setInsEdit(i)}><Pencil />Edit</Button>
                </div>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
      {can("cases:read") && <div className="lg:col-span-2"><CoveragePanel patientId={p.id} /></div>}
      <FormDialog
        open={!!insEdit} onOpenChange={(o) => !o && setInsEdit(null)} title={insEdit === "new" ? "Add coverage" : "Edit coverage"}
        fields={[
          { name: "payer_name", label: "Payer", required: true },
          { name: "plan_name", label: "Plan", span: 1 },
          { name: "priority", label: "Priority", type: "select", options: [["primary", "Primary"], ["secondary", "Secondary"], ["tertiary", "Tertiary"]], span: 1 },
          { name: "member_id", label: "Member ID", required: true, span: 1 },
          { name: "group_number", label: "Group #", span: 1 },
          { name: "subscriber_name", label: "Subscriber name", span: 1 },
          { name: "subscriber_relation", label: "Relationship", type: "select", options: [["self", "Self"], ["spouse", "Spouse"], ["child", "Child"], ["other", "Other"]], span: 1 },
          { name: "effective_date", label: "Effective", type: "date", span: 1 },
          { name: "termination_date", label: "Terminates", type: "date", span: 1 },
          { name: "is_active", label: "Active coverage", type: "checkbox" },
        ]}
        initial={insEdit && insEdit !== "new" ? (insEdit as unknown as Record<string, string>) : { is_active: true }}
        onSubmit={async (v) => {
          if (insEdit === "new") await post(`/patients/${p.id}/insurances`, v);
          else if (insEdit) await put(`/patients/${p.id}/insurances/${insEdit.id}`, v);
          refresh();
          toast.success("Coverage saved");
        }}
      />
    </div>
  );
}

type AdminNote = { id: string; body: string; is_pinned: boolean; author_name: string | null; created_at: string };

function AdminNotesTab({ patientId }: { patientId: string }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const { confirm, dialog } = useConfirm();
  const [body, setBody] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const q = useQuery({ queryKey: ["admin-notes", patientId], queryFn: () => get<AdminNote[]>(`/patients/${patientId}/notes`) });
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
      {dialog}
      {can("patients:write") && (
        <Card>
          <CardHeader><CardTitle>Add note</CardTitle></CardHeader>
          <CardContent>
            <form className="space-y-3" onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try { await post(`/patients/${patientId}/notes`, { body }); setBody(""); qc.invalidateQueries({ queryKey: ["admin-notes", patientId] }); }
              catch (err) { toastError(err); } finally { setBusy(false); }
            }}>
              <Textarea rows={3} value={body} onChange={(e) => setBody(e.target.value)} placeholder="e.g. Prefers morning appointments; needs interpreter" aria-label="Note" />
              <p className="text-xs text-muted-foreground">Administrative only. Clinical information belongs in a visit note.</p>
              <Button type="submit" size="sm" loading={busy} disabled={!body.trim()}>Add note</Button>
            </form>
          </CardContent>
        </Card>
      )}
      <Card className="overflow-hidden">
        {q.isLoading ? <LoadingRows rows={3} /> : !q.data?.length ? <EmptyState icon={StickyNote} title="No front-desk notes" /> : (
          <ul className="divide-y">
            {q.data.map((n) => (
              <li key={n.id} className="flex gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="whitespace-pre-wrap text-body">{n.body}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{n.author_name ?? "Unknown"} · {fmtDateTime(n.created_at)}</p>
                </div>
                {can("patients:write") && (
                  <Button variant="ghost" size="icon-sm" aria-label="Delete note" onClick={async () => {
                    if (!(await confirm({ title: "Delete this note?", destructive: true, confirmLabel: "Delete" }))) return;
                    try { await del(`/patients/${patientId}/notes/${n.id}`); qc.invalidateQueries({ queryKey: ["admin-notes", patientId] }); } catch (e) { toastError(e); }
                  }}><Trash2 /></Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
