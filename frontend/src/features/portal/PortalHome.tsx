import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, CalendarPlus, CircleAlert, ClipboardCheck, CreditCard, FileHeart, FlaskConical, HeartPulse, Home, LogOut, Mail, MessageSquare, Pill, Send, ShieldCheck, UserRound, Video } from "lucide-react";
import * as React from "react";
import { Link, NavLink, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { PortalInsurance, usePortalInsurance } from "./PortalInsurance";
import { toast } from "sonner";
import { AppointmentStatusBadge, EmptyState, ErrorState, LoadingRows, toastError, useConfirm } from "@/components/common";
import { Notifications } from "@/components/layout/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/misc";
import { AccountPage } from "@/features/account/AccountPage";
import { flagClass, flagLabel } from "@/features/orders/shared";
import type { Summary } from "@/features/patients/PatientChart";
import { VideoVisit } from "@/features/telehealth/VideoVisit";
import { get, post } from "@/lib/api";
import { fmtMoney, newIdempotencyKey } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, fmtTime } from "@/lib/format";
import type { Appointment } from "@/lib/types";
import { addDays, minutesOfDay, todayIn, hhmm } from "@/lib/tz";
import { cn } from "@/lib/utils";

type PortalAppt = Appointment & { intake_submitted: boolean };
type HomeData = { patient: { id: string; first_name: string; last_name: string; date_of_birth: string; mrn: string }; upcoming: PortalAppt[]; has_recent_results: boolean };
type Thread = { id: string; subject: string; category: string; status: string; last_message_at: string; unread: number; messages: { id: string; body: string; created_at: string; from_patient: boolean; sender: string }[] };

const canJoinVideo = (a: Appointment) => a.mode === "telehealth" && !["cancelled", "no_show", "checked_out"].includes(a.status)
  && Date.now() >= new Date(a.start_at).getTime() - 30 * 60_000 && Date.now() <= new Date(a.end_at).getTime() + 60 * 60_000;

function Brand() {
  return (
    <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-blue-500 to-blue-700">
      <svg viewBox="0 0 32 32" className="size-5" aria-hidden><path d="M10 9v8a6 6 0 0 0 12 0V9" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" /><circle cx="16" cy="24.5" r="1.8" fill="#bfdbfe" /></svg>
    </span>
  );
}

const NAV = [
  { to: "/portal", label: "Home", icon: Home, end: true },
  { to: "/portal/appointments", label: "Appointments", icon: CalendarDays },
  { to: "/portal/messages", label: "Messages", icon: MessageSquare },
  { to: "/portal/visits", label: "Visit summaries", icon: FileHeart },
  { to: "/portal/results", label: "Test results", icon: FlaskConical },
  { to: "/portal/health", label: "Health record", icon: HeartPulse },
  { to: "/portal/insurance", label: "Insurance", icon: ShieldCheck },
  { to: "/portal/billing", label: "Billing", icon: CreditCard },
  { to: "/portal/account", label: "Account", icon: UserRound },
];

export function PortalHome() {
  const { membership, logout, me } = useAuth();
  if (membership && !membership.roles.includes("patient")) return <EmptyState title="The portal is for patients" description="Staff use the main workspace." action={<Button asChild><Link to="/">Go to workspace</Link></Button>} className="min-h-dvh" />;
  if (!membership?.patient_id) return <EmptyState title="Your account isn't linked to a patient record yet" description="Please contact the clinic." className="min-h-dvh" />;
  return (
    <div className="min-h-dvh bg-background">
      <header className="sticky top-0 z-30 border-b bg-card/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4">
          <Brand />
          <span className="truncate font-semibold">{membership.organization_name}</span>
          <span className="hidden text-[13px] text-muted-foreground sm:inline">Patient portal</span>
          <div className="ml-auto flex items-center gap-1">
            <Notifications />
            <span className="hidden text-[13px] sm:inline">{me?.user.first_name}</span>
            <Button variant="ghost" size="sm" onClick={() => logout()}><LogOut />Sign out</Button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-3 scrollbar-thin" aria-label="Portal">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cn("-mb-px flex shrink-0 items-center gap-1.5 border-b-2 border-transparent px-3 py-2.5 text-[13px] font-medium text-muted-foreground hover:text-foreground", isActive && "border-primary text-foreground")}>
              <n.icon className="size-4" />{n.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route index element={<PortalDashboard />} />
          <Route path="appointments" element={<PortalAppointments />} />
          <Route path="book" element={<BookingWizard />} />
          <Route path="appointments/:apptId/intake" element={<IntakeForm />} />
          <Route path="visit/:appointmentId" element={<VideoVisit portal />} />
          <Route path="messages" element={<PortalMessages />} />
          <Route path="messages/:threadId" element={<PortalMessages />} />
          <Route path="visits" element={<VisitSummaries />} />
          <Route path="results" element={<PortalResults />} />
          <Route path="health" element={<HealthRecord />} />
          <Route path="billing" element={<PortalBilling />} />
          <Route path="insurance" element={<PortalInsurance />} />
          <Route path="account" element={<AccountPage />} />
          <Route path="*" element={<EmptyState title="Page not found" />} />
        </Routes>
      </main>
    </div>
  );
}

function ApptCard({ a, onCancelled }: { a: PortalAppt; onCancelled?: () => void }) {
  const { confirm, dialog } = useConfirm();
  const navigate = useNavigate();
  const upcoming = new Date(a.start_at) > new Date(Date.now() - 2 * 3600_000) && ["scheduled", "confirmed", "checked_in"].includes(a.status);
  const cancellable = ["scheduled", "confirmed"].includes(a.status) && new Date(a.start_at).getTime() - Date.now() > 24 * 3600_000;
  return (
    <div className="rounded-xl border bg-card p-4">
      {dialog}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-semibold">{fmtDateTime(a.start_at)}</p>
          <p className="text-[13px] text-muted-foreground">{a.appointment_type?.name ?? "Appointment"} with {a.provider.name}</p>
          <p className="text-[13px] text-muted-foreground">{a.mode === "telehealth" ? "Video visit" : a.clinic.name}</p>
        </div>
        <AppointmentStatusBadge status={a.status} />
      </div>
      {upcoming && (
        <div className="mt-3 flex flex-wrap gap-2">
          {canJoinVideo(a) && <Button size="sm" onClick={() => navigate(`/portal/visit/${a.id}`)}><Video />Join video visit</Button>}
          {a.mode === "telehealth" && !canJoinVideo(a) && <Badge variant="info"><Video />Join opens 30 minutes before</Badge>}
          <Button size="sm" variant={a.intake_submitted ? "ghost" : "outline"} asChild>
            <Link to={`/portal/appointments/${a.id}/intake`}><ClipboardCheck />{a.intake_submitted ? "Update pre-visit form" : "Complete pre-visit form"}</Link>
          </Button>
          {cancellable && <Button size="sm" variant="ghost" className="text-destructive" onClick={async () => {
            if (!(await confirm({ title: "Cancel this appointment?", description: fmtDateTime(a.start_at), destructive: true, confirmLabel: "Cancel appointment" }))) return;
            try { await post(`/portal/appointments/${a.id}/cancel`); toast.success("Appointment cancelled"); onCancelled?.(); } catch (e) { toastError(e); }
          }}>Cancel</Button>}
          {!cancellable && ["scheduled", "confirmed"].includes(a.status) && <span className="self-center text-xs text-muted-foreground">To cancel within 24 hours, please call the clinic.</span>}
        </div>
      )}
    </div>
  );
}

function PortalDashboard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["portal-home"], queryFn: () => get<HomeData>("/portal/home") });
  const threads = useQuery({ queryKey: ["portal-threads"], queryFn: () => get<Thread[]>("/portal/messages") });
  if (q.error) return <ErrorState error={q.error} />;
  if (!q.data) return <LoadingRows />;
  const unread = (threads.data ?? []).reduce((n, t) => n + t.unread, 0);
  return (
    <div className="space-y-6">
      <InsurancePrompt />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-semibold tracking-tight">Hello, {q.data.patient.first_name}</h1><p className="text-[13.5px] text-muted-foreground">Here's what's coming up.</p></div>
        <Button asChild><Link to="/portal/book"><CalendarPlus />Book an appointment</Link></Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Link to="/portal/messages" className="rounded-xl border bg-card p-4 hover:bg-muted/40"><Mail className="mb-2 size-5 text-primary" /><p className="font-medium">Messages</p><p className="text-[13px] text-muted-foreground">{unread ? `${unread} unread` : "Message your care team"}</p></Link>
        <Link to="/portal/results" className="rounded-xl border bg-card p-4 hover:bg-muted/40"><FlaskConical className="mb-2 size-5 text-primary" /><p className="font-medium">Test results</p><p className="text-[13px] text-muted-foreground">{q.data.has_recent_results ? "New results available" : "View released results"}</p></Link>
        <Link to="/portal/visits" className="rounded-xl border bg-card p-4 hover:bg-muted/40"><FileHeart className="mb-2 size-5 text-primary" /><p className="font-medium">Visit summaries</p><p className="text-[13px] text-muted-foreground">Plans and follow-up from past visits</p></Link>
      </div>
      <section>
        <h2 className="mb-3 text-[15px] font-semibold">Upcoming appointments</h2>
        {!q.data.upcoming.length ? <Card><EmptyState icon={CalendarDays} title="No upcoming appointments" action={<Button variant="outline" asChild><Link to="/portal/book">Book one</Link></Button>} /></Card>
          : <div className="grid gap-3 md:grid-cols-2">{q.data.upcoming.map((a) => <ApptCard key={a.id} a={a} onCancelled={() => qc.invalidateQueries({ queryKey: ["portal-home"] })} />)}</div>}
      </section>
    </div>
  );
}

function PortalAppointments() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["portal-appts"], queryFn: () => get<PortalAppt[]>("/portal/appointments") });
  const nowTs = Date.now();
  const upcoming = (q.data ?? []).filter((a) => new Date(a.end_at).getTime() > nowTs - 3600_000 && !["cancelled", "no_show", "checked_out"].includes(a.status)).reverse();
  const past = (q.data ?? []).filter((a) => !upcoming.includes(a));
  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between"><h1 className="text-xl font-semibold">Appointments</h1><Button asChild><Link to="/portal/book"><CalendarPlus />Book</Link></Button></div>
      {q.isLoading ? <LoadingRows /> : <>
        <div className="grid gap-3 md:grid-cols-2">{upcoming.map((a) => <ApptCard key={a.id} a={a} onCancelled={() => qc.invalidateQueries({ queryKey: ["portal-appts"] })} />)}</div>
        {!upcoming.length && <p className="text-[13.5px] text-muted-foreground">No upcoming appointments.</p>}
        <section>
          <h2 className="mb-2 text-[15px] font-semibold">Past</h2>
          <Card><ul className="divide-y">{past.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-2 px-4 py-2.5 text-[13.5px]">
              <span>{fmtDateTime(a.start_at)} · {a.appointment_type?.name ?? "Visit"} with {a.provider.name}</span><AppointmentStatusBadge status={a.status} />
            </li>))}
            {!past.length && <li className="px-4 py-3 text-[13px] text-muted-foreground">None yet.</li>}
          </ul></Card>
        </section>
      </>}
    </div>
  );
}

type Options = { types: { id: string; name: string; duration_minutes: number; is_telehealth: boolean }[]; providers: { id: string; name: string; specialty: string | null; is_my_provider: boolean }[]; clinics: { id: string; name: string; timezone: string; address: string }[] };

function BookingWizard() {
  const navigate = useNavigate();
  const opts = useQuery({ queryKey: ["portal-book-opts"], queryFn: () => get<Options>("/portal/booking/options") });
  const [typeId, setTypeId] = React.useState("");
  const [provId, setProvId] = React.useState("");
  const [clinicId, setClinicId] = React.useState("");
  const tz = opts.data?.clinics.find((c) => c.id === clinicId)?.timezone ?? "America/New_York";
  const [day, setDay] = React.useState(() => addDays(todayIn("America/New_York"), 1));
  const [slot, setSlot] = React.useState<string | null>(null);
  const [reason, setReason] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => {
    if (!opts.data) return;
    setTypeId((v) => v || opts.data.types[0]?.id || "");
    setProvId((v) => v || (opts.data.providers.find((p) => p.is_my_provider) ?? opts.data.providers[0])?.id || "");
    setClinicId((v) => v || opts.data.clinics[0]?.id || "");
  }, [opts.data]);
  const slots = useQuery({
    queryKey: ["portal-slots", provId, clinicId, typeId, day],
    queryFn: () => get<{ slots: string[] }>("/portal/booking/slots", { provider_id: provId, clinic_id: clinicId, type_id: typeId, day }),
    enabled: !!(provId && clinicId && typeId),
  });
  const days = Array.from({ length: 14 }, (_, i) => addDays(todayIn(tz), i + 1));
  const type = opts.data?.types.find((t) => t.id === typeId);
  if (!opts.data) return <LoadingRows />;
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-xl font-semibold">Book an appointment</h1>
      <Card>
        <CardContent className="grid gap-4 pt-5 sm:grid-cols-3">
          <Field label="Visit type"><NativeSelect value={typeId} onChange={(e) => { setTypeId(e.target.value); setSlot(null); }}>{opts.data.types.map((t) => <option key={t.id} value={t.id}>{t.name}{t.is_telehealth ? " (video)" : ""}</option>)}</NativeSelect></Field>
          <Field label="Clinician"><NativeSelect value={provId} onChange={(e) => { setProvId(e.target.value); setSlot(null); }}>{opts.data.providers.map((p) => <option key={p.id} value={p.id}>{p.name}{p.is_my_provider ? " (your clinician)" : ""}</option>)}</NativeSelect></Field>
          <Field label="Location"><NativeSelect value={clinicId} onChange={(e) => { setClinicId(e.target.value); setSlot(null); }}>{opts.data.clinics.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</NativeSelect></Field>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2"><CardTitle>Choose a time</CardTitle><span className="text-xs text-muted-foreground">{tz.replace("_", " ")}</span></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-thin" role="tablist" aria-label="Day">
            {days.map((d) => {
              const dt = new Date(`${d}T12:00:00Z`);
              return (
                <button key={d} role="tab" aria-selected={day === d} onClick={() => { setDay(d); setSlot(null); }}
                  className={cn("flex w-14 shrink-0 flex-col items-center rounded-lg border py-1.5 text-xs", day === d && "border-primary bg-primary text-primary-foreground")}>
                  <span>{dt.toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" })}</span><span className="text-base font-semibold">{dt.getUTCDate()}</span>
                </button>
              );
            })}
          </div>
          {slots.isLoading ? <LoadingRows rows={2} /> : !slots.data?.slots.length ? <p className="text-[13px] text-muted-foreground">No online openings this day. Try another day or clinician, or call the clinic.</p> : (
            <div className="flex flex-wrap gap-1.5">
              {slots.data.slots.map((s) => (
                <button key={s} onClick={() => setSlot(s)} className={cn("rounded-md border px-2.5 py-1.5 text-[13px] tabular hover:border-primary", slot === s && "border-primary bg-primary text-primary-foreground")}>{hhmm(minutesOfDay(s, tz))}</button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
      {slot && (
        <Card>
          <CardContent className="space-y-3 pt-5">
            <p className="text-[13.5px]"><strong>{type?.name}</strong> with {opts.data.providers.find((p) => p.id === provId)?.name} on <strong>{fmtDateTime(slot)}</strong>{type?.is_telehealth ? " (video visit)" : ` at ${opts.data.clinics.find((c) => c.id === clinicId)?.name}`}</p>
            <Field label="Reason for visit" required><Input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} placeholder="e.g. Follow-up on blood pressure" /></Field>
            <p className="text-xs text-muted-foreground">For urgent problems call the clinic. For emergencies call 911.</p>
            <Button loading={busy} disabled={reason.trim().length < 3} onClick={async () => {
              setBusy(true);
              try {
                await post("/portal/appointments", { appointment_type_id: typeId, provider_id: provId, clinic_id: clinicId, start_at: slot, reason });
                toast.success("Appointment booked");
                navigate("/portal/appointments");
              } catch (e) { toastError(e); slots.refetch(); setSlot(null); } finally { setBusy(false); }
            }}>Confirm booking</Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

const SYMPTOMS = ["Fever", "Cough", "Shortness of breath", "Chest pain", "Headache", "Nausea", "Rash", "Fatigue", "Pain"];
const PHQ = ["Not at all", "Several days", "More than half the days", "Nearly every day"];

function IntakeForm() {
  const { apptId = "" } = useParams();
  const navigate = useNavigate();
  const pid = useAuthPatient();
  const existing = useQuery({ queryKey: ["intake", apptId], queryFn: () => get<{ answers: Record<string, unknown> } | null>(`/portal/appointments/${apptId}/intake`) });
  const summary = useQuery({ queryKey: ["portal-summary"], queryFn: () => get<Summary>(`/patients/${pid}/summary`) });
  const [f, setF] = React.useState({ reason_details: "", symptoms: [] as string[], symptom_duration: "", pain_score: "", medications_confirmed: false, medication_changes: "", allergies_confirmed: false, allergy_changes: "", phq2_interest: "0", phq2_mood: "0", questions_for_clinician: "" });
  React.useEffect(() => {
    const a = existing.data?.answers as Record<string, unknown> | undefined;
    if (a) setF((x) => ({ ...x, ...Object.fromEntries(Object.entries(a).map(([k, v]) => [k, typeof v === "number" ? String(v) : v ?? ""])) } as typeof x));
  }, [existing.data]);
  const [busy, setBusy] = React.useState(false);
  const set = (k: keyof typeof f, v: unknown) => setF({ ...f, [k]: v });
  return (
    <form className="mx-auto max-w-2xl space-y-4" onSubmit={async (e) => {
      e.preventDefault();
      setBusy(true);
      try {
        await post(`/portal/appointments/${apptId}/intake`, {
          ...f, pain_score: f.pain_score === "" ? null : Number(f.pain_score), phq2_interest: Number(f.phq2_interest), phq2_mood: Number(f.phq2_mood),
          symptom_duration: f.symptom_duration || null, medication_changes: f.medication_changes || null, allergy_changes: f.allergy_changes || null, questions_for_clinician: f.questions_for_clinician || null,
        });
        toast.success("Thanks — your answers were sent to your care team");
        navigate("/portal");
      } catch (err) { toastError(err); } finally { setBusy(false); }
    }}>
      <h1 className="text-xl font-semibold">Pre-visit form</h1>
      <Card><CardContent className="space-y-4 pt-5">
        <Field label="What would you like to discuss?" required><Textarea rows={3} value={f.reason_details} onChange={(e) => set("reason_details", e.target.value)} /></Field>
        <fieldset><legend className="mb-2 text-[13px] font-medium">Current symptoms</legend>
          <div className="flex flex-wrap gap-2">{SYMPTOMS.map((s) => (
            <label key={s} className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[13px]"><Checkbox checked={f.symptoms.includes(s)} onCheckedChange={(c) => set("symptoms", c ? [...f.symptoms, s] : f.symptoms.filter((x) => x !== s))} />{s}</label>
          ))}</div>
        </fieldset>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="How long?"><Input value={f.symptom_duration} onChange={(e) => set("symptom_duration", e.target.value)} placeholder="e.g. 3 days" /></Field>
          <Field label="Pain (0–10)"><NativeSelect value={f.pain_score} onChange={(e) => set("pain_score", e.target.value)}><option value="">No pain / not applicable</option>{Array.from({ length: 11 }, (_, i) => <option key={i}>{i}</option>)}</NativeSelect></Field>
        </div>
      </CardContent></Card>
      <Card><CardHeader className="pb-2"><CardTitle>Medications & allergies</CardTitle></CardHeader><CardContent className="space-y-3">
        <div className="rounded-lg bg-muted/50 p-3 text-[13px]"><p className="mb-1 font-medium">Medications on file</p>{summary.data?.medications?.length ? summary.data.medications.map((m) => <p key={m.id}>{m.name} {m.dose}</p>) : <p className="text-muted-foreground">None</p>}</div>
        <label className="flex items-center gap-2 text-[13px]"><Checkbox checked={f.medications_confirmed} onCheckedChange={(c) => set("medications_confirmed", !!c)} />This list is correct</label>
        {!f.medications_confirmed && <Field label="What's changed?"><Textarea rows={2} value={f.medication_changes} onChange={(e) => set("medication_changes", e.target.value)} /></Field>}
        <div className="rounded-lg bg-muted/50 p-3 text-[13px]"><p className="mb-1 font-medium">Allergies on file</p>{summary.data?.allergies?.length ? summary.data.allergies.map((a) => <p key={a.id}>{a.substance} — {a.reaction}</p>) : <p className="text-muted-foreground">No known allergies</p>}</div>
        <label className="flex items-center gap-2 text-[13px]"><Checkbox checked={f.allergies_confirmed} onCheckedChange={(c) => set("allergies_confirmed", !!c)} />This list is correct</label>
        {!f.allergies_confirmed && <Field label="What's changed?"><Textarea rows={2} value={f.allergy_changes} onChange={(e) => set("allergy_changes", e.target.value)} /></Field>}
      </CardContent></Card>
      <Card><CardHeader className="pb-2"><CardTitle>Over the last 2 weeks, how often have you been bothered by…</CardTitle></CardHeader><CardContent className="grid gap-3 sm:grid-cols-2">
        <Field label="Little interest or pleasure in doing things"><NativeSelect value={f.phq2_interest} onChange={(e) => set("phq2_interest", e.target.value)}>{PHQ.map((l, i) => <option key={i} value={i}>{l}</option>)}</NativeSelect></Field>
        <Field label="Feeling down, depressed, or hopeless"><NativeSelect value={f.phq2_mood} onChange={(e) => set("phq2_mood", e.target.value)}>{PHQ.map((l, i) => <option key={i} value={i}>{l}</option>)}</NativeSelect></Field>
      </CardContent></Card>
      <Card><CardContent className="pt-5"><Field label="Questions for your clinician"><Textarea rows={2} value={f.questions_for_clinician} onChange={(e) => set("questions_for_clinician", e.target.value)} /></Field></CardContent></Card>
      <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => navigate(-1)}>Cancel</Button><Button type="submit" loading={busy} disabled={!f.reason_details.trim()}><Send />Submit</Button></div>
    </form>
  );
}

function useAuthPatient() {
  const { membership } = useAuth();
  return membership?.patient_id ?? "";
}

function PortalMessages() {
  const { threadId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const threads = useQuery({ queryKey: ["portal-threads"], queryFn: () => get<Thread[]>("/portal/messages"), refetchInterval: 20_000 });
  const thread = useQuery({ queryKey: ["portal-thread", threadId], queryFn: () => get<Thread>(`/portal/messages/${threadId}`), enabled: !!threadId && threadId !== "new" });
  const [compose, setCompose] = React.useState({ subject: "", category: "general", body: "" });
  const [reply, setReply] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (thread.data) qc.invalidateQueries({ queryKey: ["portal-threads"] }); }, [thread.data?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between border-b px-4 py-3"><span className="font-semibold">Messages</span><Button size="xs" onClick={() => navigate("/portal/messages/new")}><Send />New</Button></div>
        {threads.isLoading ? <LoadingRows rows={3} /> : !threads.data?.length ? <p className="p-4 text-[13px] text-muted-foreground">No messages yet.</p> : (
          <ul className="divide-y">{threads.data.map((t) => (
            <li key={t.id}><Link to={`/portal/messages/${t.id}`} className={cn("block px-4 py-3 hover:bg-muted/40", t.id === threadId && "bg-accent/50")}>
              <span className="flex items-center gap-2 text-[13.5px] font-medium">{t.subject}{t.unread > 0 && <span className="size-2 rounded-full bg-primary" />}</span>
              <span className="block truncate text-xs text-muted-foreground">{t.messages[t.messages.length - 1]?.body}</span>
              <span className="text-[11px] text-muted-foreground">{fmtDateTime(t.last_message_at)}</span>
            </Link></li>
          ))}</ul>
        )}
      </Card>
      <Card>
        {threadId === "new" ? (
          <form className="space-y-3 p-5" onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try { const t = await post<Thread>("/portal/messages", compose); qc.invalidateQueries({ queryKey: ["portal-threads"] }); navigate(`/portal/messages/${t.id}`); setCompose({ subject: "", category: "general", body: "" }); }
            catch (err) { toastError(err); } finally { setBusy(false); }
          }}>
            <h2 className="font-semibold">New message to your care team</h2>
            <div className="grid gap-3 sm:grid-cols-[1fr_180px]">
              <Field label="Subject" required><Input value={compose.subject} onChange={(e) => setCompose({ ...compose, subject: e.target.value })} /></Field>
              <Field label="Topic"><NativeSelect value={compose.category} onChange={(e) => setCompose({ ...compose, category: e.target.value })}><option value="general">General question</option><option value="medication">Medication / refill</option><option value="results">Test results</option><option value="appointment">Appointment</option></NativeSelect></Field>
            </div>
            <Field label="Message" required><Textarea rows={6} value={compose.body} onChange={(e) => setCompose({ ...compose, body: e.target.value })} /></Field>
            <p className="text-xs text-muted-foreground">Messages are answered within 2 business days. Don't use messages for urgent needs — call the clinic or 911.</p>
            <Button type="submit" loading={busy} disabled={compose.subject.trim().length < 2 || !compose.body.trim()}><Send />Send</Button>
          </form>
        ) : !threadId ? <EmptyState icon={MessageSquare} title="Select a conversation" description="Or start a new message to your care team." />
          : thread.isLoading ? <LoadingRows /> : thread.data && (
            <div className="flex h-full flex-col">
              <div className="border-b px-5 py-3"><p className="font-semibold">{thread.data.subject}</p>{thread.data.status === "closed" && <Badge>Closed</Badge>}</div>
              <ol className="flex-1 space-y-3 p-5">{thread.data.messages.map((m) => (
                <li key={m.id} className={cn("max-w-[80%] rounded-2xl px-4 py-2.5 text-[13.5px]", m.from_patient ? "ml-auto bg-primary text-primary-foreground" : "bg-muted")}>
                  <p className="whitespace-pre-wrap">{m.body}</p>
                  <p className={cn("mt-1 text-[11px]", m.from_patient ? "text-primary-foreground/70" : "text-muted-foreground")}>{m.from_patient ? "You" : m.sender} · {fmtDateTime(m.created_at)}</p>
                </li>
              ))}</ol>
              {thread.data.status === "open" && (
                <form className="flex gap-2 border-t p-3" onSubmit={async (e) => {
                  e.preventDefault();
                  setBusy(true);
                  try { await post(`/portal/messages/${threadId}/reply`, { body: reply }); setReply(""); thread.refetch(); } catch (err) { toastError(err); } finally { setBusy(false); }
                }}>
                  <Input value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Write a reply…" aria-label="Reply" />
                  <Button type="submit" loading={busy} disabled={!reply.trim()}><Send />Send</Button>
                </form>
              )}
            </div>
          )}
      </Card>
    </div>
  );
}

type Avs = { encounter_id: string; date: string; provider: string; reason: string | null; diagnoses: { code: string; description: string }[]; assessment: string | null; plan: string | null; follow_up: string | null; addenda: string[]; vitals: { bp: string | null; heart_rate: number | null; weight_lb: number | null }; prescriptions: { title: string; sig: string }[] };

function VisitSummaries() {
  const q = useQuery({ queryKey: ["portal-visits"], queryFn: () => get<Avs[]>("/portal/visits") });
  if (q.isLoading) return <LoadingRows />;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Visit summaries</h1>
      {!q.data?.length && <Card><EmptyState icon={FileHeart} title="No visit summaries yet" description="Summaries appear after your clinician signs the visit note." /></Card>}
      {q.data?.map((v) => (
        <Card key={v.encounter_id}>
          <CardHeader className="pb-2"><div><CardTitle>{fmtDate(v.date)} · {v.reason ?? "Office visit"}</CardTitle><p className="text-[13px] text-muted-foreground">{v.provider}</p></div></CardHeader>
          <CardContent className="space-y-3 text-[13.5px]">
            {!!v.diagnoses.length && <div><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Diagnoses</p>{v.diagnoses.map((d) => <p key={d.code}>{d.description}</p>)}</div>}
            {v.plan && <div><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Your plan</p><p className="whitespace-pre-wrap">{v.plan}</p></div>}
            {!!v.prescriptions.length && <div><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Prescriptions</p>{v.prescriptions.map((p) => <p key={p.title} className="flex items-center gap-1.5"><Pill className="size-3.5" />{p.title} — {p.sig}</p>)}</div>}
            {v.follow_up && <p><strong>Follow-up:</strong> {v.follow_up}</p>}
            {(v.vitals.bp || v.vitals.heart_rate) && <p className="text-muted-foreground">Vitals: {[v.vitals.bp && `BP ${v.vitals.bp}`, v.vitals.heart_rate && `HR ${v.vitals.heart_rate}`, v.vitals.weight_lb && `${v.vitals.weight_lb} lb`].filter(Boolean).join(" · ")}</p>}
            {v.addenda.map((a, i) => <p key={i} className="rounded-lg border-l-4 border-primary bg-muted/40 px-3 py-1.5 text-[13px]">Update: {a}</p>)}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

type PR = { id: string; panel: string; name: string; value: string; unit: string | null; reference_range: string | null; flag: string; resulted_at: string; order_id: string };

function PortalResults() {
  const pid = useAuthPatient();
  const q = useQuery({ queryKey: ["portal-results"], queryFn: () => get<PR[]>(`/patients/${pid}/results`) });
  if (q.isLoading) return <LoadingRows />;
  const byOrder = new Map<string, PR[]>();
  (q.data ?? []).forEach((r) => byOrder.set(r.order_id, [...(byOrder.get(r.order_id) ?? []), r]));
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Test results</h1>
      <p className="text-[13px] text-muted-foreground">Results appear here after your clinician reviews them. Questions? <Link to="/portal/messages/new" className="text-primary underline">Send a message</Link>.</p>
      {!byOrder.size && <Card><EmptyState icon={FlaskConical} title="No released results" /></Card>}
      {[...byOrder.values()].map((rs) => (
        <Card key={rs[0].order_id}>
          <CardHeader className="pb-2"><CardTitle>{rs[0].panel}</CardTitle><span className="text-xs text-muted-foreground">{fmtDateTime(rs[0].resulted_at)}</span></CardHeader>
          <CardContent>
            <table className="w-full text-[13.5px]"><tbody>{rs.map((r) => (
              <tr key={r.id} className="border-b last:border-0">
                <td className="py-1.5">{r.name}</td>
                <td className={cn("tabular", flagClass(r.flag))}>{r.value} {r.unit} {flagLabel(r.flag) && <span className="text-xs">({r.flag.replace("_", " ")})</span>}</td>
                <td className="text-right text-muted-foreground tabular">{r.reference_range && `normal ${r.reference_range}`}</td>
              </tr>
            ))}</tbody></table>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function HealthRecord() {
  const pid = useAuthPatient();
  const s = useQuery({ queryKey: ["portal-summary"], queryFn: () => get<Summary>(`/patients/${pid}/summary`) });
  if (s.isLoading || !s.data) return <LoadingRows />;
  const d = s.data;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Health record</h1>
      <div className="grid gap-4 md:grid-cols-2">
        <Card><CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><ShieldCheck className="size-4 text-destructive" />Allergies</CardTitle></CardHeader>
          <CardContent>{d.allergies?.length ? <ul className="space-y-1 text-[13.5px]">{d.allergies.map((a) => <li key={a.id}>{a.substance} <span className="text-muted-foreground">— {a.reaction}</span></li>)}</ul> : <p className="text-[13px] text-muted-foreground">No known allergies on file.</p>}</CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><Pill className="size-4 text-success" />Medications</CardTitle></CardHeader>
          <CardContent>{d.medications?.length ? <ul className="space-y-1 text-[13.5px]">{d.medications.map((m) => <li key={m.id}>{m.name} <span className="text-muted-foreground">{[m.dose, m.frequency].filter(Boolean).join(", ")}</span></li>)}</ul> : <p className="text-[13px] text-muted-foreground">No medications on file.</p>}</CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle>Health conditions</CardTitle></CardHeader>
          <CardContent>{d.problems?.length ? <ul className="space-y-1 text-[13.5px]">{d.problems.map((p) => <li key={p.id}>{p.description}</li>)}</ul> : <p className="text-[13px] text-muted-foreground">None on file.</p>}</CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><HeartPulse className="size-4 text-primary" />Latest vitals</CardTitle></CardHeader>
          <CardContent className="text-[13.5px]">{d.last_vitals ? <>{d.last_vitals.systolic && <p>Blood pressure {d.last_vitals.systolic}/{d.last_vitals.diastolic}</p>}{d.last_vitals.heart_rate && <p>Heart rate {d.last_vitals.heart_rate}</p>}<p className="text-xs text-muted-foreground">{fmtDateTime(d.last_vitals.measured_at)} · {fmtTime(d.last_vitals.measured_at)}</p></> : <p className="text-muted-foreground">None recorded.</p>}</CardContent></Card>
      </div>
      <p className="text-xs text-muted-foreground">Something incorrect? <Link to="/portal/messages/new" className="text-primary underline">Let your care team know</Link>.</p>
    </div>
  );
}

type Bill = { id: string; number: string; description: string; status: string; total_cents: number; balance_cents: number; issued_at: string; due_date: string };

function PortalBilling() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["portal-bills"], queryFn: () => get<{ balance_cents: number; invoices: Bill[]; payments: { id: string; amount_cents: number; created_at: string; reference: string | null }[] }>("/portal/bills") });
  const [paying, setPaying] = React.useState<Bill | null>(null);
  const [amount, setAmount] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const key = React.useRef<string | null>(null);
  if (!q.data) return <LoadingRows />;
  const cents = Math.round(Number(amount) * 100);
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Billing</h1>
      <Card><CardContent className="flex flex-wrap items-center gap-4 pt-5">
        <CreditCard className="size-6 text-primary" />
        <div><p className="text-xs text-muted-foreground">Amount you owe</p><p className="text-2xl font-semibold tabular">{fmtMoney(q.data.balance_cents)}</p></div>
        <Badge variant="warning" className="ml-auto"><FlaskConical />Payments are simulated — no card is charged</Badge>
      </CardContent></Card>
      <Card><CardHeader className="pb-2"><CardTitle>Statements</CardTitle></CardHeader><CardContent>
        {!q.data.invoices.length ? <p className="text-[13px] text-muted-foreground">No statements.</p> : (
          <ul className="divide-y">{q.data.invoices.map((i) => (
            <li key={i.id} className="flex flex-wrap items-center gap-3 py-3 text-[13.5px]">
              <span className="min-w-0 flex-1"><span className="font-medium">{i.description}</span><span className="block text-xs text-muted-foreground">{i.number} · issued {fmtDate(i.issued_at)} · due {fmtDate(i.due_date)}</span></span>
              <span className="tabular">{fmtMoney(i.balance_cents)}{i.balance_cents !== i.total_cents && <span className="text-xs text-muted-foreground"> of {fmtMoney(i.total_cents)}</span>}</span>
              {i.status === "open" ? <Button size="sm" onClick={() => { setPaying(i); setAmount((i.balance_cents / 100).toFixed(2)); key.current = null; }}>Pay now</Button> : <Badge variant="success">Paid</Badge>}
            </li>
          ))}</ul>
        )}
      </CardContent></Card>
      <Card><CardHeader className="pb-2"><CardTitle>Payment history</CardTitle></CardHeader><CardContent>
        {!q.data.payments.length ? <p className="text-[13px] text-muted-foreground">No payments yet.</p> : <ul className="divide-y text-[13.5px]">{q.data.payments.map((p) => <li key={p.id} className="flex justify-between py-2"><span>{fmtDateTime(p.created_at)} · {p.reference}</span><span className="tabular">{fmtMoney(p.amount_cents)}</span></li>)}</ul>}
      </CardContent></Card>
      {paying && (
        <Card className="border-primary/30"><CardContent className="space-y-3 pt-5">
          <p className="font-medium">Pay {paying.number}</p>
          <Field label="Amount (USD)" hint={`Balance ${fmtMoney(paying.balance_cents)}`}><Input inputMode="decimal" value={amount} onChange={(e) => { setAmount(e.target.value.replace(/[^\d.]/g, "")); key.current = null; }} className="max-w-40" /></Field>
          <p className="text-xs text-muted-foreground">This environment uses a simulated payment processor. You won't be asked for card details and nothing is charged.</p>
          <div className="flex gap-2">
            <Button loading={busy} disabled={!(cents > 0) || cents > paying.balance_cents} onClick={async () => {
              key.current ??= newIdempotencyKey("portal-pay");
              setBusy(true);
              try { await post(`/portal/bills/${paying.id}/pay`, { amount_cents: cents }, { "Idempotency-Key": key.current }); toast.success(`Payment of ${fmtMoney(cents)} received`); setPaying(null); qc.invalidateQueries({ queryKey: ["portal-bills"] }); }
              catch (e) { toastError(e); } finally { setBusy(false); }
            }}>Pay {cents > 0 ? fmtMoney(cents) : ""}</Button>
            <Button variant="ghost" onClick={() => setPaying(null)}>Cancel</Button>
          </div>
        </CardContent></Card>
      )}
    </div>
  );
}

function InsurancePrompt() {
  const q = usePortalInsurance();
  const req = q.data?.requests.find((r) => r.status === "requested");
  if (!req) return null;
  return (
    <Link to="/portal/insurance" className="flex items-start gap-3 rounded-xl border border-warning/50 bg-warning-soft/40 p-4 hover:bg-warning-soft/60">
      <CircleAlert className="mt-0.5 size-5 shrink-0 text-warning" />
      <div className="text-[13.5px]"><p className="font-medium">Please confirm your insurance</p><p className="text-muted-foreground">{req.reason} It takes about a minute.</p></div>
    </Link>
  );
}
