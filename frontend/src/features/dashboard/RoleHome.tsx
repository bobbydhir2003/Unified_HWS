/**
 * Role dashboards (Home). One shell for every workspace; the CONTENT comes from /home (dashboard section), which computes
 * each role's figures and worklists from live records with the same scoping as the department screens. The AI companion
 * uses the real HMS Intelligence agents (/assist/agents) and opens the shared conversation panel; availability shown is the
 * server's (enabled, permitted in this workspace, conversations on). Nothing here is hard-coded data.
 */
import { useQuery } from "@tanstack/react-query";
import {
  Activity, AlertTriangle, ArrowRight, BedDouble, Bot, Building2, CalendarClock, CalendarPlus, CheckCircle2, ClipboardCheck, ClipboardList,
  Clock, FileCheck2, FlaskConical, HeartPulse, Inbox, KeyRound, type LucideIcon, MessageSquare, Pill, Radar, Receipt, ScanLine, ScrollText,
  Search, ServerCog, ShieldCheck, Siren, Sparkles, Stethoscope, UserPlus, Users,
} from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingRows } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { type AssistAgent, type AssistContext, HMSAssistSheet, useAssistAgents } from "@/features/assist/HMSAssistPanel";
import { AGENTS as PROFILES } from "@/features/public/agents";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ROLE_LABELS, type Role } from "@/lib/types";
import { cn } from "@/lib/utils";

type Priority = { id: string; kind: "case" | "task" | "approval" | "critical_result"; kind_label: string; title: string; severity: string; status: string;
  overdue: boolean; due_at: string | null; owner: string; patient_name: string | null; link: string; action: string; escalated?: boolean };
type Item = { at?: string | null; title: string; detail?: string | null; status?: string | null; tone?: string | null; link: string; patient_id?: string | null };
type Section = { title: string; link: string; kind: "schedule" | "list"; items: Item[]; more?: number };
type MetricT = { key: string; label: string; value: number | string; link: string; sub?: string | null; tone?: string | null };
type Recent = { agent_key: string; summary: string; at: string; link?: string | null; context_type?: string | null; context_id?: string | null };
type Automation = { monitors: number; enabled: number; ai_enabled: number; safety_rule_only: number; open_cases: number; last_run_at: string | null; link: string };
type HomeData = {
  profile: string; dashboard_profile: string; role_label: string; priorities: Priority[]; counts: Record<string, number>;
  identity: { name: string; first_name: string; title: string | null; is_platform_admin: boolean; has_provider_profile: boolean; acting_role: string | null };
  dashboard: { header: { title: string; subtitle: string }; metrics: MetricT[]; queue: Section | null; extra: Section | null;
    agents: { primary: string; secondary: string[] }; ai_recent: Recent[]; automation: Automation | null; generated_at: string; timezone: string };
};
type ConvRow = { id: string; context_type: string; context_id: string | null; context_label: string | null; status: string; last_message_at: string };

type Action = { label: string; to: string; icon: LucideIcon; perm?: string; any?: string[] };
const ACTIONS: Record<string, Action[]> = {
  doctor: [{ label: "My visits", to: "/encounters", icon: Stethoscope }, { label: "Find a patient", to: "/patients", icon: Search }, { label: "Orders & results", to: "/orders", icon: ClipboardList }, { label: "Emergency board", to: "/ed", icon: Siren, perm: "adt:read" }],
  nurse: [{ label: "Unit worklist", to: "/nursing", icon: HeartPulse }, { label: "Find a patient", to: "/patients", icon: Search }, { label: "Emergency board", to: "/ed", icon: Siren, perm: "adt:read" }, { label: "Bed board", to: "/beds", icon: BedDouble, perm: "adt:read" }],
  receptionist: [{ label: "Check in arrivals", to: "/front-desk", icon: ClipboardList, perm: "schedule:write" }, { label: "Register patient", to: "/patients/new", icon: UserPlus, perm: "patients:write" }, { label: "Book appointment", to: "/schedule?new=1", icon: CalendarPlus, perm: "schedule:write" }, { label: "Insurance issues", to: "/insurance", icon: ShieldCheck, any: ["insurance:write", "automation:manage"] }],
  clinic_admin: [{ label: "Front desk", to: "/front-desk", icon: ClipboardList, perm: "schedule:write" }, { label: "Messages", to: "/messages", icon: MessageSquare, perm: "messages:use" }, { label: "Book appointment", to: "/schedule?new=1", icon: CalendarPlus, perm: "schedule:write" }, { label: "Staff & roles", to: "/admin/staff", icon: Users, perm: "users:manage" }],
  pharmacist: [{ label: "Verify orders", to: "/pharmacy?tab=verify", icon: Pill }, { label: "Stock & purchasing", to: "/pharmacy?tab=purchasing", icon: ClipboardList }, { label: "Find a patient", to: "/patients", icon: Search }],
  lab_tech: [{ label: "Laboratory worklist", to: "/lab", icon: FlaskConical }, { label: "Find a patient", to: "/patients", icon: Search }, { label: "Orders", to: "/orders", icon: ClipboardList }],
  radiologist: [{ label: "Reading worklist", to: "/radiology", icon: ScanLine }, { label: "Find a patient", to: "/patients", icon: Search }, { label: "Orders", to: "/orders", icon: ClipboardList }],
  radiology_tech: [{ label: "Imaging worklist", to: "/radiology", icon: ScanLine }, { label: "Find a patient", to: "/patients", icon: Search }, { label: "Orders", to: "/orders", icon: ClipboardList }],
  bed_manager: [{ label: "Assign beds", to: "/beds", icon: BedDouble }, { label: "Inpatients", to: "/inpatients", icon: Building2 }, { label: "Emergency board", to: "/ed", icon: Siren }, { label: "Command Center", to: "/command", icon: Radar, any: ["command:view", "automation:manage"] }],
  billing: [{ label: "Claims", to: "/billing", icon: Receipt, perm: "billing:read" }, { label: "Claims & authorizations", to: "/revenue", icon: FileCheck2 }, { label: "Insurance issues", to: "/insurance", icon: ShieldCheck, any: ["insurance:write", "automation:manage"] }],
  insurance_specialist: [{ label: "Insurance cases", to: "/insurance", icon: ShieldCheck }, { label: "Card reviews", to: "/insurance?tab=review", icon: FileCheck2 }, { label: "Prior authorizations", to: "/revenue", icon: ClipboardList }],
  hospital_admin: [{ label: "Command Center", to: "/command", icon: Radar }, { label: "Approvals", to: "/worklist?tab=approvals", icon: CheckCircle2 }, { label: "Staff roster", to: "/roster", icon: Users }, { label: "Reports", to: "/analytics", icon: ScrollText, perm: "analytics:read" }],
  super_admin: [{ label: "Staff & roles", to: "/admin/staff", icon: Users, perm: "users:manage" }, { label: "Agent Studio", to: "/agents", icon: Bot, perm: "ai:use" }, { label: "AI settings", to: "/admin/ai-settings", icon: KeyRound, perm: "org:manage" }, { label: "System status", to: "/admin/system", icon: ServerCog, perm: "clinic:manage" }],
  staff: [{ label: "My work", to: "/worklist", icon: Inbox }, { label: "Find a patient", to: "/patients", icon: Search }],
};
const METRIC_ICON: Record<string, LucideIcon> = {
  visits: CalendarClock, appointments: CalendarClock, arriving: Clock, waiting: Users, inpatients: BedDouble, patients: BedDouble, tasks: ClipboardCheck,
  approvals: ShieldCheck, results: FlaskConical, discharges: ClipboardList, meds: Pill, vitals: HeartPulse, assessments: ClipboardCheck, handoffs: Users,
  insurance: ShieldCheck, messages: MessageSquare, verify: Pill, clarify: AlertTriangle, stock: Pill, prs: Receipt, collect: FlaskConical, in_lab: FlaskConical,
  critical: AlertTriangle, schedule: CalendarClock, active: ScanLine, read: ScanLine, prelim: ScanLine, free: BedDouble, cleaning: BedDouble,
  discharging: ClipboardList, cases: Inbox, review: Receipt, hold: AlertTriangle, denied: AlertTriangle, pa: FileCheck2, escalated: AlertTriangle,
  checks: ShieldCheck, beds: BedDouble, ed: Siren, staffing: Users, staff: Users, ai_runs: Bot,
};
const TONE: Record<string, string> = {
  danger: "bg-destructive-soft text-destructive", warning: "bg-warning-soft text-warning-foreground", success: "bg-success-soft text-success",
  info: "bg-info-soft text-accent-foreground", primary: "bg-accent text-accent-foreground", neutral: "bg-muted text-muted-foreground",
};
const DEPT_LINK: Record<string, string> = { medical_scribe: "/encounters", document_intelligence: "/documents", doctor_assistant: "/patients" };

function greeting(tz: string) {
  const h = Number(new Intl.DateTimeFormat("en-US", { hour: "numeric", hourCycle: "h23", timeZone: tz }).format(new Date()));
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}
function timeIn(at: string | null | undefined, tz: string) {
  return at ? new Date(at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZone: tz }) : "";
}
function ago(at: string | null | undefined) {
  if (!at) return "—";
  const m = Math.max(0, Math.round((Date.now() - new Date(at).getTime()) / 60000));
  return m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
}

export function AgentAvatar({ agentKey, size = "md", className }: { agentKey: string; size?: "sm" | "md" | "lg"; className?: string }) {
  const p = PROFILES.find((x) => x.key === agentKey);
  const dim = { sm: "size-8 text-table", md: "size-10 text-section", lg: "size-14 text-xl" }[size];
  if (!p) return <span className={cn("grid shrink-0 place-items-center rounded-xl bg-ai-soft text-ai", dim, className)}><Bot className="size-4" /></span>;
  return (
    <span className={cn("relative grid shrink-0 place-items-center rounded-xl font-semibold text-white shadow-sm", dim, className)} style={{ backgroundColor: p.hue }} aria-hidden>
      {p.name[0]}<span className="absolute -bottom-1 -right-1 grid size-4 place-items-center rounded bg-card ring-1 ring-border"><p.icon className="size-2.5" style={{ color: p.hue }} /></span>
    </span>
  );
}

function SectionCard({ title, icon: Icon, link, linkLabel = "View all", children, testId, className }: {
  title: string; icon: LucideIcon; link?: string; linkLabel?: string; children: React.ReactNode; testId?: string; className?: string;
}) {
  return (
    <Card className={cn("overflow-hidden", className)} data-testid={testId}>
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <Icon className="size-4 text-primary" aria-hidden /><h2 className="text-section font-semibold text-heading">{title}</h2>
        {link && <Link to={link} className="ml-auto inline-flex items-center gap-1 text-table font-medium text-primary hover:underline">{linkLabel}<ArrowRight className="size-3.5" /></Link>}
      </div>
      {children}
    </Card>
  );
}

function QueueList({ s, tz, empty }: { s: Section | null; tz: string; empty: string }) {
  if (!s || !s.items.length) return <p className="flex items-center gap-2 px-4 py-6 text-body text-muted-foreground"><CheckCircle2 className="size-4 text-success" />{empty}</p>;
  return (
    <>
      <ul className="divide-y">
        {s.items.map((i, n) => (
          <li key={n}>
            <Link to={i.link} className="flex items-center gap-3 px-4 py-2.5 text-table hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50">
              {s.kind === "schedule" && <span className="w-16 shrink-0 font-semibold tabular text-heading">{timeIn(i.at, tz)}</span>}
              <span className="min-w-0 flex-1"><span className="block truncate font-medium text-heading">{i.title}</span>
                {i.detail && <span className="block truncate text-label text-muted-foreground">{i.detail}</span>}</span>
              {i.status && <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-label font-medium capitalize", TONE[i.tone ?? "neutral"] ?? TONE.neutral)}>{i.status}</span>}
            </Link>
          </li>
        ))}
      </ul>
      {!!s.more && <Link to={s.link} className="block border-t px-4 py-2 text-center text-table font-medium text-primary hover:underline">+ {s.more} more</Link>}
    </>
  );
}

const SEV_ICON: Record<string, { icon: LucideIcon; cls: string }> = {
  critical: { icon: AlertTriangle, cls: "text-destructive" }, high: { icon: AlertTriangle, cls: "text-warning" }, medium: { icon: Clock, cls: "text-primary" }, low: { icon: Clock, cls: "text-muted-foreground" },
};

function Attention({ items, total }: { items: Priority[]; total: number }) {
  return (
    <SectionCard title={`Requires your attention${total ? ` (${total})` : ""}`} icon={Inbox} link="/worklist" testId="home-priorities">
      {!items.length ? (
        <p className="flex items-center gap-2 px-4 py-6 text-body text-muted-foreground"><CheckCircle2 className="size-4 text-success" />You're all caught up. New alerts, tasks and approvals appear here.</p>
      ) : (
        <ul className="divide-y">{items.map((p) => {
          const s = SEV_ICON[p.severity] ?? SEV_ICON.medium;
          return (
            <li key={`${p.kind}-${p.id}`}>
              <Link to={p.link} className="flex items-center gap-3 px-4 py-2.5 text-table hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50">
                <s.icon className={cn("size-4 shrink-0", s.cls)} aria-label={p.severity} />
                <span className="min-w-0 flex-1"><span className="block truncate font-medium text-heading">{p.patient_name ?? p.title}</span>
                  <span className="block truncate text-label text-muted-foreground">{p.patient_name ? p.title : p.owner}{p.overdue ? " · overdue" : ""}{p.escalated ? " · escalated" : ""}</span></span>
                <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-label font-medium", p.kind === "critical_result" ? TONE.danger : p.kind === "approval" ? TONE.warning : TONE.info)}>{p.kind_label}</span>
              </Link>
            </li>);
        })}</ul>
      )}
    </SectionCard>
  );
}

type Opener = (agent: AssistAgent, ctx: AssistContext) => void;

/** The role's primary agent: identity, real availability, verified capabilities, direct conversation entry. */
function Companion({ primary, agents, patients, open, live, featureOn }: {
  primary: string; agents: AssistAgent[]; patients: { id: string; name: string }[]; open: Opener; live: boolean | undefined; featureOn: boolean;
}) {
  const a = agents.find((x) => x.key === primary);
  const prof = PROFILES.find((x) => x.key === primary);
  const [pid, setPid] = React.useState("");
  const [q, setQ] = React.useState("");
  const search = useQuery({ queryKey: ["home", "patient-search", q], enabled: primary === "doctor_assistant" && q.trim().length >= 2,
    queryFn: () => get<{ items: { id: string; first_name: string; last_name: string; mrn: string }[] }>("/patients", { q: q.trim(), page_size: 5 }) });
  const history = useQuery({ queryKey: ["assist", "history", primary, "home"], enabled: !!a?.can_use && featureOn,
    queryFn: () => get<ConvRow[]>("/assist/conversations", { agent_key: primary }) });
  if (!a || !prof) return null;
  const usable = featureOn && a.enabled && a.can_use;
  const status = !a.enabled ? { label: "Turned off by your administrator", cls: "bg-white/15 text-white/80" } : !a.can_use ? { label: "Not available in this workspace", cls: "bg-white/15 text-white/80" }
    : !featureOn ? { label: "Conversations not enabled", cls: "bg-white/15 text-white/80" } : { label: live ? "Active · live AI" : "Active · rule-based mode", cls: "bg-emerald-400/20 text-emerald-100" };
  // Plain-language capabilities; approval/confirm lines only when the server reports this user can use those tools here.
  const caps = [...prof.helps, ...(a.capabilities.proposals.length ? prof.approval.map((x) => `Proposes: ${x}`) : []),
    ...(a.capabilities.confirm.length ? prof.confirm.map((x) => `Prepares for you to confirm: ${x}`) : [])].slice(0, 5);
  const readOnly = !a.capabilities.proposals.length && !a.capabilities.confirm.length;
  const needsPatient = !a.contexts.includes("workspace");
  const choices = [...patients, ...(search.data?.items ?? []).map((p) => ({ id: p.id, name: `${p.first_name} ${p.last_name} (${p.mrn})` }))]
    .filter((p, i, arr) => arr.findIndex((x) => x.id === p.id) === i);
  const recent = (history.data ?? []).filter((h) => h.status === "active").slice(0, 3);
  return (
    <Card className="overflow-hidden border-0 bg-gradient-to-b from-brand-navy to-indigo-950 text-white shadow-lg" data-testid="ai-companion" data-agent={primary}>
      <div className="flex items-center gap-2 px-4 pt-4 text-table font-medium text-white/75"><Sparkles className="size-4 text-cyan-300" aria-hidden />Your AI agent · HMS Intelligence</div>
      <div className="flex items-start gap-3 px-4 pt-3">
        <AgentAvatar agentKey={primary} size="lg" className="ring-2 ring-white/20" />
        <div className="min-w-0 flex-1">
          <p className="text-2xl font-semibold tracking-tight" data-testid="companion-name">{a.name}</p>
          <p className="text-table text-white/75">{a.role}</p>
          <span className={cn("mt-1.5 inline-flex rounded-full px-2 py-0.5 text-label font-medium", status.cls)} data-testid="companion-status">{status.label}</span>
        </div>
      </div>
      <p className="mx-4 mt-3 rounded-lg bg-white/10 px-3 py-2.5 text-table leading-relaxed text-white/90">{prof.summary}</p>
      <div className="px-4 pt-3">
        <p className="text-label font-semibold uppercase tracking-wider text-white/60">{readOnly ? "What I can do (read-only)" : "What I can do for you"}</p>
        <ul className="mt-1.5 space-y-1 text-table text-white/85">{caps.map((c) => <li key={c} className="flex gap-2"><CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-cyan-300" aria-hidden />{c}</li>)}</ul>
        {!readOnly && <p className="mt-2 text-label text-white/60">Changes need your confirmation or a different authorized person's approval.</p>}
      </div>
      <div className="space-y-2 p-4">
        {needsPatient && usable && (
          <div className="space-y-1.5">
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search a patient (name or MRN)…" aria-label={`Find a patient for ${a.name}`} className="h-8 border-white/20 bg-white/10 text-white placeholder:text-white/50" />
            <select value={pid} onChange={(e) => setPid(e.target.value)} aria-label="Patient" className="h-8 w-full rounded-md border border-white/20 bg-white/10 px-2 text-table text-white" data-testid="companion-patient">
              <option value="" className="text-foreground">Choose a patient…</option>
              {choices.map((p) => <option key={p.id} value={p.id} className="text-foreground">{p.name}</option>)}
            </select>
          </div>
        )}
        <Button className="w-full justify-between bg-white text-brand-navy hover:bg-white/90" disabled={!usable || (needsPatient && !pid)} data-testid="companion-ask"
          onClick={() => open(a, needsPatient ? { type: "patient", id: pid } : { type: "workspace" })}>
          <span className="flex min-w-0 items-center gap-2 truncate"><MessageSquare />Ask {a.name}{needsPatient && pid ? ` about ${choices.find((p) => p.id === pid)?.name.split(" (")[0] ?? "this patient"}` : ""}</span><ArrowRight />
        </Button>
        {!!recent.length && (
          <div className="rounded-lg bg-white/5 px-3 py-2" data-testid="companion-history">
            <p className="text-label font-semibold uppercase tracking-wider text-white/60">Continue a conversation</p>
            <ul className="mt-1 space-y-0.5">{recent.map((h) => (
              <li key={h.id}><button type="button" className="w-full truncate text-left text-table text-white/85 hover:text-white hover:underline"
                onClick={() => open(a, { type: h.context_type as AssistContext["type"], id: h.context_id })}>
                {h.context_label ?? "Your workspace"} · {ago(h.last_message_at)}</button></li>))}</ul>
          </div>
        )}
      </div>
    </Card>
  );
}

function Team({ keys, agents, open }: { keys: string[]; agents: AssistAgent[]; open: Opener }) {
  const { can } = useAuth();
  const avail = keys.map((k) => agents.find((a) => a.key === k)).filter((a): a is AssistAgent => !!a && a.can_use && a.enabled);
  if (!avail.length) return null;
  return (
    <Card className="p-4" data-testid="ai-team">
      <div className="flex items-center"><h2 className="text-section font-semibold text-heading">Meet your AI team</h2>
        {can("ai:use") && <Link to="/agents" className="ml-auto inline-flex items-center gap-1 text-table font-medium text-primary hover:underline">All agents<ArrowRight className="size-3.5" /></Link>}</div>
      <ul className="mt-3 grid grid-cols-3 gap-2">{avail.slice(0, 6).map((a) => {
        const inner = <><AgentAvatar agentKey={a.key} size="sm" /><span className="mt-1.5 block text-table font-semibold text-heading">{a.name}</span><span className="block w-full truncate text-label text-muted-foreground">{a.role?.replace(" AI", "")}</span></>;
        const cls = "flex w-full flex-col items-center rounded-lg border p-2 text-center hover:border-primary/40 hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60";
        return <li key={a.key} data-agent={a.key}>{a.contexts.includes("workspace")
          ? <button type="button" className={cls} onClick={() => open(a, { type: "workspace" })} aria-label={`Ask ${a.name}, ${a.role}`}>{inner}</button>
          : <Link to={DEPT_LINK[a.key] ?? "/agents"} className={cls} title={`${a.name} works inside its workflow`}>{inner}</Link>}</li>;
      })}</ul>
    </Card>
  );
}

function RecentAI({ items, agents, open }: { items: Recent[]; agents: AssistAgent[]; open: Opener }) {
  return (
    <SectionCard title="Recent AI assistance" icon={Sparkles} testId="ai-recent">
      {!items.length ? <p className="px-4 py-6 text-body text-muted-foreground">No AI activity yet. Ask an agent from the panel on the right.</p> : (
        <ul className="divide-y">{items.map((r, n) => {
          const a = agents.find((x) => x.key === r.agent_key);
          const body = <><AgentAvatar agentKey={r.agent_key} size="sm" /><span className="min-w-0 flex-1"><span className="block font-semibold text-heading">{a?.name ?? r.agent_key}</span>
            <span className="block truncate text-muted-foreground">{r.summary}</span></span><span className="shrink-0 text-label text-muted-foreground">{ago(r.at)}</span></>;
          const cls = "flex w-full items-center gap-3 px-4 py-2.5 text-left text-table hover:bg-muted/50";
          const ctx: AssistContext | null = r.context_type && r.context_type !== "workspace" ? { type: r.context_type as AssistContext["type"], id: r.context_id } : r.context_type === "workspace" ? { type: "workspace" } : null;
          return <li key={n}>{a && a.can_use && a.enabled && ctx && a.contexts.includes(ctx.type) ? <button type="button" className={cls} onClick={() => open(a, ctx)}>{body}</button>
            : r.link ? <Link to={r.link} className={cls}>{body}</Link> : <div className={cls}>{body}</div>}</li>;
        })}</ul>
      )}
    </SectionCard>
  );
}

function AutomationCard({ a }: { a: Automation }) {
  const stats: [string, number | string, string?][] = [["Monitors active", `${a.enabled}/${a.monitors}`], ["With AI assistance", a.ai_enabled], ["Open cases", a.open_cases, a.open_cases ? "text-destructive" : undefined], ["Critical, rule-based only", a.safety_rule_only]];
  return (
    <SectionCard title="Automation monitors" icon={Activity} link={a.link} linkLabel="Monitors" testId="automation-card">
      <dl className="grid grid-cols-2 divide-x divide-y sm:grid-cols-4 sm:divide-y-0">{stats.map(([l, v, cls]) => (
        <div key={l} className="px-4 py-3"><dd className={cn("text-2xl font-semibold tabular text-heading", cls)}>{v}</dd><dt className="text-label text-muted-foreground">{l}</dt></div>))}</dl>
      <p className="border-t bg-subtle px-4 py-2.5 text-label text-muted-foreground">Rule-based checks open cases for the owning team; AI assists selected cases only with human approval. Last run {ago(a.last_run_at)}.</p>
    </SectionCard>
  );
}

export function RoleHome() {
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["home"], queryFn: () => get<HomeData>("/home"), refetchInterval: 60_000 });
  const ag = useAssistAgents();
  const provider = useQuery({ queryKey: ["ai", "provider"], queryFn: () => get<{ live: boolean }>("/ai/provider"), enabled: can("ai:use"), staleTime: 5 * 60_000 });
  const [sheet, setSheet] = React.useState<{ agent: AssistAgent; ctx: AssistContext } | null>(null);
  const d = q.data;
  const dash = d?.dashboard;
  const tz = dash?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
  const profile = d?.dashboard_profile ?? "staff";
  const actions = (ACTIONS[profile] ?? ACTIONS.staff).filter((a) => (!a.perm || can(a.perm)) && (!a.any || a.any.some((p) => can(p))));
  const agents = ag.data?.agents ?? [];
  const patients = React.useMemo(() => {
    const out: { id: string; name: string }[] = [];
    for (const s of [dash?.queue, dash?.extra]) for (const i of s?.items ?? []) if (i.patient_id && !out.some((p) => p.id === i.patient_id)) out.push({ id: i.patient_id, name: i.title });
    return out.slice(0, 12);
  }, [dash]);
  const open: Opener = (agent, ctx) => setSheet({ agent, ctx });
  const totalWork = d ? d.counts.cases + d.counts.tasks + d.counts.approvals + d.counts.critical_results : 0;
  const date = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", timeZone: tz });
  const id = d?.identity;
  const actingNote = id?.is_platform_admin && id.acting_role && id.acting_role !== "super_admin"
    ? `Viewing the ${ROLE_LABELS[id.acting_role as Role] ?? id.acting_role} workspace as Platform Admin — signing and approvals still follow your own permissions.` : null;

  if (q.error) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  return (
    <div className="space-y-5" data-testid="role-home" data-profile={profile}>
      <section className="relative overflow-hidden rounded-xl bg-gradient-to-r from-brand-navy via-blue-900 to-blue-800 px-5 py-5 text-white shadow-sm sm:px-6" data-testid="home-header">
        <div className="pointer-events-none absolute inset-0 opacity-[0.08] [background-image:linear-gradient(to_right,white_1px,transparent_1px),linear-gradient(to_bottom,white_1px,transparent_1px)] [background-size:32px_32px]" aria-hidden />
        <div className="relative flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <p className="text-table text-white/80">{greeting(tz)}, {id?.first_name ?? "…"} · {d?.role_label ?? "Your workspace"} · {date}</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">{dash?.header.title ?? "Your workspace"}</h1>
            <p className="mt-1 text-body text-white/80">{dash?.header.subtitle}</p>
            {actingNote && <p className="mt-2 inline-flex rounded-md bg-white/10 px-2 py-1 text-label text-white/85" data-testid="acting-note">{actingNote}</p>}
          </div>
          {!!actions.length && (
            <nav aria-label="Quick actions" data-testid="home-actions" className="flex flex-wrap gap-2">
              {actions.map((a) => (
                <Link key={a.label} to={a.to} className="flex w-24 flex-col items-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.06] px-2 py-2.5 text-center text-label font-medium text-white/90 hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60">
                  <a.icon className="size-5 text-cyan-200" aria-hidden />{a.label}</Link>))}
            </nav>
          )}
        </div>
      </section>

      {dash && agents.some((a) => a.key === dash.agents.primary) && (
        <a href="#ai-companion" className="flex items-center gap-3 rounded-xl border bg-card px-3 py-2.5 text-table shadow-sm xl:hidden" data-testid="companion-jump">
          <AgentAvatar agentKey={dash.agents.primary} size="sm" />
          <span className="min-w-0 flex-1"><span className="block font-semibold text-heading">Ask {agents.find((a) => a.key === dash.agents.primary)?.name}</span>
            <span className="block truncate text-label text-muted-foreground">{agents.find((a) => a.key === dash.agents.primary)?.role} · HMS Intelligence</span></span>
          <ArrowRight className="size-4 text-primary" aria-hidden />
        </a>
      )}

      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_21rem]">
        <div className="min-w-0 space-y-5">
          {q.isLoading ? <LoadingRows rows={2} /> : (
            <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-5" data-testid="home-metrics">
              {dash?.metrics.map((m) => {
                const Icon = METRIC_ICON[m.key] ?? Activity;
                return (
                  <li key={m.key}>
                    <Link to={m.link} className="flex h-full items-start gap-3 rounded-xl border bg-card p-3.5 shadow-sm transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60" data-metric={m.key}>
                      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground"><Icon className="size-4" aria-hidden /></span>
                      <span className="min-w-0"><span className="block text-label font-medium text-muted-foreground">{m.label}</span>
                        <span className={cn("block text-2xl font-semibold tabular text-heading", m.value === 0 && "text-muted-foreground")}>{m.value}</span>
                        {m.sub && <span className={cn("mt-0.5 inline-flex rounded-full px-1.5 py-0.5 text-label font-medium", TONE[m.tone ?? "neutral"] ?? TONE.neutral)}>{m.sub}</span>}</span>
                    </Link>
                  </li>);
              })}
            </ul>
          )}

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <SectionCard title={dash?.queue?.title ?? "Today"} icon={CalendarClock} link={dash?.queue?.link} testId="home-queue">
              {q.isLoading ? <LoadingRows rows={4} /> : <QueueList s={dash?.queue ?? null} tz={tz} empty="Nothing waiting in this queue right now." />}
            </SectionCard>
            {q.isLoading ? <Card><LoadingRows rows={4} /></Card> : <Attention items={d?.priorities ?? []} total={totalWork} />}
          </div>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <RecentAI items={dash?.ai_recent ?? []} agents={agents} open={open} />
            {dash?.automation && <AutomationCard a={dash.automation} />}
          </div>
          {dash?.extra && (
            <SectionCard title={dash.extra.title} icon={Siren} link={dash.extra.link} testId="home-extra">
              <QueueList s={dash.extra} tz={tz} empty="Nothing here right now." />
            </SectionCard>
          )}
          <p className="text-label text-muted-foreground">Live data · updated {q.dataUpdatedAt ? ago(new Date(q.dataUpdatedAt).toISOString()) : "—"} · times in {tz.replace("_", " ")}</p>
        </div>

        <aside id="ai-companion" className="scroll-mt-20 space-y-4 xl:sticky xl:top-20" aria-label="AI agents">
          {dash && <Companion primary={dash.agents.primary} agents={agents} patients={patients} live={provider.data?.live} featureOn={!!ag.data?.feature_enabled} open={open} />}
          {dash && <Team keys={dash.agents.secondary} agents={agents} open={open} />}
        </aside>
      </div>
      {sheet && <HMSAssistSheet agent={sheet.agent} context={sheet.ctx} open onOpenChange={(o) => !o && setSheet(null)} />}
    </div>
  );
}
