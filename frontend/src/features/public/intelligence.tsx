/** HMS Intelligence presentation components for the public website (agent identities, explorer, conversation, flow). */
import { ArrowRight, Bot, CheckCircle2, Hand, MessageSquareText, ScanSearch, ShieldCheck, UserRound, Wrench } from "lucide-react";
import * as React from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { AGENTS, type AgentProfile, type Turn } from "./agents";

export function AgentAvatar({ a, size = "md", className }: { a: AgentProfile; size?: "sm" | "md" | "lg"; className?: string }) {
  const dim = { sm: "size-9 text-body", md: "size-11 text-section", lg: "size-14 text-xl" }[size];
  return (
    <span className={cn("relative grid shrink-0 place-items-center rounded-xl font-semibold text-white shadow-sm ring-1 ring-black/5", dim, className)}
      style={{ backgroundColor: a.hue }} aria-hidden>
      {a.name[0]}
      <span className="absolute -bottom-1 -right-1 grid size-5 place-items-center rounded-md bg-card ring-1 ring-border"><a.icon className="size-3" style={{ color: a.hue }} /></span>
    </span>
  );
}

/** Compact team grid (Home). Each tile deep-links to the agent on the AI page. */
export function AgentTeamGrid({ dark }: { dark?: boolean }) {
  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="agent-team">
      {AGENTS.map((a) => (
        <li key={a.key} data-agent={a.key}>
          <Link to={`/ai-automation#agent-${a.key}`} className={cn("group flex h-full flex-col rounded-xl border p-4 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
            dark ? "border-white/15 bg-white/[0.04] hover:border-white/40 hover:bg-white/[0.08]" : "bg-card hover:border-primary/40")}>
            <AgentAvatar a={a} />
            <span className={cn("mt-3 text-lg font-semibold tracking-tight", dark ? "text-white" : "text-heading")}>{a.name}</span>
            <span className={cn("text-label font-medium", dark ? "text-white/70" : "text-muted-foreground")}>{a.role}</span>
            <span className={cn("mt-2 flex-1 text-table leading-relaxed", dark ? "text-white/80" : "text-muted-foreground")}>{a.tagline}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function Conversation({ turns, agent, className }: { turns: Turn[]; agent: AgentProfile; className?: string }) {
  return (
    <div className={cn("rounded-xl border bg-card shadow-sm", className)} data-testid="agent-conversation">
      <div className="flex items-center gap-2 border-b px-4 py-2.5">
        <AgentAvatar a={agent} size="sm" />
        <div className="min-w-0"><p className="text-body font-semibold text-heading">{agent.name}</p><p className="truncate text-label text-muted-foreground">{agent.role} · illustrative conversation, synthetic data</p></div>
      </div>
      <ol className="space-y-2.5 p-4 text-table">
        {turns.map((t, i) => (
          <li key={i} className={cn("max-w-[88%] rounded-lg px-3 py-2 leading-relaxed",
            t.from === "staff" ? "ml-auto bg-primary text-primary-foreground" : t.from === "agent" ? "border bg-subtle text-foreground" : "mx-auto max-w-full border border-success/30 bg-success-soft text-center text-label font-medium text-success")}>
            {t.from === "system" && <CheckCircle2 className="mr-1 inline size-3.5 -translate-y-px" aria-hidden />}{t.text}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Facts({ title, items, icon: Icon, tone }: { title: string; items: string[]; icon: React.ElementType; tone: "primary" | "warning" | "success" | "muted" }) {
  if (!items.length) return null;
  const c = { primary: "text-primary", warning: "text-warning-foreground", success: "text-success", muted: "text-muted-foreground" }[tone];
  return (
    <div>
      <p className="flex items-center gap-1.5 text-label font-semibold uppercase tracking-wider text-muted-foreground"><Icon className={cn("size-3.5", c)} aria-hidden />{title}</p>
      <ul className="mt-1.5 space-y-1 text-table leading-relaxed text-foreground">{items.map((x) => <li key={x} className="flex gap-2"><span className={cn("mt-2 size-1 shrink-0 rounded-full bg-current", c)} aria-hidden />{x}</li>)}</ul>
    </div>
  );
}

/** Agent explorer (AI page): pick an agent; its role, workplace, questions, actions, approvals, limits and an example. */
export function AgentExplorer() {
  const { hash } = useLocation();
  const fromHash = AGENTS.find((a) => hash === `#agent-${a.key}`)?.key;
  const [sel, setSel] = React.useState(fromHash ?? AGENTS[0].key);
  React.useEffect(() => { if (fromHash) setSel(fromHash); }, [fromHash]);
  const a = AGENTS.find((x) => x.key === sel)!;
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]" data-testid="agent-explorer">
      <ul className="grid min-w-0 grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-1" aria-label="HMS Intelligence agents">
        {AGENTS.map((x) => (
          <li key={x.key} data-agent={x.key}>
            <button type="button" id={`agent-${x.key}`} aria-pressed={x.key === sel} onClick={() => setSel(x.key)}
              className={cn("flex w-full scroll-mt-28 items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
                x.key === sel ? "border-primary/50 bg-accent/60" : "bg-card hover:border-primary/30")}>
              <AgentAvatar a={x} size="sm" />
              <span className="min-w-0"><span className="block text-body font-semibold text-heading">{x.name}</span><span className="block truncate text-label text-muted-foreground">{x.role}</span></span>
            </button>
          </li>
        ))}
      </ul>
      <article className="min-w-0 rounded-2xl border bg-card p-5 shadow-sm sm:p-7" aria-live="polite" data-testid="agent-detail">
        <div className="flex flex-wrap items-start gap-4">
          <AgentAvatar a={a} size="lg" />
          <div className="min-w-0 flex-1">
            <h3 className="text-2xl font-semibold tracking-tight text-heading">{a.name} <span className="font-normal text-muted-foreground">— {a.role}</span></h3>
            <p className="mt-1 text-section font-medium" style={{ color: a.hue }}>{a.tagline}</p>
          </div>
        </div>
        <p className="mt-4 text-body leading-relaxed text-foreground">{a.summary}</p>
        <dl className="mt-4 grid gap-2 text-table sm:grid-cols-2">
          <div className="rounded-lg border bg-subtle px-3 py-2"><dt className="text-label font-medium text-muted-foreground">Works with</dt><dd className="font-medium text-heading">{a.team}</dd></div>
          <div className="rounded-lg border bg-subtle px-3 py-2"><dt className="text-label font-medium text-muted-foreground">Where it lives</dt><dd className="font-medium text-heading">{a.where}</dd></div>
        </dl>
        <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="space-y-5">
            <div>
              <p className="flex items-center gap-1.5 text-label font-semibold uppercase tracking-wider text-muted-foreground"><MessageSquareText className="size-3.5 text-primary" aria-hidden />Employees ask</p>
              <ul className="mt-2 flex flex-wrap gap-1.5">{a.ask.map((q) => <li key={q} className="rounded-full border bg-card px-3 py-1 text-table text-heading">“{q}”</li>)}</ul>
            </div>
            <Facts title="Reads and explains" items={a.helps} icon={ScanSearch} tone="primary" />
            <Facts title="Proposes — a different authorized person approves" items={a.approval} icon={ShieldCheck} tone="warning" />
            <Facts title="Prepares — runs only after the employee confirms" items={a.confirm} icon={Hand} tone="success" />
            <Facts title="Never does" items={a.never} icon={Wrench} tone="muted" />
            {a.automation && <p className="rounded-lg border border-dashed px-3 py-2 text-table text-muted-foreground"><span className="font-medium text-heading">Automation: </span>{a.automation}</p>}
          </div>
          <Conversation turns={a.example} agent={a} />
        </div>
      </article>
    </div>
  );
}

const FLOW = [
  { icon: UserRound, title: "An employee asks", text: "From the case, claim, stay, thread, chart or document they are working on — in plain language, with follow-up questions." },
  { icon: ScanSearch, title: "The agent reads authorized context", text: "The record is re-checked against the employee's access on every message; tools are pinned to that record." },
  { icon: Bot, title: "It prepares the next step", text: "An explanation with references, a task or message proposal, or a small internal action to confirm." },
  { icon: ShieldCheck, title: "A person decides", text: "The employee confirms their own action; anything else waits for a different authorized approver in My Work." },
  { icon: CheckCircle2, title: "The real result is tracked", text: "The conversation shows the backend outcome — executed, rejected or failed — with a link to the created task." },
];

export function ConversationToAction({ dark }: { dark?: boolean }) {
  return (
    <ol className="grid grid-cols-1 gap-3 md:grid-cols-5" data-testid="action-flow">
      {FLOW.map((s, i) => (
        <li key={s.title} className={cn("relative rounded-xl border p-4", dark ? "border-white/15 bg-white/[0.04]" : "bg-card")}>
          <span className={cn("grid size-9 place-items-center rounded-lg", dark ? "bg-white text-brand-navy" : "bg-primary text-primary-foreground")}><s.icon className="size-5" aria-hidden /></span>
          <p className={cn("mt-3 text-label font-semibold tabular", dark ? "text-white/60" : "text-muted-foreground")}>Step {i + 1}</p>
          <p className={cn("text-section font-semibold", dark ? "text-white" : "text-heading")}>{s.title}</p>
          <p className={cn("mt-1 text-table leading-relaxed", dark ? "text-white/75" : "text-muted-foreground")}>{s.text}</p>
          {i < FLOW.length - 1 && <ArrowRight className={cn("absolute -right-2.5 top-1/2 hidden size-4 -translate-y-1/2 md:block", dark ? "text-white/40" : "text-muted-foreground")} aria-hidden />}
        </li>
      ))}
    </ol>
  );
}
