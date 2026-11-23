import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, BedDouble, Bot, CheckCircle2, CircleDashed, ClipboardList, FileText, HeartPulse, LogOut, MinusCircle, Stethoscope, UserPlus, Users } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { AIBadge, EmptyState, ErrorState, KeyValue, LoadingRows, PageHeader, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, fromNow } from "@/lib/format";
import { ROLE_LABELS, type Role } from "@/lib/types";
import { StatusChip } from "@/components/common/Status";
import { cn, titleCase } from "@/lib/utils";
import { AdmitDialog, losLabel, type StayT, StayStatusBadge } from "./shared";
import { AskAI } from "@/features/ai/AskAI";

type Item = { id: string; key: string; label: string; required: boolean; owner_role: Role; verification: string; status: string; note: string | null; evidence: Record<string, string>; completed_at: string | null };
type Readiness = { ready: boolean; blocking: string[]; done: number; total: number; items: Item[]; instructions: { text: string | null; source: string | null; approved_at: string | null }; plan_status: string };
type DischargeT = { stay: StayT; readiness: Readiness | null; pending_instructions: { id: string; text: string; source: string; created_at: string } | null };
type StayDetail = StayT & { movements: { bed: string; start_at: string; end_at: string | null; reason: string }[]; events: { kind: string; at: string; note: string | null }[] };
type NursingRow = StayT & { vitals: null | { measured_at: string; bp: string | null; hr: number | null; rr: number | null; temp_c: number | null; spo2: number | null; pain: number | null }; open_tasks: number; vitals_overdue: boolean; last_handoff_at: string | null; discharge: null | { ready: boolean; done: number; total: number; blocking: string[] } };

// ======================= Inpatient list =======================

export function InpatientsPage() {
  const [status, setStatus] = React.useState<"active" | "pending" | "discharge_ordered" | "discharged">("active");
  const [mine, setMine] = React.useState(false);
  const [admit, setAdmit] = React.useState(false);
  const { can, membership } = useAuth();
  const q = useQuery({ queryKey: ["adt", "stays", status, mine], queryFn: () => get<StayT[]>("/adt/stays", { status, mine: mine || undefined }) });
  const nav = useNavigate();
  return (
    <>
      <PageHeader title="Inpatients" description="Hospital stays across your units — admissions, current location, length of stay and discharge status."
        actions={can("adt:write") ? <Button onClick={() => setAdmit(true)}><UserPlus />Request admission</Button> : undefined} />
      <Card className="overflow-hidden">
        <div className="flex flex-wrap gap-1.5 border-b p-3">
          {([["active", "Current"], ["pending", "Awaiting bed"], ["discharge_ordered", "Discharge ordered"], ["discharged", "Discharged"]] as const).map(([v, l]) => (
            <button key={v} onClick={() => setStatus(v)} className={cn("rounded-md px-2.5 py-1 text-[13px] font-medium text-muted-foreground hover:bg-muted", status === v && "bg-accent text-accent-foreground")}>{l}</button>))}
          {membership?.provider_id && <><span className="mx-1 w-px bg-border" /><button onClick={() => setMine(!mine)} className={cn("rounded-md px-2.5 py-1 text-[13px] font-medium text-muted-foreground hover:bg-muted", mine && "bg-accent text-accent-foreground")}>My patients</button></>}
        </div>
        {q.isLoading ? <LoadingRows /> : q.isError ? <ErrorState error={q.error} retry={q.refetch} /> : !q.data?.length ? <EmptyState icon={BedDouble} title="No patients" /> : (
          <Table><THead><TR><TH>Patient</TH><TH>Bed</TH><TH>Unit</TH><TH>Reason</TH><TH>Attending</TH><TH>LOS</TH><TH>Status</TH></TR></THead>
            <TBody>{q.data.map((s) => (
              <TR key={s.id} className="cursor-pointer hover:bg-muted/40" onClick={() => nav(`/inpatients/${s.id}`)}>
                <TD><p className="font-medium">{s.patient.name}</p><p className="text-xs text-muted-foreground">{s.patient.mrn}</p></TD>
                <TD className="font-medium">{s.bed?.name ?? "—"}</TD><TD>{s.department?.name ?? "—"}</TD><TD className="max-w-64 truncate">{s.reason}</TD>
                <TD>{s.attending ?? "—"}</TD><TD className="tabular">{s.status === "pending" ? `waiting ${losLabel(s.waiting_hours)}` : losLabel(s.los_hours)}</TD>
                <TD><StayStatusBadge status={s.status} />{s.isolation && <Badge variant="warning" className="ml-1">{s.isolation}</Badge>}</TD>
              </TR>))}</TBody></Table>
        )}
      </Card>
      <AdmitDialog open={admit} onOpenChange={setAdmit} />
    </>
  );
}

// ======================= Stay detail =======================

export function InpatientDetail() {
  const { stayId } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["adt", "stay", stayId], queryFn: () => get<StayDetail>(`/adt/stays/${stayId}`) });
  const dc = useQuery({ queryKey: ["discharge", stayId], queryFn: () => get<DischargeT>(`/adt/stays/${stayId}/discharge`) });
  const [dialog, setDialog] = React.useState<null | "order" | "discharge" | "override">(null);
  const [f, setF] = React.useState({ disposition: "home", note: "" });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["adt"] }); qc.invalidateQueries({ queryKey: ["discharge", stayId] }); qc.invalidateQueries({ queryKey: ["beds"] }); };
  const act = async (path: string, body: unknown, ok: string) => { try { await post(path, body); toast.success(ok); setDialog(null); refresh(); } catch (e) { toastError(e); } };
  if (q.isLoading) return <LoadingRows rows={8} />;
  if (q.isError || !q.data) return <ErrorState error={q.error} retry={q.refetch} />;
  const s = q.data;
  const r = dc.data?.readiness;
  return (
    <>
      <PageHeader title={s.patient.name} description={`${s.patient.mrn} · DOB ${fmtDate(s.patient.dob)} · ${s.reason}`}
        actions={<div className="flex flex-wrap gap-2">
          <Button variant="outline" asChild><Link to={`/patients/${s.patient.id}`}>Open chart</Link></Button>
          {s.encounter_id && <Button variant="outline" asChild><Link to={`/encounters/${s.encounter_id}`}><FileText />Documentation</Link></Button>}
          {s.status === "admitted" && can("orders:sign") && <Button onClick={() => setDialog("order")}><LogOut />Order discharge</Button>}
          {s.status === "discharge_ordered" && can("adt:write") && (
            <div className="flex flex-col items-end gap-1">
              <Button disabled={!r || (!r.ready && !can("orders:sign"))} aria-describedby="complete-discharge-reason" onClick={() => setDialog(r && !r.ready ? "override" : "discharge")}><CheckCircle2 />Complete discharge</Button>
              {r && !r.ready && <p id="complete-discharge-reason" className="max-w-xs text-right text-[11.5px] text-muted-foreground">
                {can("orders:sign") ? `${r.blocking.length} required step(s) still open — completing now is an audited override.` : `Available when ${r.blocking.length} required step(s) are done (see Discharge tab) — or a physician overrides.`}</p>}
            </div>
          )}
        </div>} />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Card className="p-4"><KeyValue label="Status" value={<StayStatusBadge status={s.status} />} /></Card>
        <Card className="p-4"><KeyValue label="Bed" value={s.bed ? `${s.bed.name} · ${s.department?.name ?? ""}` : "Not placed"} /></Card>
        <Card className="p-4"><KeyValue label="Attending" value={s.attending} /></Card>
        <Card className="p-4"><KeyValue label="Length of stay" value={s.status === "pending" ? `waiting ${losLabel(s.waiting_hours)}` : losLabel(s.los_hours)} /></Card>
        <Card className="p-4"><KeyValue label="Expected discharge" value={s.expected_discharge_date ? fmtDate(s.expected_discharge_date) : "—"} /></Card>
      </div>
      <Tabs defaultValue={s.status === "discharge_ordered" ? "discharge" : "care"}>
        <TabsList><TabsTrigger value="care">Nursing & vitals</TabsTrigger><TabsTrigger value="discharge">Discharge {r ? <span className="ml-1.5 text-xs tabular text-muted-foreground">{r.done}/{r.total}</span> : null}</TabsTrigger><TabsTrigger value="team">Care team</TabsTrigger><TabsTrigger value="history">Movement history</TabsTrigger></TabsList>
        <TabsContent value="care"><NursingPanel stay={s} /></TabsContent>
        <TabsContent value="discharge"><DischargePanel stay={s} data={dc.data} onChange={refresh} /></TabsContent>
        <TabsContent value="team"><CareTeamPanel stayId={s.id} /></TabsContent>
        <TabsContent value="history">
          <Card><CardContent className="grid gap-6 p-5 md:grid-cols-2">
            <div><h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Beds</h4>
              <ul className="space-y-1.5 text-[13px]">{s.movements.map((m, i) => <li key={i}><span className="font-medium">{m.bed}</span> <span className="text-muted-foreground">{fmtDateTime(m.start_at)} → {m.end_at ? fmtDateTime(m.end_at) : "now"} · {m.reason}</span></li>)}</ul></div>
            <div><h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">ADT events</h4>
              <ol className="space-y-1.5 text-[13px]">{s.events.map((e, i) => <li key={i}><span className="font-medium">{titleCase(e.kind.replace(/_/g, " "))}</span> <span className="text-muted-foreground">{fmtDateTime(e.at)}{e.note ? ` · ${e.note}` : ""}</span></li>)}</ol></div>
          </CardContent></Card>
        </TabsContent>
      </Tabs>
      <Dialog open={dialog === "order"} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent size="sm"><DialogHeader><DialogTitle>Order discharge</DialogTitle><DialogDescription>Creates the discharge checklist and sends a task to each owner (pharmacy, nursing, front desk, physician).</DialogDescription></DialogHeader>
          <Field label="Disposition"><NativeSelect value={f.disposition} onChange={(e) => setF({ ...f, disposition: e.target.value })}>{["home", "home_health", "snf", "rehab", "hospice", "transfer", "other"].map((d) => <option key={d} value={d}>{titleCase(d.replace("_", " "))}</option>)}</NativeSelect></Field>
          <Field label="Note"><Input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
          <DialogFooter><Button variant="outline" onClick={() => setDialog(null)}>Cancel</Button><Button onClick={() => act(`/adt/stays/${s.id}/discharge-order`, { disposition: f.disposition, note: f.note || null }, "Discharge ordered — checklist created")}>Order discharge</Button></DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={dialog === "discharge" || dialog === "override"} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent size="sm"><DialogHeader><DialogTitle>{dialog === "override" ? "Discharge with open items" : "Complete discharge"}</DialogTitle>
          <DialogDescription>{dialog === "override" ? `Still open: ${r?.blocking.join(", ")}. This override is audited.` : "The bed goes to cleaning and housekeeping is notified."}</DialogDescription></DialogHeader>
          <Field label={dialog === "override" ? "Reason for override" : "Note"} required={dialog === "override"}><Textarea rows={2} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
          <DialogFooter><Button variant="outline" onClick={() => setDialog(null)}>Cancel</Button>
            <Button variant={dialog === "override" ? "destructive" : "default"} disabled={dialog === "override" && f.note.trim().length < 5}
              onClick={() => act(`/adt/stays/${s.id}/discharge`, dialog === "override" ? { override_readiness: true, override_reason: f.note } : { note: f.note || null }, "Patient discharged")}>Discharge</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

const ITEM_ICON: Record<string, React.ElementType> = { done: CheckCircle2, not_applicable: MinusCircle, pending: CircleDashed, in_progress: Activity };

function DischargePanel({ stay, data, onChange }: { stay: StayT; data?: DischargeT; onChange: () => void }) {
  const { can, membership } = useAuth();
  const [draft, setDraft] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const r = data?.readiness;
  const pending = data?.pending_instructions;
  React.useEffect(() => { if (pending) setDraft(pending.text); }, [pending?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const roles = membership?.roles ?? [];
  const mark = async (key: string, status: string) => {
    const note = status === "not_applicable" ? window.prompt("Why doesn't this apply?") : null;
    if (status === "not_applicable" && !note) return;
    try { await post(`/adt/stays/${stay.id}/discharge/items/${key}`, { status, note }); toast.success("Checklist updated"); onChange(); } catch (e) { toastError(e); }
  };
  if (!data) return <LoadingRows />;
  if (!r) return (
    <Card><CardContent className="flex flex-col items-start gap-3 p-6"><p className="text-[13.5px] text-muted-foreground">No discharge plan yet. It starts automatically when discharge is ordered, or start planning early.</p>
      {can("clinical:write") && stay.status === "admitted" && <Button variant="outline" onClick={async () => { try { await post(`/adt/stays/${stay.id}/discharge/plan`); toast.success("Discharge planning started"); onChange(); } catch (e) { toastError(e); } }}><ClipboardList />Start discharge planning</Button>}
    </CardContent></Card>
  );
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_420px]">
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2"><CardTitle>Discharge checklist</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
          <AskAI agent="discharge_coordination" size="xs" variant="ghost" label="What's this waiting on?" question={`Summarize what the discharge for ${stay.patient.name} (stay ${stay.id}) is waiting on, which team owns each step, and what should happen next.`} />
          <StatusChip status={r.ready ? "done" : "waiting"} label={r.ready ? "Ready to discharge" : `${r.blocking.length} step${r.blocking.length === 1 ? "" : "s"} left`} /></div></CardHeader>
        <CardContent>
        {(() => {
          // Plain-language summary: which teams the discharge is waiting on, and what each still has to do.
          const open = r.items.filter((it) => it.required && !["done", "not_applicable"].includes(it.status));
          const byOwner = new Map<string, string[]>();
          for (const it of open) byOwner.set(it.owner_role, [...(byOwner.get(it.owner_role) ?? []), it.label]);
          if (!open.length) return <p className="mb-3 rounded-lg bg-success-soft/60 px-3 py-2 text-[13px]"><strong>All required steps are done.</strong> The discharge can be completed.</p>;
          return (
            <div className="mb-3 rounded-lg border border-warning/40 bg-warning-soft/50 px-3 py-2.5 text-[13px]" data-testid="discharge-waiting-on">
              <p><strong>Waiting on:</strong> {[...byOwner.keys()].map((role) => `${ROLE_LABELS[role as Role] ?? role}${roles.includes(role as Role) ? " (you)" : ""}`).join(", ")}</p>
              <ul className="mt-1 space-y-0.5 text-muted-foreground">
                {[...byOwner.entries()].map(([role, labels]) => <li key={role}><span className="text-foreground">{ROLE_LABELS[role as Role] ?? role}:</span> {labels.join("; ")}</li>)}
              </ul>
              <p className="mt-1.5 text-muted-foreground">Complete discharge becomes available when these are done. A physician can discharge with open items; that override is recorded in the audit log.</p>
            </div>
          );
        })()}
        <ul className="divide-y">{r.items.map((it) => {
          const Icon = ITEM_ICON[it.status] ?? CircleDashed;
          const mine = roles.includes(it.owner_role) || roles.includes("doctor") || roles.includes("hospital_admin");
          return (
            <li key={it.key} className="flex flex-wrap items-center gap-3 py-2.5">
              <Icon className={cn("size-5 shrink-0", it.status === "done" ? "text-success" : it.status === "not_applicable" ? "text-muted-foreground" : "text-warning")} />
              <div className="min-w-0 flex-1">
                <p className={cn("text-[13.5px] font-medium", it.status === "not_applicable" && "text-muted-foreground line-through")}>{it.label}{!it.required && <span className="ml-1 text-xs font-normal text-muted-foreground">(optional)</span>}</p>
                <p className="text-xs text-muted-foreground">{ROLE_LABELS[it.owner_role] ?? it.owner_role} · {it.verification === "auto" ? "verified from the record automatically" : "attested by owner"}
                  {it.evidence?.at ? ` · appointment ${fmtDateTime(it.evidence.at)}` : ""}{it.note ? ` · ${it.note}` : ""}{it.completed_at ? ` · ${fromNow(it.completed_at)}` : ""}</p>
              </div>
              {it.verification === "manual" && mine && it.status !== "done" && can("cases:work") && (
                <div className="flex gap-1"><Button size="xs" onClick={() => mark(it.key, "done")}>Done</Button>{it.status !== "not_applicable" && <Button size="xs" variant="ghost" onClick={() => mark(it.key, "not_applicable")}>N/A</Button>}</div>
              )}
              {it.key === "documentation" && it.status !== "done" && stay.encounter_id && can("clinical:write") && <Button size="xs" variant="outline" asChild><Link to={`/encounters/${stay.encounter_id}`}>Write summary</Link></Button>}
              {it.key === "follow_up" && it.status !== "done" && can("schedule:write") && <Button size="xs" variant="outline" asChild><Link to={`/schedule?patient=${stay.patient.id}`}>Book</Link></Button>}
            </li>);
        })}</ul></CardContent>
      </Card>
      <Card>
        <CardHeader className="flex-row items-center justify-between"><CardTitle>Patient instructions</CardTitle>{r.instructions.approved_at ? <Badge variant="success">Approved {fromNow(r.instructions.approved_at)}</Badge> : pending ? <AIBadge label="Draft — needs approval" /> : null}</CardHeader>
        <CardContent className="space-y-3">
          {r.instructions.approved_at && <p className="whitespace-pre-wrap rounded-lg border bg-muted/30 p-3 text-[13px]">{r.instructions.text}</p>}
          {!r.instructions.approved_at && draft !== null && (
            <>
              <p className="text-xs text-muted-foreground">{pending?.source === "ai" ? "Drafted by the AI provider from the signed discharge summary." : "Drafted from the signed discharge summary (rule-based template)."} Review and edit before approving — nothing reaches the patient until a clinician approves.</p>
              <Textarea rows={12} value={draft} onChange={(e) => setDraft(e.target.value)} disabled={!can("clinical:sign")} />
              {can("clinical:sign") && pending && <Button onClick={async () => { try { await post(`/adt/stays/${stay.id}/discharge/instructions/approve`, { approval_id: pending.id, text: draft }); toast.success("Instructions approved and shared in the portal"); onChange(); } catch (e) { toastError(e); } }}><CheckCircle2 />Approve & share with patient</Button>}
            </>
          )}
          {!r.instructions.approved_at && can("clinical:write") && (
            <Button variant="outline" loading={busy} onClick={async () => { setBusy(true); try { const d = await post<{ text: string }>(`/adt/stays/${stay.id}/discharge/instructions/draft`); setDraft(d.text); onChange(); } catch (e) { toastError(e); } finally { setBusy(false); } }}><Bot />{pending ? "Redraft" : "Draft instructions"}</Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ======================= Nursing panel (per stay) =======================

type Vit = { id: string; measured_at: string; systolic: number | null; diastolic: number | null; heart_rate: number | null; respiratory_rate: number | null; temperature_c: string | null; spo2: number | null; pain_score: number | null };
type Handoff = { id: string; shift: string; situation: string; background: string | null; assessment: string | null; recommendation: string | null; author: string; author_id: string; created_at: string; acknowledged_by: string | null; acknowledged_at: string | null };

function NursingPanel({ stay }: { stay: StayT }) {
  const { can, me } = useAuth();
  const qc = useQueryClient();
  const vit = useQuery({ queryKey: ["vitals", stay.patient.id], queryFn: () => get<Vit[]>(`/patients/${stay.patient.id}/vitals`, { limit: 12 }) });
  const ho = useQuery({ queryKey: ["handoffs", stay.id], queryFn: () => get<Handoff[]>(`/adt/stays/${stay.id}/handoffs`) });
  const [vOpen, setVOpen] = React.useState(false);
  const [hOpen, setHOpen] = React.useState(false);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader className="flex-row items-center justify-between"><CardTitle className="flex items-center gap-2"><HeartPulse className="size-4" />Vital signs</CardTitle>{can("clinical:write") && <Button size="sm" variant="outline" onClick={() => setVOpen(true)}>Record vitals</Button>}</CardHeader>
        {!vit.data?.length ? <CardContent><p className="text-[13px] text-muted-foreground">No vitals recorded.</p></CardContent> : (
          <Table><THead><TR><TH>Time</TH><TH>BP</TH><TH>HR</TH><TH>RR</TH><TH>Temp</TH><TH>SpO₂</TH><TH>Pain</TH></TR></THead>
            <TBody>{vit.data.map((v) => <TR key={v.id}><TD>{fmtDateTime(v.measured_at)}</TD><TD>{v.systolic ? `${v.systolic}/${v.diastolic}` : "—"}</TD><TD>{v.heart_rate ?? "—"}</TD><TD>{v.respiratory_rate ?? "—"}</TD><TD>{v.temperature_c ?? "—"}</TD>
              <TD className={cn(v.spo2 != null && v.spo2 < 92 && "font-semibold text-destructive")}>{v.spo2 ?? "—"}</TD><TD>{v.pain_score ?? "—"}</TD></TR>)}</TBody></Table>
        )}
      </Card>
      <Card>
        <CardHeader className="flex-row items-center justify-between"><CardTitle className="flex items-center gap-2"><Stethoscope className="size-4" />Shift handoffs (SBAR)</CardTitle>{can("nursing:write") && <Button size="sm" variant="outline" onClick={() => setHOpen(true)}>Write handoff</Button>}</CardHeader>
        <CardContent>{!ho.data?.length ? <p className="text-[13px] text-muted-foreground">No handoffs yet.</p> : (
          <ul className="space-y-3">{ho.data.map((h) => (
            <li key={h.id} className="rounded-lg border p-3 text-[13px]">
              <div className="mb-1 flex flex-wrap items-center gap-2"><Badge variant="outline">{titleCase(h.shift)} shift</Badge><span className="text-xs text-muted-foreground">{h.author} · {fmtDateTime(h.created_at)}</span>
                {h.acknowledged_at ? <Badge variant="success">Received by {h.acknowledged_by}</Badge> : can("nursing:write") && h.author_id !== me?.user.id && <Button size="xs" variant="outline" onClick={async () => { try { await post(`/handoffs/${h.id}/acknowledge`); qc.invalidateQueries({ queryKey: ["handoffs", stay.id] }); } catch (e) { toastError(e); } }}>Acknowledge</Button>}</div>
              {(["situation", "background", "assessment", "recommendation"] as const).map((k) => h[k] && <p key={k}><span className="font-medium">{k[0].toUpperCase()}:</span> {h[k]}</p>)}
            </li>))}</ul>
        )}</CardContent>
      </Card>
      <VitalsDialog open={vOpen} onOpenChange={setVOpen} stay={stay} />
      <HandoffDialog open={hOpen} onOpenChange={setHOpen} stay={stay} />
    </div>
  );
}

export function VitalsDialog({ open, onOpenChange, stay }: { open: boolean; onOpenChange: (o: boolean) => void; stay: StayT }) {
  const qc = useQueryClient();
  const [v, setV] = React.useState<Record<string, string>>({});
  const fields: [string, string][] = [["systolic", "Systolic"], ["diastolic", "Diastolic"], ["heart_rate", "Heart rate"], ["respiratory_rate", "Resp. rate"], ["temperature_c", "Temp °C"], ["spo2", "SpO₂ %"], ["pain_score", "Pain 0–10"]];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md"><DialogHeader><DialogTitle>Record vitals — {stay.patient.name}</DialogTitle></DialogHeader>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{fields.map(([k, l]) => <Field key={k} label={l}><Input inputMode="decimal" value={v[k] ?? ""} onChange={(e) => setV({ ...v, [k]: e.target.value })} /></Field>)}</div>
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={async () => {
            const body: Record<string, unknown> = { encounter_id: stay.encounter_id };
            Object.entries(v).forEach(([k, x]) => { if (x.trim()) body[k] = Number(x); });
            try { await post(`/patients/${stay.patient.id}/vitals`, body); toast.success("Vitals saved"); setV({}); onOpenChange(false); qc.invalidateQueries({ queryKey: ["vitals"] }); qc.invalidateQueries({ queryKey: ["nursing"] }); } catch (e) { toastError(e); }
          }}>Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function HandoffDialog({ open, onOpenChange, stay }: { open: boolean; onOpenChange: (o: boolean) => void; stay: StayT }) {
  const qc = useQueryClient();
  const hour = new Date().getHours();
  const [f, setF] = React.useState({ shift: hour < 15 && hour >= 7 ? "day" : hour < 23 && hour >= 15 ? "evening" : "night", situation: "", background: "", assessment: "", recommendation: "" });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg"><DialogHeader><DialogTitle>Shift handoff — {stay.patient.name}</DialogTitle><DialogDescription>SBAR. Saved notes can't be edited after the receiving nurse acknowledges them.</DialogDescription></DialogHeader>
        <Field label="Shift"><NativeSelect value={f.shift} onChange={(e) => setF({ ...f, shift: e.target.value })}><option value="day">Day</option><option value="evening">Evening</option><option value="night">Night</option></NativeSelect></Field>
        {(["situation", "background", "assessment", "recommendation"] as const).map((k) => <Field key={k} label={titleCase(k)} required={k === "situation"}><Textarea rows={2} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>)}
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={f.situation.trim().length < 3} onClick={async () => { try { await post(`/adt/stays/${stay.id}/handoffs`, { ...f, background: f.background || null, assessment: f.assessment || null, recommendation: f.recommendation || null }); toast.success("Handoff saved"); onOpenChange(false); qc.invalidateQueries({ queryKey: ["handoffs", stay.id] }); qc.invalidateQueries({ queryKey: ["nursing"] }); } catch (e) { toastError(e); } }}>Save handoff</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CareTeamPanel({ stayId }: { stayId: string }) {
  const qc = useQueryClient();
  const { can, me } = useAuth();
  const q = useQuery({ queryKey: ["careteam", stayId], queryFn: () => get<{ id: string; user_id: string; name: string; role: string; is_primary: boolean; since: string }[]>(`/adt/stays/${stayId}/care-team`) });
  const [role, setRole] = React.useState("nurse");
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between"><CardTitle className="flex items-center gap-2"><Users className="size-4" />Care team</CardTitle>
        {can("adt:write") && me && !q.data?.some((m) => m.user_id === me.user.id) && (
          <div className="flex gap-2"><NativeSelect className="h-9 w-40" value={role} onChange={(e) => setRole(e.target.value)} aria-label="My role">{["attending", "resident", "nurse", "case_manager", "pharmacist", "therapist"].map((r) => <option key={r} value={r}>{titleCase(r.replace("_", " "))}</option>)}</NativeSelect>
            <Button size="sm" onClick={async () => { try { await post(`/adt/stays/${stayId}/care-team`, { user_id: me.user.id, role }); qc.invalidateQueries({ queryKey: ["careteam", stayId] }); qc.invalidateQueries({ queryKey: ["nursing"] }); } catch (e) { toastError(e); } }}>Add me</Button></div>)}
      </CardHeader>
      <CardContent>{!q.data?.length ? <p className="text-[13px] text-muted-foreground">No care team members assigned yet.</p> : (
        <ul className="divide-y">{q.data.map((m) => <li key={m.id} className="flex items-center justify-between py-2 text-[13.5px]"><span className="font-medium">{m.name}</span><span className="text-muted-foreground">{titleCase(m.role.replace("_", " "))} · since {fromNow(m.since)}</span></li>)}</ul>
      )}</CardContent>
    </Card>
  );
}

// ======================= Nursing workspace =======================

export function NursingPage() {
  const [mine, setMine] = React.useState(false);
  const q = useQuery({ queryKey: ["nursing", mine], queryFn: () => get<NursingRow[]>("/nursing/patients", { mine: mine || undefined }), refetchInterval: 60_000 });
  const [vitFor, setVitFor] = React.useState<StayT | null>(null);
  const nav = useNavigate();
  const overdue = (q.data ?? []).filter((r) => r.vitals_overdue).length;
  return (
    <>
      <PageHeader title="Nursing" description="Your unit at a glance: beds, latest vitals, open tasks, handoffs and discharge progress." />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button onClick={() => setMine(false)} className={cn("rounded-md px-2.5 py-1 text-[13px] font-medium text-muted-foreground hover:bg-muted", !mine && "bg-accent text-accent-foreground")}>My units</button>
        <button onClick={() => setMine(true)} className={cn("rounded-md px-2.5 py-1 text-[13px] font-medium text-muted-foreground hover:bg-muted", mine && "bg-accent text-accent-foreground")}>My assigned patients</button>
        {overdue > 0 && <Badge variant="warning"><AlertTriangle />{overdue} with vitals older than 4 h</Badge>}
      </div>
      <Card className="overflow-hidden">
        {q.isLoading ? <LoadingRows /> : q.isError ? <ErrorState error={q.error} retry={q.refetch} /> : !q.data?.length ? <EmptyState icon={BedDouble} title={mine ? "You aren't on any care team yet" : "No patients on your units"} description={mine ? "Open a patient and choose Care team → Add me." : undefined} /> : (
          <Table><THead><TR><TH>Bed</TH><TH>Patient</TH><TH>Latest vitals</TH><TH>Tasks</TH><TH>Handoff</TH><TH>Discharge</TH><TH /></TR></THead>
            <TBody>{q.data.map((r) => (
              <TR key={r.id}>
                <TD className="font-semibold">{r.bed?.name ?? "—"}</TD>
                <TD><button className="text-left hover:underline" onClick={() => nav(`/inpatients/${r.id}`)}><p className="font-medium">{r.patient.name}</p><p className="text-xs text-muted-foreground">{r.reason} · LOS {losLabel(r.los_hours)}</p></button>{r.isolation && <Badge variant="warning" className="mt-1">{r.isolation} isolation</Badge>}</TD>
                <TD className={cn("text-[13px]", r.vitals_overdue && "text-warning")}>{r.vitals ? <>{r.vitals.bp ?? "—"} · HR {r.vitals.hr ?? "—"} · SpO₂ {r.vitals.spo2 ?? "—"}<p className="text-xs text-muted-foreground">{fromNow(r.vitals.measured_at)}</p></> : "None recorded"}</TD>
                <TD className="tabular">{r.open_tasks}</TD>
                <TD className="text-xs text-muted-foreground">{r.last_handoff_at ? fromNow(r.last_handoff_at) : "—"}</TD>
                <TD>{r.discharge ? <Badge variant={r.discharge.ready ? "success" : "warning"}>{r.discharge.done}/{r.discharge.total}</Badge> : r.status === "discharge_ordered" ? <Badge variant="info">Ordered</Badge> : "—"}</TD>
                <TD><Button size="xs" variant="outline" onClick={() => setVitFor(r)}>Vitals</Button></TD>
              </TR>))}</TBody></Table>
        )}
      </Card>
      {vitFor && <VitalsDialog open onOpenChange={(o) => !o && setVitFor(null)} stay={vitFor} />}
    </>
  );
}
