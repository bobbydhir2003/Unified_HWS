import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, BedDouble, Building2, CalendarPlus, CheckCircle2, ClipboardList, FileCheck2, FlaskConical, HeartPulse, Inbox, KeyRound,
  type LucideIcon, Pill, Radar, Receipt, ScanLine, ScrollText, Search, ServerCog, ShieldCheck, Siren, Stethoscope, UserPlus, Users,
} from "lucide-react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingRows } from "@/components/common";
import { StatusChip, toWorkStatus } from "@/components/common/Status";
import { profileFor, type HomeProfile } from "@/components/layout/nav";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AskAI } from "@/features/ai/AskAI";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, fromNow } from "@/lib/format";
import { cn } from "@/lib/utils";

type Priority = { id: string; kind: "case" | "task" | "approval" | "critical_result"; kind_label: string; title: string; severity: string; status: string;
  overdue: boolean; due_at: string | null; owner: string; patient_name: string | null; link: string; action: string; escalated?: boolean };
type HomeData = { profile: string; role_label: string; priorities: Priority[]; counts: Record<string, number>;
  today: { metrics: { label: string; value: number | string; link: string; hint?: string }[]; list: { title: string; items: { title: string; detail: string; link: string; at?: string }[] } | null } };

type Action = { label: string; to: string; icon: LucideIcon; perm?: string; any?: string[] };
const ACTIONS: Record<HomeProfile, Action[]> = {
  doctor: [{ label: "My visits", to: "/encounters", icon: Stethoscope }, { label: "Find a patient", to: "/patients", icon: Search }, { label: "Orders & results", to: "/orders", icon: ClipboardList }, { label: "Emergency board", to: "/ed", icon: Siren, perm: "adt:read" }],
  nurse: [{ label: "Record vitals", to: "/nursing", icon: HeartPulse, perm: "nursing:write" }, { label: "Find a patient", to: "/patients", icon: Search }, { label: "Emergency board", to: "/ed", icon: Siren, perm: "adt:read" }, { label: "Bed board", to: "/beds", icon: BedDouble, perm: "adt:read" }],
  receptionist: [{ label: "Check in arrivals", to: "/front-desk", icon: ClipboardList, perm: "schedule:write" }, { label: "Register patient", to: "/patients/new", icon: UserPlus, perm: "patients:write" }, { label: "Book appointment", to: "/schedule?new=1", icon: CalendarPlus, perm: "schedule:write" }, { label: "Insurance issues", to: "/insurance", icon: ShieldCheck, any: ["insurance:write", "automation:manage"] }],
  clinic_admin: [{ label: "Front desk", to: "/front-desk", icon: ClipboardList, perm: "schedule:write" }, { label: "Register patient", to: "/patients/new", icon: UserPlus, perm: "patients:write" }, { label: "Book appointment", to: "/schedule?new=1", icon: CalendarPlus, perm: "schedule:write" }, { label: "Staff & roles", to: "/admin/staff", icon: Users, perm: "users:manage" }],
  pharmacist: [{ label: "Verify medication orders", to: "/pharmacy", icon: Pill }, { label: "Stock & purchasing", to: "/pharmacy", icon: ClipboardList }, { label: "Find a patient", to: "/patients", icon: Search }],
  lab_tech: [{ label: "Laboratory worklist", to: "/lab", icon: FlaskConical }, { label: "Find a patient", to: "/patients", icon: Search }, { label: "Orders", to: "/orders", icon: ClipboardList }],
  radiologist: [{ label: "Radiology worklist", to: "/radiology", icon: ScanLine }, { label: "Find a patient", to: "/patients", icon: Search }, { label: "Orders", to: "/orders", icon: ClipboardList }],
  bed_manager: [{ label: "Assign beds", to: "/beds", icon: BedDouble }, { label: "Inpatients", to: "/inpatients", icon: Building2 }, { label: "Emergency board", to: "/ed", icon: Siren }, { label: "Command Center", to: "/command", icon: Radar, any: ["command:view", "automation:manage"] }],
  billing: [{ label: "Claims", to: "/billing", icon: Receipt, perm: "billing:read" }, { label: "Claims & authorizations", to: "/revenue", icon: FileCheck2 }, { label: "Insurance issues", to: "/insurance", icon: ShieldCheck, any: ["insurance:write", "automation:manage"] }],
  insurance_specialist: [{ label: "Insurance cases", to: "/insurance", icon: ShieldCheck }, { label: "Card reviews", to: "/insurance?tab=review", icon: FileCheck2 }, { label: "Prior authorizations", to: "/revenue", icon: ClipboardList }],
  hospital_admin: [{ label: "Command Center", to: "/command", icon: Radar }, { label: "Approvals", to: "/worklist?tab=approvals", icon: CheckCircle2 }, { label: "Bed board", to: "/beds", icon: BedDouble }, { label: "Reports", to: "/analytics", icon: ScrollText, perm: "analytics:read" }],
  super_admin: [{ label: "AI settings", to: "/admin/ai-settings", icon: KeyRound, perm: "org:manage" }, { label: "Staff & roles", to: "/admin/staff", icon: Users, perm: "users:manage" }, { label: "Audit log", to: "/admin/audit", icon: ScrollText, perm: "audit:read" }, { label: "System status", to: "/admin/system", icon: ServerCog, perm: "clinic:manage" }],
  staff: [{ label: "My work", to: "/worklist", icon: Inbox }, { label: "Find a patient", to: "/patients", icon: Search }],
};

/** Contextual AI on Home — an existing agent with a preset, role-relevant question. */
const HOME_AI: Partial<Record<HomeProfile, { agent: string; label: string; question: string }>> = {
  hospital_admin: { agent: "hospital_operations", label: "Explain today's bottlenecks", question: "Explain today's operational bottlenecks and which teams they are waiting on, citing case references." },
  bed_manager: { agent: "hospital_operations", label: "Explain bed bottlenecks", question: "Summarize bed capacity, patients waiting for a bed and beds waiting for cleaning, citing case references." },
  pharmacist: { agent: "pharmacy_watchdog", label: "Summarize inventory risks", question: "Summarize medication stock and expiry risks that need pharmacy review today." },
  billing: { agent: "claims_review", label: "Explain claim problems", question: "Explain which claims need attention and why, citing case references." },
  insurance_specialist: { agent: "insurance_guardian", label: "Summarize coverage issues", question: "Summarize open insurance coverage issues for upcoming visits, most urgent first." },
  receptionist: { agent: "insurance_guardian", label: "Arrivals with insurance issues", question: "Which upcoming appointments have insurance coverage issues, and what is the next step for each?" },
  nurse: { agent: "discharge_coordination", label: "Summarize discharge tasks", question: "Summarize discharges that are waiting on nursing and what each one needs next." },
  doctor: { agent: "discharge_coordination", label: "Summarize my discharge tasks", question: "Summarize discharges waiting on a physician (summaries, instructions) and what each one needs next." },
};

const SEV_DOT: Record<string, string> = { critical: "bg-destructive", high: "bg-destructive/80", medium: "bg-warning", low: "bg-muted-foreground/50" };

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export function RoleHome() {
  const { me, membership, clinic, can } = useAuth();
  const profile = profileFor(membership?.roles);
  const q = useQuery({ queryKey: ["home"], queryFn: () => get<HomeData>("/home"), refetchInterval: 60_000 });
  const d = q.data;
  const actions = ACTIONS[profile].filter((a) => (!a.perm || can(a.perm)) && (!a.any || a.any.some((p) => can(p))));
  const ai = HOME_AI[profile];
  const totalWork = d ? d.counts.cases + d.counts.tasks + d.counts.approvals + d.counts.critical_results : 0;

  return (
    <div className="mx-auto max-w-6xl space-y-5" data-testid="role-home">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{greeting()}, {me?.user.first_name}</h1>
          <p className="mt-0.5 text-[13.5px] text-muted-foreground">
            {d?.role_label ?? "Your workspace"}{clinic ? ` · ${clinic.name}` : ""} · {new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
          </p>
        </div>
        {ai && <AskAI agent={ai.agent} label={ai.label} question={ai.question} variant="outline" />}
      </header>

      {q.error ? <ErrorState error={q.error} retry={() => q.refetch()} /> : (
        <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
          <Card data-testid="home-priorities">
            <CardHeader className="flex-row items-center justify-between gap-2 pb-2">
              <div>
                <CardTitle className="text-[15px]">My priorities</CardTitle>
                <p className="text-[12.5px] text-muted-foreground">What needs your attention first — most urgent at the top.</p>
              </div>
              <Link to="/worklist" className="inline-flex items-center gap-1 text-[13px] font-medium text-primary hover:underline">View all{d ? ` (${totalWork})` : ""}<ArrowRight className="size-3.5" /></Link>
            </CardHeader>
            <CardContent className="pt-0">
              {q.isLoading ? <LoadingRows rows={4} /> : !d?.priorities.length ? (
                <div className="flex items-center gap-3 rounded-xl bg-success-soft/60 px-4 py-5 text-[13.5px]">
                  <CheckCircle2 className="size-5 shrink-0 text-success" />
                  <div><p className="font-medium">You're all caught up.</p><p className="text-muted-foreground">Nothing is assigned to you right now. New alerts, tasks and approvals will appear here automatically.</p></div>
                </div>
              ) : (
                <ul className="divide-y">
                  {d.priorities.map((p) => (
                    <li key={`${p.kind}-${p.id}`} className="flex items-start gap-3 py-3">
                      <span className={cn("mt-1.5 size-2.5 shrink-0 rounded-full", SEV_DOT[p.severity] ?? SEV_DOT.medium)} aria-hidden />
                      <div className="min-w-0 flex-1">
                        <p className="text-[13.5px] font-medium leading-snug">{p.title}</p>
                        <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-muted-foreground">
                          <Badge variant={p.kind === "approval" ? "ai" : p.kind === "critical_result" ? "danger" : "neutral"}>{p.kind_label}</Badge>
                          <span>Owner: <span className="text-foreground">{p.owner}</span></span>
                          {p.patient_name && <span>· {p.patient_name}</span>}
                          {p.due_at && <span>· {p.overdue ? "overdue " : "due "}{fromNow(p.due_at)}</span>}
                          {p.escalated && <span>· escalated</span>}
                        </p>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1.5">
                        <StatusChip status={toWorkStatus(p.status, { overdue: p.overdue, kind: p.kind })} />
                        <Link to={p.link} className="text-[12.5px] font-medium text-primary hover:underline">{p.action}</Link>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <div className="space-y-5">
            <Card data-testid="home-actions">
              <CardHeader className="pb-2"><CardTitle className="text-[15px]">Quick actions</CardTitle></CardHeader>
              <CardContent className="grid gap-2 pt-0">
                {actions.map((a) => (
                  <Link key={a.label} to={a.to} className="flex items-center gap-3 rounded-lg border px-3 py-2.5 text-[13.5px] font-medium hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
                    <a.icon className="size-4 text-primary" />{a.label}<ArrowRight className="ml-auto size-3.5 text-muted-foreground" />
                  </Link>
                ))}
              </CardContent>
            </Card>
          </div>

          <Card className="lg:col-span-2" data-testid="home-today">
            <CardHeader className="pb-2"><CardTitle className="text-[15px]">Today</CardTitle></CardHeader>
            <CardContent className="space-y-4 pt-0">
              {q.isLoading ? <LoadingRows rows={2} /> : !d?.today.metrics.length ? (
                <p className="text-[13.5px] text-muted-foreground">No daily figures for your role yet — use My work and Quick actions.</p>
              ) : (
                <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                  {d.today.metrics.map((m) => (
                    <li key={m.label}>
                      <Link to={m.link} className="block rounded-xl border bg-card px-4 py-3 hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
                        <p className="text-[12.5px] text-muted-foreground">{m.label}</p>
                        <p className="mt-0.5 text-xl font-semibold tabular">{m.value}</p>
                        {m.hint && <p className="mt-0.5 truncate text-[11.5px] text-muted-foreground">{m.hint}</p>}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              {d?.today.list && (
                <div>
                  <p className="mb-1.5 text-[13px] font-medium">{d.today.list.title}</p>
                  <ul className="divide-y rounded-xl border">
                    {d.today.list.items.map((i, n) => (
                      <li key={n}>
                        <Link to={i.link} className="flex items-center gap-3 px-4 py-2.5 text-[13.5px] hover:bg-muted/50">
                          {i.at && <span className="w-16 shrink-0 tabular text-muted-foreground">{new Date(i.at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>}
                          <span className="min-w-0 flex-1 truncate font-medium">{i.title}</span>
                          <span className="hidden min-w-0 max-w-[45%] truncate text-muted-foreground sm:block">{i.detail}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-[11.5px] text-muted-foreground">Live figures from the same records as each department screen{d ? ` · updated ${fmtDateTime(new Date().toISOString())}` : ""}.</p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
