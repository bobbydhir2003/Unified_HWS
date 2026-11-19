import { useQuery } from "@tanstack/react-query";
import { CalendarDays, HeartPulse, LogOut, Pill, ShieldCheck } from "lucide-react";
import { Navigate } from "react-router-dom";
import { AppointmentStatusBadge, EmptyState, ErrorState, LoadingRows } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Summary } from "@/features/patients/PatientChart";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import type { Patient } from "@/lib/types";

/** Patient portal home (Phase 1 scope: the patient's own demographics, appointments, allergies and medications). */
export function PortalHome() {
  const { me, membership, logout } = useAuth();
  const pid = membership?.patient_id;
  const p = useQuery({ queryKey: ["patient", pid], queryFn: () => get<Patient>(`/patients/${pid}`), enabled: !!pid });
  const s = useQuery({ queryKey: ["summary", pid], queryFn: () => get<Summary>(`/patients/${pid}/summary`), enabled: !!pid });
  if (membership && !membership.roles.includes("patient")) return <Navigate to="/" replace />;
  return (
    <div className="min-h-dvh bg-background">
      <header className="border-b bg-card">
        <div className="mx-auto flex h-14 max-w-4xl items-center gap-3 px-4">
          <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-blue-500 to-blue-700">
            <svg viewBox="0 0 32 32" className="size-5" aria-hidden><path d="M10 9v8a6 6 0 0 0 12 0V9" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" /><circle cx="16" cy="24.5" r="1.8" fill="#bfdbfe" /></svg>
          </span>
          <span className="font-semibold">{membership?.organization_name ?? "Patient portal"}</span>
          <Button variant="ghost" size="sm" className="ml-auto" onClick={() => logout()}><LogOut />Sign out</Button>
        </div>
      </header>
      <main className="mx-auto max-w-4xl space-y-5 px-4 py-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Hello, {me?.user.first_name}</h1>
          <p className="text-[13.5px] text-muted-foreground">Your health information from {membership?.organization_name}.</p>
        </div>
        {!pid ? <EmptyState title="Your account isn't linked to a patient record yet" description="Please contact the clinic." /> : p.error ? <ErrorState error={p.error} /> : (
          <div className="grid gap-4 md:grid-cols-2">
            <Card className="md:col-span-2">
              <CardHeader><CardTitle className="flex items-center gap-2"><CalendarDays className="size-4 text-primary" />Upcoming appointments</CardTitle></CardHeader>
              <CardContent>
                {s.isLoading ? <LoadingRows rows={2} /> : !s.data?.upcoming_appointments.length ? <p className="text-[13px] text-muted-foreground">No upcoming appointments.</p> : (
                  <ul className="divide-y">{s.data.upcoming_appointments.map((a) => (
                    <li key={a.id} className="flex items-center justify-between gap-2 py-2.5">
                      <span><span className="font-medium">{fmtDateTime(a.start_at)}</span><span className="block text-xs text-muted-foreground">{[a.type, a.provider].filter(Boolean).join(" · ")}</span></span>
                      <AppointmentStatusBadge status={a.status} />
                    </li>
                  ))}</ul>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck className="size-4 text-destructive" />Allergies</CardTitle></CardHeader>
              <CardContent>{s.data?.allergies?.length ? <ul className="space-y-1 text-[13.5px]">{s.data.allergies.map((a) => <li key={a.id}>{a.substance} <span className="text-muted-foreground">— {a.reaction}</span></li>)}</ul> : <p className="text-[13px] text-muted-foreground">No known allergies on file.</p>}</CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><Pill className="size-4 text-success" />Medications</CardTitle></CardHeader>
              <CardContent>{s.data?.medications?.length ? <ul className="space-y-1 text-[13.5px]">{s.data.medications.map((m) => <li key={m.id}>{m.name} <span className="text-muted-foreground">{[m.dose, m.frequency].filter(Boolean).join(", ")}</span></li>)}</ul> : <p className="text-[13px] text-muted-foreground">No medications on file.</p>}</CardContent>
            </Card>
            {s.data?.last_vitals && (
              <Card className="md:col-span-2">
                <CardHeader><CardTitle className="flex items-center gap-2"><HeartPulse className="size-4 text-primary" />Latest vitals</CardTitle></CardHeader>
                <CardContent className="text-[13.5px]">
                  {s.data.last_vitals.systolic && <>Blood pressure {s.data.last_vitals.systolic}/{s.data.last_vitals.diastolic} · </>}
                  {s.data.last_vitals.heart_rate && <>Heart rate {s.data.last_vitals.heart_rate} · </>}
                  <span className="text-muted-foreground">{fmtDateTime(s.data.last_vitals.measured_at)}</span>
                </CardContent>
              </Card>
            )}
            <p className="text-xs text-muted-foreground md:col-span-2">Messaging, online booking, visit summaries, results and bills are coming to the portal in a later release.</p>
          </div>
        )}
      </main>
    </div>
  );
}
