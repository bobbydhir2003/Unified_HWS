import { useQueryClient } from "@tanstack/react-query";
import { Ban, CalendarClock, Check, DoorOpen, ExternalLink, LogIn, LogOut, Stethoscope, UserX, Video } from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { AppointmentStatusBadge, KeyValue, toastError, useConfirm } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, SheetContent } from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/menu";
import { Dialog as D } from "radix-ui";
import { post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useRooms } from "@/lib/hooks";
import { fmtDateTime, fmtDob, fmtTime, sexShort } from "@/lib/format";
import type { Appointment } from "@/lib/types";
import { AppointmentDialog } from "./AppointmentDialog";

export function useAppointmentActions() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { can, membership } = useAuth();
  const { confirm, dialog } = useConfirm();
  const [busy, setBusy] = React.useState<string | null>(null);

  const invalidate = () => {
    for (const k of ["appointments", "queue", "dashboard", "notifications"]) qc.invalidateQueries({ queryKey: [k] });
  };
  const act = async (a: Appointment, action: string, extra: Record<string, unknown> = {}) => {
    setBusy(`${a.id}:${action}`);
    try {
      const r = await post<Appointment>(`/appointments/${a.id}/status`, { action, ...extra });
      invalidate();
      qc.invalidateQueries({ queryKey: ["patient-appts", a.patient.id] });
      return r;
    } catch (e) { toastError(e); return null; } finally { setBusy(null); }
  };

  const actions = {
    checkIn: async (a: Appointment) => { const r = await act(a, "check_in"); if (r) toast.success(`${a.patient.name} checked in`); return r; },
    confirm: (a: Appointment) => act(a, "confirm"),
    room: async (a: Appointment, room: string) => { const r = await act(a, "room", { room }); if (r) toast.success(`Roomed in ${room}`); return r; },
    checkOut: async (a: Appointment) => {
      if (a.status !== "completed" && a.status !== "checked_out") {
        const ok = await confirm({ title: "Check out before the visit is completed?", description: "The visit note hasn't been signed and completed yet. You can still check the patient out; the clinician can finish documentation afterwards.", confirmLabel: "Check out" });
        if (!ok) return null;
      }
      const r = await act(a, "check_out");
      if (r) toast.success(`${a.patient.name} checked out`);
      return r;
    },
    cancel: async (a: Appointment) => {
      const reason = await confirm({ title: `Cancel ${a.patient.name}'s appointment?`, description: `${fmtDateTime(a.start_at)} with ${a.provider.name}`, requireReason: true, reasonLabel: "Cancellation reason", destructive: true, confirmLabel: "Cancel appointment" });
      if (!reason) return null;
      const r = await act(a, "cancel", { reason });
      if (r) toast.success("Appointment cancelled");
      return r;
    },
    noShow: async (a: Appointment) => {
      if (!(await confirm({ title: `Mark ${a.patient.name} as a no-show?`, destructive: true, confirmLabel: "Mark no-show" }))) return null;
      return act(a, "no_show");
    },
    startVisit: async (a: Appointment) => {
      if (a.encounter_id) { navigate(`/encounters/${a.encounter_id}`); return; }
      setBusy(`${a.id}:start`);
      try {
        const e = await post<{ id: string }>("/encounters", { patient_id: a.patient.id, appointment_id: a.id });
        invalidate();
        navigate(`/encounters/${e.id}`);
      } catch (err) { toastError(err); } finally { setBusy(null); }
    },
  };
  const canWrite = can("schedule:write");
  const canClinical = can("clinical:write") && !!membership?.provider_id;
  return { actions, busy, dialog, canWrite, canClinical };
}

export function RoomPicker({ rooms, onPick, disabled, loading }: { rooms: string[]; onPick: (r: string) => void; disabled?: boolean; loading?: boolean }) {
  const [room, setRoom] = React.useState(rooms[0] ?? "Exam 1");
  const [open, setOpen] = React.useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild><Button size="xs" variant="outline" disabled={disabled} loading={loading}><DoorOpen />Room</Button></PopoverTrigger>
      <PopoverContent className="w-56 space-y-2">
        <p className="text-table font-medium">Assign room</p>
        <NativeSelect value={room} onChange={(e) => setRoom(e.target.value)} aria-label="Room">
          {(rooms.length ? rooms : ["Exam 1"]).map((r) => <option key={r}>{r}</option>)}
        </NativeSelect>
        <Button size="sm" className="w-full" onClick={() => { onPick(room); setOpen(false); }}>Assign</Button>
      </PopoverContent>
    </Popover>
  );
}

/** Contextual actions for an appointment given its status. */
export function AppointmentButtons({ a, rooms, ctl, compact }: { a: Appointment; rooms: string[]; ctl: ReturnType<typeof useAppointmentActions>; compact?: boolean }) {
  const { actions, busy, canWrite, canClinical } = ctl;
  const b = (k: string) => busy === `${a.id}:${k}`;
  const s = a.status;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {canWrite && s === "scheduled" && !compact && <Button size="xs" variant="outline" onClick={() => actions.confirm(a)} loading={b("confirm")}><Check />Confirm</Button>}
      {canWrite && (s === "scheduled" || s === "confirmed") && <Button size="xs" variant="outline" onClick={() => actions.checkIn(a)} loading={b("check_in")}><LogIn />Check in</Button>}
      {canWrite && (s === "checked_in" || s === "roomed") && a.mode === "in_person" && <RoomPicker rooms={rooms} onPick={(r) => actions.room(a, r)} loading={b("room")} />}
      {canClinical && a.mode === "telehealth" && !["cancelled", "no_show", "checked_out", "completed"].includes(s) && (
        <Button size="xs" variant="soft" asChild><Link to={`/telehealth/${a.id}`}><Video />Join video</Link></Button>
      )}
      {canClinical && (["checked_in", "roomed", "in_progress"].includes(s) || (a.mode === "telehealth" && ["confirmed", "scheduled"].includes(s))) && (
        <Button size="xs" variant={s === "in_progress" ? "soft" : "outline"} onClick={() => actions.startVisit(a)} loading={b("start")}>
          {a.mode === "telehealth" ? <Video /> : <Stethoscope />}{a.encounter_id ? "Open visit" : "Start visit"}
        </Button>
      )}
      {!canClinical && a.encounter_id && <Button size="xs" variant="ghost" asChild><Link to={`/encounters/${a.encounter_id}`}><ExternalLink />Visit</Link></Button>}
      {canWrite && ["checked_in", "roomed", "in_progress", "completed"].includes(s) && <Button size="xs" variant="outline" onClick={() => actions.checkOut(a)} loading={b("check_out")}><LogOut />Check out</Button>}
    </div>
  );
}

export function AppointmentDrawer({ appt, onOpenChange }: { appt: Appointment | null; onOpenChange: (o: boolean) => void }) {
  const ctl = useAppointmentActions();
  const [resched, setResched] = React.useState(false);
  const rooms = useRooms(appt?.clinic.id);
  const a = appt;
  return (
    <>
      {ctl.dialog}
      <Dialog open={!!a} onOpenChange={onOpenChange}>
        <SheetContent aria-describedby={undefined}>
          {a && (
            <div className="flex h-full flex-col">
              <div className="border-b px-6 py-5">
                <D.Title className="text-base font-semibold">{a.appointment_type?.name ?? "Appointment"}</D.Title>
                <p className="mt-0.5 text-table text-muted-foreground">{fmtDateTime(a.start_at)} – {fmtTime(a.end_at)}</p>
                <div className="mt-2"><AppointmentStatusBadge status={a.status} /></div>
              </div>
              <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
                <div className="rounded-lg border p-3">
                  <Link to={`/patients/${a.patient.id}`} className="font-medium text-primary hover:underline">{a.patient.name}</Link>
                  <p className="text-xs text-muted-foreground tabular">DOB {fmtDob(a.patient.date_of_birth)} · {sexShort(a.patient.sex_at_birth)} · MRN {a.patient.mrn}</p>
                  {a.patient.phone && <p className="text-xs text-muted-foreground">{a.patient.phone}</p>}
                </div>
                <dl className="grid grid-cols-2 gap-4">
                  <KeyValue label="Provider" value={a.provider.name} />
                  <KeyValue label="Location" value={a.clinic.name} />
                  <KeyValue label="Mode" value={a.mode === "telehealth" ? "Telehealth" : "In person"} />
                  <KeyValue label="Room" value={a.room} />
                  <KeyValue label="Reason" value={a.reason} className="col-span-2" />
                  {a.notes && <KeyValue label="Scheduling notes" value={a.notes} className="col-span-2" />}
                  <KeyValue label="Checked in" value={a.checked_in_at ? fmtTime(a.checked_in_at) : null} />
                  <KeyValue label="Checked out" value={a.checked_out_at ? fmtTime(a.checked_out_at) : null} />
                  {a.cancel_reason && <KeyValue label="Cancellation reason" value={a.cancel_reason} className="col-span-2" />}
                </dl>
              </div>
              <div className="space-y-2 border-t px-6 py-4">
                <AppointmentButtons a={a} rooms={rooms} ctl={ctl} />
                {ctl.canWrite && ["scheduled", "confirmed"].includes(a.status) && (
                  <div className="flex flex-wrap gap-1.5">
                    <Button size="xs" variant="outline" onClick={() => setResched(true)}><CalendarClock />Reschedule</Button>
                    <Button size="xs" variant="ghost" onClick={async () => { if (await ctl.actions.noShow(a)) onOpenChange(false); }}><UserX />No-show</Button>
                    <Button size="xs" variant="ghost" className="text-destructive" onClick={async () => { if (await ctl.actions.cancel(a)) onOpenChange(false); }}><Ban />Cancel</Button>
                  </div>
                )}
              </div>
            </div>
          )}
        </SheetContent>
      </Dialog>
      <AppointmentDialog open={resched} onOpenChange={setResched} editing={a} onSaved={() => onOpenChange(false)} />
    </>
  );
}
