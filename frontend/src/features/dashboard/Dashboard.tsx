import { useQuery } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { CalendarDays, CalendarPlus, Clock, FilePenLine, Stethoscope, UserPlus, UsersRound, Video } from "lucide-react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { AppointmentStatusBadge, EmptyState, ErrorState, LoadingRows, PageHeader, Stat } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/misc";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtTime, minutesSince } from "@/lib/format";
import type { AppointmentStatus } from "@/lib/types";

type DashboardData = {
  date: string;
  appointments?: {
    total: number;
    by_status: Record<string, number>;
    waiting: { id: string; patient: string; patient_id: string; status: AppointmentStatus; checked_in_at: string; room: string | null; provider: string }[];
    next: { id: string; patient: string; patient_id: string; start_at: string; status: AppointmentStatus; type: string | null; reason: string | null; provider: string; mode: string }[];
  };
  appointments_7d?: { date: string; count: number }[];
  clinical?: { open_encounters: { id: string; patient: string; patient_id: string; started_at: string; chief_complaint: string | null }[]; unsigned_notes: number };
  patients?: { total: number; new_30d: number };
  admin?: { pending_invitations: number };
};

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export function Dashboard() {
  const { me, clinic, can } = useAuth();
  const q = useQuery({ queryKey: ["dashboard", clinic?.id], queryFn: () => get<DashboardData>("/dashboard", { clinic_id: clinic?.id }), refetchInterval: 60_000 });
  const d = q.data;
  const a = d?.appointments;
  const waitingCount = (a?.by_status.checked_in ?? 0) + (a?.by_status.roomed ?? 0);
  const done = (a?.by_status.checked_out ?? 0) + (a?.by_status.completed ?? 0);

  return (
    <>
      <PageHeader
        title={`${greeting()}, ${me?.user.first_name}`}
        description={`${format(new Date(), "EEEE, MMMM d")}${clinic ? ` · ${clinic.name}` : ""}`}
        actions={
          <>
            {can("patients:write") && <Button variant="outline" asChild><Link to="/patients/new"><UserPlus />Register patient</Link></Button>}
            {can("schedule:write") && <Button asChild><Link to="/schedule?new=1"><CalendarPlus />Book appointment</Link></Button>}
          </>
        }
      />
      {q.error ? <ErrorState error={q.error} retry={q.refetch} /> : (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {q.isLoading ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[104px] rounded-xl" />) : (
              <>
                {a && <Stat label="Appointments today" value={a.total} sub={`${done} completed`} icon={CalendarDays} />}
                {a && <Stat label="In clinic now" value={waitingCount} sub={`${a.by_status.in_progress ?? 0} with provider`} icon={Clock} tone="warning" />}
                {d?.clinical && <Stat label="Open visits" value={d.clinical.open_encounters.length} sub={`${d.clinical.unsigned_notes} unsigned notes`} icon={FilePenLine} tone="ai" />}
                {d?.patients && <Stat label="Active patients" value={d.patients.total.toLocaleString()} sub={`+${d.patients.new_30d} in last 30 days`} icon={UsersRound} tone="success" />}
                {!d?.clinical && d?.admin && <Stat label="Pending invitations" value={d.admin.pending_invitations} icon={UserPlus} />}
              </>
            )}
          </div>

          <div className="grid gap-5 xl:grid-cols-[1.6fr_1fr]">
            {a && (
              <Card>
                <CardHeader>
                  <div><CardTitle>Up next</CardTitle><CardDescription>Remaining appointments today</CardDescription></div>
                  <Button variant="ghost" size="sm" asChild><Link to="/schedule">Open schedule</Link></Button>
                </CardHeader>
                <CardContent className="px-0 pb-2">
                  {q.isLoading ? <LoadingRows rows={4} /> : !a.next.length ? (
                    <EmptyState icon={CalendarDays} title="No more appointments today" description="The rest of the day is clear." />
                  ) : (
                    <ul className="divide-y">
                      {a.next.map((x) => (
                        <li key={x.id}>
                          <Link to={`/patients/${x.patient_id}`} className="flex items-center gap-4 px-5 py-2.5 hover:bg-muted/50">
                            <span className="w-16 shrink-0 text-[13px] font-semibold tabular">{fmtTime(x.start_at, clinic?.timezone)}</span>
                            <span className="min-w-0 flex-1">
                              <span className="flex items-center gap-1.5 font-medium">{x.patient}{x.mode === "telehealth" && <Video className="size-3.5 text-primary" aria-label="Telehealth" />}</span>
                              <span className="block truncate text-xs text-muted-foreground">{[x.type, x.reason, x.provider].filter(Boolean).join(" · ")}</span>
                            </span>
                            <AppointmentStatusBadge status={x.status} />
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            )}

            <div className="space-y-5">
              {a && (
                <Card>
                  <CardHeader>
                    <div><CardTitle>Waiting room</CardTitle><CardDescription>Checked in and roomed</CardDescription></div>
                    <Button variant="ghost" size="sm" asChild><Link to="/front-desk">Front desk</Link></Button>
                  </CardHeader>
                  <CardContent className="px-0 pb-2">
                    {!a.waiting.length ? <p className="px-5 pb-4 text-[13px] text-muted-foreground">Nobody is waiting.</p> : (
                      <ul className="divide-y">
                        {a.waiting.map((w) => {
                          const mins = minutesSince(w.checked_in_at) ?? 0;
                          return (
                            <li key={w.id} className="flex items-center gap-3 px-5 py-2.5">
                              <span className="min-w-0 flex-1">
                                <Link to={`/patients/${w.patient_id}`} className="font-medium hover:underline">{w.patient}</Link>
                                <span className="block text-xs text-muted-foreground">{w.room ? `${w.room} · ` : ""}{w.provider}</span>
                              </span>
                              <span className={`text-xs font-medium tabular ${mins > 20 ? "text-destructive" : "text-muted-foreground"}`}>{mins} min</span>
                              <AppointmentStatusBadge status={w.status} />
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </CardContent>
                </Card>
              )}
              {d?.clinical && (
                <Card>
                  <CardHeader>
                    <div><CardTitle>My open visits</CardTitle><CardDescription>Encounters awaiting documentation</CardDescription></div>
                  </CardHeader>
                  <CardContent className="px-0 pb-2">
                    {!d.clinical.open_encounters.length ? <p className="px-5 pb-4 text-[13px] text-muted-foreground">No open encounters.</p> : (
                      <ul className="divide-y">
                        {d.clinical.open_encounters.map((e) => (
                          <li key={e.id}>
                            <Link to={`/encounters/${e.id}`} className="flex items-center gap-3 px-5 py-2.5 hover:bg-muted/50">
                              <Stethoscope className="size-4 text-ai" />
                              <span className="min-w-0 flex-1">
                                <span className="block font-medium">{e.patient}</span>
                                <span className="block truncate text-xs text-muted-foreground">{e.chief_complaint ?? "No chief complaint"}</span>
                              </span>
                              <span className="text-xs text-muted-foreground">{fmtTime(e.started_at)}</span>
                            </Link>
                          </li>
                        ))}
                      </ul>
                    )}
                  </CardContent>
                </Card>
              )}
            </div>
          </div>

          {!!d?.appointments_7d?.length && (
            <Card>
              <CardHeader><div><CardTitle>Appointment volume</CardTitle><CardDescription>Last 7 days, all locations</CardDescription></div></CardHeader>
              <CardContent className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={d.appointments_7d.map((x) => ({ ...x, label: format(parseISO(x.date), "EEE d") }))} margin={{ left: -20, right: 8, top: 4 }}>
                    <CartesianGrid vertical={false} stroke="var(--border)" />
                    <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} />
                    <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} />
                    <RTooltip cursor={{ fill: "var(--muted)" }} contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} />
                    <Bar dataKey="count" name="Appointments" fill="var(--primary)" radius={[4, 4, 0, 0]} maxBarSize={36} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </>
  );
}
