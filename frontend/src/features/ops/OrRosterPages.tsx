import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, ChevronLeft, ChevronRight, Plus, Repeat, Scissors, UserPlus, Users } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, LoadingRows, PageHeader, toastError } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect } from "@/components/ui/input";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtTime } from "@/lib/format";
import { cn, titleCase } from "@/lib/utils";
import { PatientPicker } from "../inpatient/shared";

type OrCase = { id: string; room: { id: string; name: string }; patient: { id: string; name: string; mrn: string }; surgeon: string; procedure: string; priority: string; anesthesia: string; start_at: string; end_at: string; blocked_until: string; status: string };
type OrDay = { day: string; timezone: string; rooms: { id: string; name: string; booked_hours: number; utilization_pct: number }[]; cases: OrCase[]; utilization_basis: string };

const isoDay = (d: Date) => d.toISOString().slice(0, 10);
/** "+HH:MM" offset of a timezone right now (cases are scheduled in the facility's local time). */
function offsetFor(tz?: string) {
  if (!tz) return "";
  const n = new Date();
  const local = new Date(n.toLocaleString("en-US", { timeZone: tz }));
  const utc = new Date(n.toLocaleString("en-US", { timeZone: "UTC" }));
  const mins = Math.round((local.getTime() - utc.getTime()) / 60000);
  const sign = mins >= 0 ? "+" : "-";
  const a = Math.abs(mins);
  return `${sign}${String(Math.floor(a / 60)).padStart(2, "0")}:${String(a % 60).padStart(2, "0")}`;
}
const HOURS = Array.from({ length: 13 }, (_, i) => 7 + i);

export function OrSchedulePage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [day, setDay] = React.useState(() => { const d = new Date(); d.setDate(d.getDate() + 1); return isoDay(d); });
  const q = useQuery({ queryKey: ["or", day], queryFn: () => get<OrDay>("/or/schedule", { day }) });
  const providers = useQuery({ queryKey: ["providers"], queryFn: () => get<{ id: string; name: string }[]>("/providers") });
  const [open, setOpen] = React.useState(false);
  const [patient, setPatient] = React.useState<Parameters<typeof PatientPicker>[0]["value"]>(null);
  const [f, setF] = React.useState({ room: "", surgeon: "", procedure: "", time: "08:00", minutes: "90", turnover: "30", priority: "elective" });
  const shift = (n: number) => { const d = new Date(day + "T12:00:00"); d.setDate(d.getDate() + n); setDay(isoDay(d)); };
  const act = async (id: string, to: string) => {
    const reason = to === "cancelled" ? window.prompt("Reason for cancelling?") : null;
    if (to === "cancelled" && !reason) return;
    try { await post(`/or/cases/${id}/status`, { to, reason }); qc.invalidateQueries({ queryKey: ["or"] }); } catch (e) { toastError(e); }
  };
  const tz = q.data?.timezone;
  const pos = (iso: string) => {
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: tz, hour: "numeric", minute: "numeric", hourCycle: "h23" }).formatToParts(new Date(iso));
    const h = Number(parts.find((p) => p.type === "hour")?.value ?? 0) + Number(parts.find((p) => p.type === "minute")?.value ?? 0) / 60;
    return Math.min(100, Math.max(0, ((h - 7) / 12) * 100));
  };
  return (
    <>
      <PageHeader title="Operating rooms" description="Surgical schedule by room. The database prevents double-booking a room (including turnover) or a surgeon."
        actions={<div className="flex items-center gap-2"><Button variant="outline" size="icon" onClick={() => shift(-1)} aria-label="Previous day"><ChevronLeft /></Button>
          <Input type="date" className="w-40" value={day} onChange={(e) => setDay(e.target.value)} aria-label="Day" /><Button variant="outline" size="icon" onClick={() => shift(1)} aria-label="Next day"><ChevronRight /></Button>
          {(can("or:manage") || can("orders:sign")) && <Button onClick={() => setOpen(true)}><Plus />Schedule case</Button>}</div>} />
      {!q.data ? <LoadingRows rows={5} /> : (
        <Card className="overflow-x-auto">
          <div className="min-w-[900px]">
            <div className="ml-40 flex border-b text-xs text-muted-foreground">{HOURS.map((h) => <div key={h} className="flex-1 border-l px-1 py-1.5">{h}:00</div>)}</div>
            {q.data.rooms.map((r) => (
              <div key={r.id} className="flex border-b last:border-0">
                <div className="w-40 shrink-0 px-3 py-3"><p className="text-body font-medium">{r.name}</p><p className="text-xs text-muted-foreground">{r.booked_hours} h · {r.utilization_pct}%</p></div>
                <div className="relative h-16 flex-1">
                  {HOURS.map((h, i) => <div key={h} className="absolute inset-y-0 border-l border-dashed border-border/60" style={{ left: `${(i / 12) * 100}%` }} />)}
                  {q.data.cases.filter((c) => c.room.id === r.id && c.status !== "cancelled").map((c) => (
                    <div key={c.id} className="absolute inset-y-1.5" style={{ left: `${pos(c.start_at)}%`, width: `${Math.max(pos(c.blocked_until) - pos(c.start_at), 4)}%` }}>
                      <div className="flex h-full">
                        <button className={cn("h-full grow overflow-hidden rounded-l-md border px-2 py-1 text-left text-label", c.status === "in_room" ? "border-primary bg-primary/15" : c.status === "completed" ? "border-success/40 bg-success-soft" : "border-primary/30 bg-accent")}
                          style={{ flexBasis: `${((new Date(c.end_at).getTime() - new Date(c.start_at).getTime()) / (new Date(c.blocked_until).getTime() - new Date(c.start_at).getTime())) * 100}%` }}
                          title={`${c.procedure} — ${c.patient.name} (${c.surgeon}) ${fmtTime(c.start_at)}–${fmtTime(c.end_at)}`}
                          onClick={() => { if (c.status === "scheduled" && window.confirm(`${c.procedure}: mark patient in room? (Cancel to see other options)`)) act(c.id, "in_room"); else if (c.status === "in_room") act(c.id, "completed"); else if (c.status === "scheduled" && window.confirm("Cancel this case?")) act(c.id, "cancelled"); }}>
                          <p className="truncate font-medium">{c.procedure}</p><p className="truncate text-muted-foreground">{c.patient.name} · {c.surgeon.split(",")[0]}</p>
                        </button>
                        <div className="h-full grow rounded-r-md bg-muted/70" title="Turnover" />
                      </div>
                    </div>))}
                </div>
              </div>))}
            {!q.data.rooms.length && <EmptyState icon={Scissors} title="No operating rooms configured" />}
          </div>
          <p className="border-t px-4 py-2 text-xs text-muted-foreground">Grey = turnover. Utilization = {q.data.utilization_basis}. Click a case to advance its status.</p>
        </Card>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent size="md"><DialogHeader><DialogTitle>Schedule surgical case</DialogTitle><DialogDescription>{day}</DialogDescription></DialogHeader>
          <Field label="Patient" required><PatientPicker value={patient} onChange={setPatient} /></Field>
          <Field label="Procedure" required><Input value={f.procedure} onChange={(e) => setF({ ...f, procedure: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Room"><NativeSelect value={f.room} onChange={(e) => setF({ ...f, room: e.target.value })}><option value="">Choose…</option>{q.data?.rooms.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</NativeSelect></Field>
            <Field label="Surgeon"><NativeSelect value={f.surgeon} onChange={(e) => setF({ ...f, surgeon: e.target.value })}><option value="">Choose…</option>{providers.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</NativeSelect></Field>
            <Field label="Start"><Input type="time" value={f.time} onChange={(e) => setF({ ...f, time: e.target.value })} /></Field>
            <Field label="Duration (min)"><Input inputMode="numeric" value={f.minutes} onChange={(e) => setF({ ...f, minutes: e.target.value })} /></Field>
            <Field label="Turnover (min)"><Input inputMode="numeric" value={f.turnover} onChange={(e) => setF({ ...f, turnover: e.target.value })} /></Field>
            <Field label="Priority"><NativeSelect value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}><option value="elective">Elective</option><option value="urgent">Urgent</option><option value="emergent">Emergent</option></NativeSelect></Field>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button disabled={!patient || !f.room || !f.surgeon || f.procedure.trim().length < 3} onClick={async () => {
              try { await post("/or/cases", { or_room_id: f.room, patient_id: patient!.id, surgeon_provider_id: f.surgeon, procedure: f.procedure, priority: f.priority,
                start_at: `${day}T${f.time}:00${offsetFor(tz)}`, duration_minutes: Number(f.minutes), turnover_minutes: Number(f.turnover) });
                toast.success("Case scheduled"); setOpen(false); qc.invalidateQueries({ queryKey: ["or"] }); } catch (e) { toastError(e); }
            }}>Schedule</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

type ShiftT = { id: string; user_id: string; name: string; role: string; department_id: string; department: string; start_at: string; end_at: string };
type Gap = { department_id: string; department: string; role: string; window: string; start: string; end: string; required: number; scheduled: number; short: number };
type Roster = { shifts: ShiftT[]; gaps: Gap[]; swaps: { id: string; shift_id: string; status: string; reason: string | null; requested_by_id: string; target_user_id: string | null }[]; rules: { min_rest_hours: number; max_week_hours: number } };
type Cand = { user_id: string; name: string; reasons: string[]; week_hours: number };

export function RosterPage() {
  const { can, me } = useAuth();
  const qc = useQueryClient();
  const manage = can("roster:manage");
  const depts = useQuery({ queryKey: ["departments", "all"], queryFn: () => get<{ id: string; name: string; kind: string }[]>("/departments"), enabled: manage });
  const [dept, setDept] = React.useState("");
  const q = useQuery({ queryKey: ["roster", dept], queryFn: () => get<Roster>("/roster", { days: 3, department_id: dept || undefined }) });
  const [fill, setFill] = React.useState<Gap | null>(null);
  const cands = useQuery({ queryKey: ["roster", "suggest", fill?.start, fill?.department_id], queryFn: () => get<{ candidates: Cand[]; method: string }>("/roster/suggest", { department_id: fill!.department_id, role: fill!.role, start: fill!.start, end: fill!.end }), enabled: !!fill });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["roster"] }); qc.invalidateQueries({ queryKey: ["cases"] }); };
  const r = q.data;
  const byDay = React.useMemo(() => {
    const m = new Map<string, ShiftT[]>();
    (r?.shifts ?? []).forEach((s) => { const k = new Date(s.start_at).toDateString(); m.set(k, [...(m.get(k) ?? []), s]); });
    return [...m.entries()];
  }, [r]);
  return (
    <>
      <PageHeader title={manage ? "Staff roster" : "My shifts"} description={`Hard rules: no overlapping shifts, ≥ ${r?.rules.min_rest_hours ?? 10} h rest, ≤ ${r?.rules.max_week_hours ?? 48} h per 7 days, time off and credentials respected. Suggestions explain themselves; managers decide.`}
        actions={manage ? <NativeSelect className="w-56" value={dept} onChange={(e) => setDept(e.target.value)} aria-label="Department"><option value="">All departments</option>{depts.data?.filter((d) => ["inpatient", "icu", "emergency"].includes(d.kind)).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</NativeSelect> : undefined} />
      {!r ? <LoadingRows rows={6} /> : (
        <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
          <Card className="overflow-hidden"><CardHeader><CardTitle className="flex items-center gap-2"><CalendarClock className="size-4" />Next 3 days</CardTitle></CardHeader>
            <CardContent className="space-y-4">{!byDay.length ? <EmptyState icon={Users} title="No shifts" /> : byDay.map(([d, shifts]) => (
              <div key={d}><p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{d}</p>
                <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">{shifts.map((s) => (
                  <div key={s.id} className={cn("rounded-lg border px-3 py-2 text-table", s.user_id === me?.user.id && "border-primary/40 bg-accent/50")}>
                    <p className="font-medium">{s.name}</p><p className="text-xs text-muted-foreground">{s.department} · {titleCase(s.role)} · {fmtTime(s.start_at)}–{fmtTime(s.end_at)}</p>
                    {s.user_id === me?.user.id && <button className="mt-1 inline-flex items-center gap-1 text-xs text-primary hover:underline" onClick={async () => { const reason = window.prompt("Why do you need cover?"); if (reason === null) return; try { await post("/roster/swaps", { shift_id: s.id, reason }); toast.success("Offered for swap"); refresh(); } catch (e) { toastError(e); } }}><Repeat className="size-3" />Offer swap</button>}
                  </div>))}</div></div>))}</CardContent></Card>
          <div className="space-y-4">
            {manage && <Card><CardHeader><CardTitle>Coverage gaps</CardTitle></CardHeader><CardContent>{!r.gaps.length ? <p className="text-table text-muted-foreground">All shifts meet minimum staffing.</p> : (
              <ul className="space-y-2">{r.gaps.map((g) => (
                <li key={g.department_id + g.start + g.role} className="rounded-lg border border-warning/50 bg-warning-soft/30 p-2.5 text-table">
                  <p className="font-medium">{g.department}: {g.short} {g.role} short</p><p className="text-xs text-muted-foreground">{titleCase(g.window)} · {new Date(g.start).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" })} · {g.scheduled}/{g.required}</p>
                  <Button size="xs" variant="outline" className="mt-1.5" onClick={() => setFill(g)}><UserPlus />Find staff</Button>
                </li>))}</ul>)}</CardContent></Card>}
            <Card><CardHeader><CardTitle>Swap requests</CardTitle></CardHeader><CardContent>{!r.swaps.length ? <p className="text-table text-muted-foreground">None open.</p> : (
              <ul className="space-y-2">{r.swaps.map((w) => {
                const s = r.shifts.find((x) => x.id === w.shift_id);
                return (
                  <li key={w.id} className="rounded-lg border p-2.5 text-table"><p className="font-medium">{s ? `${s.name} · ${s.department} ${fmtTime(s.start_at)}` : "Shift"}</p><p className="text-xs text-muted-foreground">{w.reason} · {w.status}</p>
                    <div className="mt-1.5 flex gap-1">{w.status === "open" && w.requested_by_id !== me?.user.id && <Button size="xs" variant="outline" onClick={async () => { try { await post(`/roster/swaps/${w.id}/accept`); toast.success("You accepted — waiting for manager approval"); refresh(); } catch (e) { toastError(e); } }}>Take shift</Button>}
                      {w.status === "accepted" && manage && <><Button size="xs" onClick={async () => { try { await post(`/roster/swaps/${w.id}/decide`, { approve: true }); toast.success("Swap approved"); refresh(); } catch (e) { toastError(e); } }}>Approve</Button><Button size="xs" variant="ghost" onClick={async () => { try { await post(`/roster/swaps/${w.id}/decide`, { approve: false }); refresh(); } catch (e) { toastError(e); } }}>Reject</Button></>}</div>
                  </li>);
              })}</ul>)}</CardContent></Card>
          </div>
        </div>
      )}
      <Dialog open={!!fill} onOpenChange={(o) => !o && setFill(null)}>
        <DialogContent size="md"><DialogHeader><DialogTitle>Fill {fill?.department} {fill?.window} shift</DialogTitle><DialogDescription>{cands.data?.method}</DialogDescription></DialogHeader>
          {!cands.data ? <LoadingRows rows={3} /> : !cands.data.candidates.length ? <p className="text-table">No eligible staff without breaking a rule. Consider float pool or agency; overrides require a documented reason.</p> : (
            <ul className="divide-y">{cands.data.candidates.map((c) => (
              <li key={c.user_id} className="flex items-center gap-3 py-2"><div className="flex-1"><p className="text-body font-medium">{c.name}</p><p className="text-xs text-muted-foreground">{c.reasons.join(" · ")}</p></div>
                <Button size="sm" onClick={async () => { try { await post("/roster/shifts", { user_id: c.user_id, department_id: fill!.department_id, role: fill!.role, start_at: fill!.start, end_at: fill!.end }); toast.success(`${c.name} scheduled`); setFill(null); refresh(); } catch (e) { toastError(e); } }}>Assign</Button></li>))}</ul>
          )}
          <DialogFooter><Button variant="outline" onClick={() => setFill(null)}>Close</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

