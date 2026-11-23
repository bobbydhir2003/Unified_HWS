import { useQuery } from "@tanstack/react-query";
import { CalendarPlus, ClipboardList, Clock, Lock, UserPlus, Video } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { AppointmentStatusBadge, EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/tabs";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDob, fmtTime, minutesSince, sexShort } from "@/lib/format";
import { useRooms } from "@/lib/hooks";
import type { Appointment } from "@/lib/types";
import { todayIn } from "@/lib/tz";
import { cn } from "@/lib/utils";
import { AppointmentButtons, AppointmentDrawer, useAppointmentActions } from "./AppointmentActions";
import { AppointmentDialog } from "./AppointmentDialog";

type Queue = { date: string; timezone: string; counts: Record<string, number>; appointments: Appointment[] };

const FD_COLS = "grid grid-cols-[4.5rem_minmax(0,1fr)] items-center gap-x-4 gap-y-2 lg:grid-cols-[4.5rem_minmax(0,1.4fr)_minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1.6fr)]";

const LANES: { key: string; title: string; statuses: Appointment["status"][]; hint: string }[] = [
  { key: "upcoming", title: "Expected", statuses: ["scheduled", "confirmed"], hint: "Not yet arrived" },
  { key: "waiting", title: "Waiting room", statuses: ["checked_in"], hint: "Checked in, waiting to be roomed" },
  { key: "roomed", title: "Roomed / with provider", statuses: ["roomed", "in_progress"], hint: "In an exam room or visit" },
  { key: "done", title: "Ready for checkout / done", statuses: ["completed", "checked_out"], hint: "Visit finished" },
];

export function FrontDesk() {
  const { clinic, can } = useAuth();
  const tz = clinic?.timezone ?? "America/New_York";
  const [day, setDay] = React.useState(todayIn(tz));
  const [openId, setOpenId] = React.useState<string | null>(null);
  const [booking, setBooking] = React.useState(false);
  const [filter, setFilter] = React.useState("");
  const ctl = useAppointmentActions();
  const rooms = useRooms(clinic?.id);
  const q = useQuery({
    queryKey: ["queue", clinic?.id, day],
    queryFn: () => get<Queue>("/front-desk/queue", { clinic_id: clinic!.id, day }),
    enabled: !!clinic,
    refetchInterval: 20_000,
  });
  const all = (q.data?.appointments ?? []).filter((a) => !filter || a.patient.name.toLowerCase().includes(filter.toLowerCase()) || a.patient.mrn.includes(filter.toUpperCase()));
  const open = q.data?.appointments.find((a) => a.id === openId) ?? null;
  const missed = all.filter((a) => a.status === "cancelled" || a.status === "no_show");

  const [lane, setLane] = React.useState<string>("all");
  const active = all.filter((a) => a.status !== "cancelled" && a.status !== "no_show");
  const laneOf = (a: Appointment) => LANES.find((l) => l.statuses.includes(a.status))?.key;
  const rows = (lane === "all" ? active : active.filter((a) => laneOf(a) === lane)).slice().sort((x, y) => x.start_at.localeCompare(y.start_at));

  return (
    <>
      {ctl.dialog}
      <PageHeader title="Front desk" eyebrow={`${clinic?.name ?? ""} · arrivals, rooming and checkout`}
        actions={<>
          <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} className="w-40" aria-label="Day" />
          {can("patients:write") && <Button variant="outline" asChild><Link to="/patients/new"><UserPlus />Register</Link></Button>}
          {can("schedule:write") && <Button onClick={() => setBooking(true)}><CalendarPlus />Book</Button>}
        </>}
        toolbar={<>
          <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by name or MRN" className="h-8 max-w-xs" aria-label="Filter queue" />
          <Segmented label="Show arrivals by status" value={lane} onChange={setLane}
            options={[{ value: "all", label: "All", count: active.length }, ...LANES.map((l) => ({ value: l.key, label: l.title, count: active.filter((a) => l.statuses.includes(a.status)).length }))]} />
        </>} />
      {q.error ? <ErrorState error={q.error} retry={q.refetch} /> : q.isLoading ? <LoadingRows rows={6} /> : !q.data?.appointments.length ? (
        <Card><EmptyState icon={ClipboardList} title="No appointments for this day" action={can("schedule:write") && <Button variant="outline" onClick={() => setBooking(true)}><CalendarPlus />Book appointment</Button>} /></Card>
      ) : (
        <Card className="overflow-hidden">
          <ul className="divide-y" aria-label="Arrivals">
            <li aria-hidden className={cn(FD_COLS, "hidden bg-subtle px-4 py-2 text-label font-medium text-muted-foreground lg:grid")}>
              <span>Time</span><span>Patient</span><span>Visit</span><span>Status</span><span>Actions</span>
            </li>
            {!rows.length && <li><EmptyState compact icon={ClipboardList} title="Nobody in this status" /></li>}
            {rows.map((a) => {
              const wait = a.status === "checked_in" ? minutesSince(a.checked_in_at) : a.status === "roomed" ? minutesSince(a.roomed_at) : null;
              return (
                <li key={a.id} className={cn(FD_COLS, "px-4 py-(--row-y) text-table")}>
                  <span className="font-semibold tabular text-heading">{fmtTime(a.start_at, tz)}</span>
                  <span className="min-w-0">
                    <button onClick={() => setOpenId(a.id)} className="flex items-center gap-1.5 text-left text-body font-semibold text-heading hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
                      {a.patient.name}
                      {a.patient.is_restricted && <Lock className="size-3 text-warning" aria-label="Restricted chart" />}
                      {a.mode === "telehealth" && <Video className="size-3.5 text-primary" aria-label="Video visit" />}
                    </button>
                    <span className="block text-label tabular text-muted-foreground">{fmtDob(a.patient.date_of_birth)} · {sexShort(a.patient.sex_at_birth)} · MRN {a.patient.mrn}</span>
                  </span>
                  <span className="min-w-0 text-muted-foreground"><span className="block truncate text-foreground">{a.appointment_type?.name ?? "Visit"}</span><span className="block truncate text-label">{[a.provider.name, a.room].filter(Boolean).join(" · ")}</span></span>
                  <span className="flex flex-wrap items-center gap-2">
                    <AppointmentStatusBadge status={a.status} />
                    {wait !== null && <span className={cn("inline-flex items-center gap-1 text-label font-medium tabular", wait > 20 ? "text-warning-foreground" : "text-muted-foreground")}><Clock className="size-3" aria-hidden />{wait} min{wait > 20 ? " waiting" : ""}</span>}
                  </span>
                  <span className="min-w-0"><AppointmentButtons a={a} rooms={rooms} ctl={ctl} compact /></span>
                </li>
              );
            })}
          </ul>
        </Card>
      )}
      {missed.length > 0 && (
        <details className="mt-4 rounded-lg border bg-card p-3">
          <summary className="cursor-pointer text-table font-medium">Cancelled & no-shows ({missed.length})</summary>
          <ul className="mt-2 divide-y">
            {missed.map((a) => (
              <li key={a.id} className="flex items-center gap-3 py-2 text-table">
                <span className="w-16 tabular text-muted-foreground">{fmtTime(a.start_at, tz)}</span>
                <button onClick={() => setOpenId(a.id)} className="flex-1 text-left font-medium hover:underline">{a.patient.name}</button>
                <AppointmentStatusBadge status={a.status} />
              </li>
            ))}
          </ul>
        </details>
      )}
      <AppointmentDrawer appt={open} onOpenChange={(o) => !o && setOpenId(null)} />
      <AppointmentDialog open={booking} onOpenChange={setBooking} />
    </>
  );
}
