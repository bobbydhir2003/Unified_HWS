import { useQuery } from "@tanstack/react-query";
import { CalendarPlus, ClipboardList, Lock, UserPlus, Video } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { AppointmentStatusBadge, EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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

  return (
    <>
      {ctl.dialog}
      <PageHeader title="Front desk" description={`${clinic?.name ?? ""} · arrivals, rooming and checkout`}
        actions={<>
          <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} className="w-40" aria-label="Day" />
          {can("patients:write") && <Button variant="outline" asChild><Link to="/patients/new"><UserPlus />Register</Link></Button>}
          {can("schedule:write") && <Button onClick={() => setBooking(true)}><CalendarPlus />Book</Button>}
        </>} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by name or MRN" className="max-w-xs" aria-label="Filter queue" />
        <div className="flex flex-wrap gap-1.5 text-xs text-muted-foreground">
          {LANES.map((l) => <span key={l.key} className="rounded-full border bg-card px-2 py-0.5">{l.title}: <strong className="text-foreground">{all.filter((a) => l.statuses.includes(a.status)).length}</strong></span>)}
        </div>
      </div>
      {q.error ? <ErrorState error={q.error} retry={q.refetch} /> : q.isLoading ? <LoadingRows rows={6} /> : !q.data?.appointments.length ? (
        <Card><EmptyState icon={ClipboardList} title="No appointments for this day" action={can("schedule:write") && <Button variant="outline" onClick={() => setBooking(true)}><CalendarPlus />Book appointment</Button>} /></Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {LANES.map((lane) => {
            const items = all.filter((a) => lane.statuses.includes(a.status));
            return (
              <section key={lane.key} aria-labelledby={`lane-${lane.key}`} className="flex min-h-40 flex-col rounded-xl border bg-muted/40">
                <header className="flex items-center justify-between px-3.5 pb-2 pt-3">
                  <div><h2 id={`lane-${lane.key}`} className="text-[13.5px] font-semibold">{lane.title}</h2><p className="text-[11.5px] text-muted-foreground">{lane.hint}</p></div>
                  <span className="rounded-full bg-card px-2 py-0.5 text-xs font-semibold tabular shadow-xs">{items.length}</span>
                </header>
                <ul className="flex-1 space-y-2 px-2.5 pb-3">
                  {items.map((a) => {
                    const wait = a.status === "checked_in" ? minutesSince(a.checked_in_at) : a.status === "roomed" ? minutesSince(a.roomed_at) : null;
                    return (
                      <li key={a.id} className="rounded-lg border bg-card p-3 shadow-xs">
                        <div className="flex items-start gap-2">
                          <button onClick={() => setOpenId(a.id)} className="min-w-0 flex-1 text-left">
                            <span className="flex items-center gap-1.5 text-[13.5px] font-semibold hover:underline">
                              {a.patient.name}
                              {a.patient.is_restricted && <Lock className="size-3 text-warning" />}
                              {a.mode === "telehealth" && <Video className="size-3.5 text-primary" />}
                            </span>
                            <span className="block text-[11.5px] text-muted-foreground tabular">{fmtDob(a.patient.date_of_birth)} · {sexShort(a.patient.sex_at_birth)} · {a.patient.mrn}</span>
                          </button>
                          <span className="text-xs font-semibold tabular">{fmtTime(a.start_at, tz)}</span>
                        </div>
                        <p className="mt-1.5 truncate text-xs text-muted-foreground">{[a.appointment_type?.name, a.provider.name, a.room].filter(Boolean).join(" · ")}</p>
                        <div className="mt-2 flex items-center justify-between gap-2">
                          <AppointmentStatusBadge status={a.status} />
                          {wait !== null && <span className={cn("text-xs font-medium tabular", wait > 20 ? "text-destructive" : "text-muted-foreground")}>{wait} min</span>}
                        </div>
                        <div className="mt-2.5"><AppointmentButtons a={a} rooms={rooms} ctl={ctl} compact /></div>
                      </li>
                    );
                  })}
                  {!items.length && <li className="rounded-lg border border-dashed px-3 py-6 text-center text-xs text-muted-foreground">Empty</li>}
                </ul>
              </section>
            );
          })}
        </div>
      )}
      {missed.length > 0 && (
        <details className="mt-4 rounded-xl border bg-card p-3">
          <summary className="cursor-pointer text-[13px] font-medium">Cancelled & no-shows ({missed.length})</summary>
          <ul className="mt-2 divide-y">
            {missed.map((a) => (
              <li key={a.id} className="flex items-center gap-3 py-2 text-[13px]">
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
