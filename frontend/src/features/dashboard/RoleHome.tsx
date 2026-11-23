import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, BedDouble, Building2, CalendarPlus, CheckCircle2, ClipboardList, Clock, FileCheck2, FlaskConical, HeartPulse, Inbox, KeyRound,
  type LucideIcon, Pill, Radar, Receipt, ScanLine, ScrollText, Search, ServerCog, ShieldCheck, Siren, Stethoscope, UserPlus, Users,
} from "lucide-react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingRows, Metric, MetricStrip } from "@/components/common";
import { dueLabel, StatusChip, toWorkStatus, type WorkStatus } from "@/components/common/Status";
import { profileFor, type HomeProfile } from "@/components/layout/nav";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { AskAI } from "@/features/ai/AskAI";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
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

type Group = { key: string; patient: string | null; items: Priority[] };

/** Group priorities by patient (cases without a patient stay on their own row); keep server order (severity → overdue). */
function groupPriorities(ps: Priority[]): Group[] {
  const out: Group[] = [];
  for (const p of ps) {
    const g = p.patient_name ? out.find((x) => x.patient === p.patient_name) : undefined;
    if (g) g.items.push(p); else out.push({ key: `${p.kind}-${p.id}`, patient: p.patient_name, items: [p] });
  }
  return out;
}
/** "Discharge: discharge summary signed — Maya Sorensen" → "Discharge summary signed" (patient shown in its own column). */
/** If every item in a group starts with the same "Area: " prefix, return it (shown once instead of on every line). */
function commonPrefix(items: Priority[]): string | null {
  const ps = items.map((p) => /^([^:]{2,24}):\s+/.exec(p.title)?.[1] ?? null);
  return ps[0] && ps.every((x) => x === ps[0]) ? ps[0] : null;
}
function stripPrefix(t: string, prefix: string | null) {
  if (!prefix || !t.startsWith(prefix + ":")) return t;
  const r = t.slice(prefix.length + 1).trim();
  return r.charAt(0).toUpperCase() + r.slice(1);
}
function shortTitle(p: Priority) {
  let t = p.title;
  if (p.patient_name) for (const sep of [" — ", ": ", " - "]) if (t.endsWith(`${sep}${p.patient_name}`)) t = t.slice(0, -(p.patient_name.length + sep.length));
  const m = /^([^:]{2,24}):\s+(.*)$/.exec(t);
  if (m && m[2].toLowerCase().startsWith(m[1].toLowerCase())) t = m[2];
  return t.charAt(0).toUpperCase() + t.slice(1);
}
const STATUS_LABEL: Record<WorkStatus, string> = { urgent: "Urgent", blocked: "Blocked", failed: "Failed", overdue: "Overdue", escalated: "Escalated", needs_approval: "Needs approval", in_progress: "In progress", waiting: "Waiting", not_started: "Not started", done: "Done" };
const STATUS_RANK: Record<WorkStatus, number> = { urgent: 0, blocked: 1, failed: 2, overdue: 3, escalated: 4, needs_approval: 5, in_progress: 6, waiting: 7, not_started: 8, done: 9 };

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
  const groups = d ? groupPriorities(d.priorities) : [];
  const ownLabel = d?.role_label;
  const today = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });

  return (
    <div className="space-y-5" data-testid="role-home">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-label font-medium text-muted-foreground">{d?.role_label ?? "Your workspace"}{clinic ? ` · ${clinic.name}` : ""} · {today}</p>
          <h1 className="mt-0.5 text-title font-semibold tracking-tight text-heading">{greeting()}, {me?.user.first_name}</h1>
        </div>
        {ai && <AskAI agent={ai.agent} label={ai.label} question={ai.question} variant="ai" />}
      </header>

      {!!actions.length && (
        <nav aria-label="Quick actions" data-testid="home-actions" className="flex flex-wrap items-center gap-2">
          <span className="mr-1 text-label font-medium text-muted-foreground">Quick actions</span>
          {actions.map((a) => (
            <Button key={a.label} asChild variant="outline" size="sm"><Link to={a.to}><a.icon />{a.label}</Link></Button>
          ))}
        </nav>
      )}

      {q.error ? <ErrorState error={q.error} retry={() => q.refetch()} /> : (
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.8fr)_minmax(0,1fr)]">
          <Card data-testid="home-priorities">
            <CardHeader className="items-center border-b">
              <div>
                <CardTitle>My priorities</CardTitle>
                <CardDescription>Clinical severity first, then overdue work{d ? ` · ${totalWork} open` : ""}</CardDescription>
              </div>
              <Link to="/worklist" className="inline-flex items-center gap-1 text-table font-medium text-primary hover:underline">View all{d ? ` (${totalWork})` : ""}<ArrowRight className="size-3.5" /></Link>
            </CardHeader>
            {q.isLoading ? <LoadingRows rows={4} /> : !groups.length ? (
              <div className="flex items-center gap-3 px-4 py-5 text-body">
                <CheckCircle2 className="size-5 shrink-0 text-success" />
                <div><p className="font-medium text-heading">You're all caught up.</p><p className="text-table text-muted-foreground">Nothing is assigned to you right now. New alerts, tasks and approvals appear here automatically.</p></div>
              </div>
            ) : (
              <Table>
                <THead><TR><TH>Patient / item</TH><TH className="hidden md:table-cell">What's needed</TH><TH className="hidden md:table-cell">Due</TH><TH className="hidden md:table-cell">Status</TH><TH className="hidden w-0 md:table-cell"><span className="sr-only">Action</span></TH></TR></THead>
                <TBody>
                  {groups.map((g) => {
                    const statuses = g.items.map((p) => toWorkStatus(p.status, { overdue: p.overdue, kind: p.kind, severity: p.severity }));
                    const worst = [...statuses].sort((a, b) => STATUS_RANK[a] - STATUS_RANK[b])[0];
                    const first = g.items[0];
                    const owners = [...new Set(g.items.map((p) => p.owner))].filter((o) => o !== ownLabel);
                    const due = g.items.map((p) => p.due_at).filter(Boolean).sort()[0] ?? null;
                    return (
                      <TR key={g.key}>
                        <TD className="w-[11rem] min-w-[9rem] align-top">
                          <p className="font-semibold text-heading">{g.patient ?? shortTitle(first)}</p>
                          <p className="text-label text-muted-foreground">{[commonPrefix(g.items), ...new Set(g.items.map((p) => p.kind_label))].filter(Boolean).join(" · ")}{owners.length ? ` · Owner: ${owners.join(", ")}` : ""}{g.items.some((p) => p.escalated) ? " · escalated" : ""}</p>
                          <div className="mt-1.5 space-y-1.5 md:hidden">
                            {g.patient && [...new Set(g.items.map((p) => stripPrefix(shortTitle(p), commonPrefix(g.items))))].map((t) => <p key={t} className="leading-snug">{t}</p>)}
                            <div className="flex flex-wrap items-center gap-2">
                              <StatusChip status={worst} />
                              {due && <span className="text-label text-muted-foreground">{dueLabel(String(due))}</span>}
                              <Link to={first.link} className="text-table font-medium text-primary hover:underline">{first.action}</Link>
                            </div>
                          </div>
                        </TD>
                        <TD className="hidden align-top md:table-cell">
                          {g.patient ? Object.entries(g.items.reduce<Record<string, number>>((acc, p) => { const t = stripPrefix(shortTitle(p), commonPrefix(g.items)); acc[t] = (acc[t] ?? 0) + 1; return acc; }, {}))
                            .map(([t, n]) => <p key={t} className="leading-snug">{t}{n > 1 ? <span className="text-muted-foreground"> ×{n}</span> : null}</p>) : <p className="text-muted-foreground">{first.kind_label}</p>}
                        </TD>
                        <TD className="hidden whitespace-nowrap align-top md:table-cell">
                          {due ? <span className={cn("inline-flex items-center gap-1", g.items.some((p) => p.overdue) ? "font-medium text-warning-foreground" : "text-muted-foreground")}>
                            <Clock className="size-3.5" aria-hidden />{dueLabel(typeof due === "string" ? due : String(due))}</span> : <span className="text-muted-foreground">—</span>}
                        </TD>
                        <TD className="hidden align-top md:table-cell"><StatusChip status={worst} label={g.items.length > 1 ? `${STATUS_LABEL[worst]} · ${g.items.length}` : undefined} /></TD>
                        <TD className="hidden align-top md:table-cell"><Button asChild variant="outline" size="xs"><Link to={first.link}>{first.action}</Link></Button></TD>
                      </TR>
                    );
                  })}
                </TBody>
              </Table>
            )}
          </Card>

          <Card data-testid="home-today">
            <CardHeader className="items-center border-b"><div><CardTitle>Today</CardTitle><CardDescription>Live figures from the department screens</CardDescription></div></CardHeader>
            {q.isLoading ? <LoadingRows rows={2} /> : !d?.today.metrics.length ? (
              <p className="px-4 py-4 text-body text-muted-foreground">No daily figures for your role yet — use My work and Quick actions.</p>
            ) : (
              <MetricStrip cols={2} className="rounded-none border-0 border-b sm:grid-cols-2">
                {d.today.metrics.map((m) => (
                  <Metric key={m.label} label={m.label} value={<span className={cn(m.value === 0 && "text-muted-foreground")}>{m.value}</span>} sub={m.hint} to={m.link} />
                ))}
              </MetricStrip>
            )}
            {d?.today.list && (
              <div>
                <p className="px-4 pb-1 pt-3 text-label font-medium text-muted-foreground">{d.today.list.title}</p>
                <ul className="divide-y">
                  {d.today.list.items.map((i, n) => (
                    <li key={n}>
                      <Link to={i.link} className="flex items-start gap-3 px-4 py-2.5 text-table hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50">
                        {i.at && <span className="w-16 shrink-0 font-medium tabular text-heading">{new Date(i.at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>}
                        <span className="min-w-0 flex-1"><span className="block truncate font-medium text-heading">{i.title}</span>
                          {i.detail && <span className="block truncate text-label text-muted-foreground">{i.detail}</span>}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="border-t px-4 py-2.5 text-label text-muted-foreground">Updated {d ? fmtDateTime(new Date(q.dataUpdatedAt).toISOString()) : "…"}</p>
          </Card>
        </div>
      )}
    </div>
  );
}
