import {
  ArrowRight, ClipboardCheck, FlaskConical, HeartPulse, Info, KeyRound, Lock, Pill, Receipt, ScanLine, ScrollText,
  ShieldAlert, Siren, Sparkles, Stethoscope, UserPlus, UsersRound, BedDouble, Hospital,
} from "lucide-react";
import { Link } from "react-router-dom";
import { ProvenanceChip } from "@/components/common/Status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LoginForm } from "@/features/auth/LoginForm";
import { CODE_SET_NOTICES, COPYRIGHT_NOTICE, PRODUCT_TAGLINE, THIRD_PARTY } from "@/lib/legal";
import { cn } from "@/lib/utils";
import { AgentExplorer, AgentTeamGrid, Conversation, ConversationToAction } from "./intelligence";
import { AGENTS, INTELLIGENCE } from "./agents";
import {
  AccessButton, AnchorChips, AutomationFlow, CheckList, ConnectedHospitalDiagram, Eyebrow, H2, PageHero, PathwayExplorer,
  ProductShot, Section, SectionIntro, StatusList,
} from "./components";
import {
  APPROACH, CLINICAL, LAYERS, MONITOR_COUNT, MONITOR_GROUPS, OPERATIONS, PHILOSOPHY, PILLARS,
  PROBLEMS, RESPONSIBLE, REVENUE, SECURITY, SHOTS, type ShotKey, TEAMS, type Team,
} from "./content";
import { BrandMark, PublicLayout } from "./PublicLayout";

const VERSION = import.meta.env.VITE_APP_VERSION ?? "development";

const DEPARTMENTS = [
  { name: "Front desk", icon: UserPlus }, { name: "Doctors", icon: Stethoscope }, { name: "Nursing", icon: HeartPulse }, { name: "Emergency", icon: Siren },
  { name: "Beds", icon: BedDouble }, { name: "Laboratory", icon: FlaskConical }, { name: "Radiology", icon: ScanLine }, { name: "Pharmacy", icon: Pill },
  { name: "Insurance", icon: ClipboardCheck }, { name: "Billing", icon: Receipt }, { name: "Administration", icon: Hospital }, { name: "Patients", icon: UsersRound },
];

/** Closing call to action shared by every page: the tagline, Sign in, and one secondary link. */
function FinalCta({ secondary = { to: "/platform", label: "See how it works" } }: { secondary?: { to: string; label: string } }) {
  return (
    <Section tone="brand" labelledBy="cta-title" className="text-center">
      <div className="mx-auto max-w-3xl">
        <BrandMark className="mx-auto size-12" />
        <h2 id="cta-title" className="mt-6 text-3xl font-semibold tracking-tight text-balance text-white sm:text-4xl">{PRODUCT_TAGLINE}</h2>
        <p className="mx-auto mt-4 max-w-2xl text-section leading-relaxed text-white/80 sm:text-lead">{PHILOSOPHY}</p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <AccessButton className="bg-white text-brand-navy hover:bg-white/90" />
          <Button asChild size="lg" variant="outline" className="border-white/40 bg-transparent text-white hover:bg-white/10 hover:text-white">
            <Link to={secondary.to}>{secondary.label}<ArrowRight /></Link>
          </Button>
        </div>
        <p className="mt-6 text-table text-white/70">HMS Workflows is in development and tested with synthetic data. Accounts are issued by a hospital administrator.</p>
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------------------------- Home

export function HomePage() {
  return (
    <PublicLayout>
      {/* 1. Hero */}
      <section className="relative overflow-hidden bg-brand-navy px-4 pb-20 pt-14 text-white sm:px-6 lg:pb-28 lg:pt-20" aria-labelledby="home-title">
        <div className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(to_right,white_1px,transparent_1px),linear-gradient(to_bottom,white_1px,transparent_1px)] [background-size:48px_48px]" aria-hidden />
        <div className="relative mx-auto grid max-w-7xl grid-cols-1 items-center gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-14">
          <div>
            <p className="mb-4 flex items-center gap-2 text-label font-semibold uppercase tracking-[0.14em] text-white/70"><BrandMark className="size-5" />HMS Workflows</p>
            <h1 id="home-title" className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl lg:text-6xl lg:leading-[1.05]">Your Entire Hospital. <span className="text-sky-300">Working as One.</span></h1>
            <p className="mt-6 max-w-xl text-lead leading-relaxed text-white/85 text-pretty">Clinical care, hospital operations, revenue, automation and ten department AI agents on one platform — so every team works from the same patient, sees what is waiting, and knows who owns the next step.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <AccessButton className="bg-white text-brand-navy hover:bg-white/90" />
              <Button asChild size="lg" variant="outline" className="border-white/40 bg-transparent text-white hover:bg-white/10 hover:text-white"><Link to="/ai-automation">Meet HMS Intelligence<ArrowRight /></Link></Button>
            </div>
            <p className="mt-6 text-table text-white/65">Real screens with synthetic data: the Command Center and Aurelia working on an insurance case. In development; not certified for clinical use.</p>
          </div>
          <div className="relative lg:pb-10">
            <ProductShot shot="commandCenter" priority caption={false} sizes="(min-width: 1024px) 56vw, 100vw" className="border-white/10" />
            <ProductShot shot="assistCoverage" caption={false} sizes="380px" className="absolute -bottom-6 -left-10 hidden w-[46%] border-white/10 ring-1 ring-black/20 lg:block" />
          </div>
        </div>
      </section>

      {/* 2. The problem */}
      <Section tone="subtle" labelledBy="problem-title">
        <SectionIntro eyebrow="The problem" id="problem-title" title="Hospitals don't fail for lack of data. They fail at the hand-offs.">
          Registration, wards, pharmacy, the lab, bed management, insurance and billing each depend on what the others have done. When their systems and follow-ups are disconnected, work waits silently until a patient is affected.
        </SectionIntro>
        <ul className="mt-10 grid gap-4 md:grid-cols-2" data-testid="problems">
          {PROBLEMS.map((p) => (
            <li key={p.title} className="flex flex-col overflow-hidden rounded-xl border bg-card">
              <div className="flex-1 p-5">
                <p className="flex items-center gap-2.5 text-section font-semibold text-heading"><span className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted"><p.icon className="size-5 text-muted-foreground" aria-hidden /></span>{p.title}</p>
                <p className="mt-3 text-body leading-relaxed text-muted-foreground">{p.problem}</p>
              </div>
              <div className="border-t border-primary/15 bg-accent/40 px-5 py-4"><p className="text-body leading-relaxed text-heading"><span className="font-semibold">HMS Workflows: </span>{p.helps}</p></div>
            </li>
          ))}
        </ul>
      </Section>

      {/* 3. One connected hospital */}
      <Section labelledBy="connected-title">
        <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-14">
          <SectionIntro eyebrow="One connected hospital" id="connected-title" title="Every department, one patient, one record of the work.">
            Four connected parts of one platform. Each team has its own workspace, and every hand-off between them is recorded, owned and followed through.
          </SectionIntro>
          <ConnectedHospitalDiagram departments={DEPARTMENTS} />
        </div>
        <ul className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4" data-testid="pillars">
          {PILLARS.map((p) => (
            <li key={p.id}>
              <Link to={p.to} className="group flex h-full flex-col rounded-xl border bg-card p-5 transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
                <span className="grid size-10 place-items-center rounded-lg bg-primary text-primary-foreground"><p.icon className="size-5" aria-hidden /></span>
                <span className="mt-4 text-lg font-semibold text-heading">{p.title}</span>
                <span className="mt-1.5 text-body leading-relaxed text-muted-foreground">{p.text}</span>
                <CheckList items={p.includes} className="mt-4 flex-1 text-table" />
                <span className="mt-5 inline-flex items-center gap-1 text-table font-medium text-primary">Learn more<ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" /></span>
              </Link>
            </li>
          ))}
        </ul>
        <div className="mt-14">
          <h3 className="text-xl font-semibold tracking-tight text-heading">Follow a patient through the hospital</h3>
          <p className="mt-1 text-body text-muted-foreground">Choose a pathway. Where something can stall, a monitor watches for it.</p>
          <div className="mt-6"><PathwayExplorer /></div>
        </div>
      </Section>

      {/* 4. Clinical EHR */}
      <FeatureBand id="clinical" eyebrow="Clinical EHR" title="A complete clinical record, built for the team around the patient." items={CLINICAL} shot="patientChart"
        caption="Patient chart with allergies, flagged vitals, problems and medications. Synthetic data." tone="subtle" />

      {/* 5. Hospital operations */}
      <FeatureBand id="operations" eyebrow="Hospital operations" title="The departments that keep patients moving." items={OPERATIONS} shot="edBoard" reverse
        caption="Emergency department tracking board. Synthetic data." />

      {/* 6. Meet HMS Intelligence */}
      <Section tone="brand" labelledBy="intelligence-title" width="max-w-7xl">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-3xl">
            <Eyebrow className="text-sky-300">HMS Intelligence</Eyebrow>
            <h2 id="intelligence-title" className="text-3xl font-semibold tracking-tight text-balance text-white sm:text-4xl">Ten AI agents. Each one at home in its department.</h2>
            <p className="mt-4 text-section leading-relaxed text-white/80 sm:text-lead">{INTELLIGENCE.text}</p>
          </div>
          <Button asChild size="lg" className="bg-white text-brand-navy hover:bg-white/90"><Link to="/ai-automation#agents">Meet the team<ArrowRight /></Link></Button>
        </div>
        <div className="mt-10"><AgentTeamGrid dark /></div>
      </Section>

      {/* 7. From conversation to action */}
      <Section labelledBy="action-title" width="max-w-7xl">
        <SectionIntro eyebrow="From conversation to action" id="action-title" title="Real work, not a chatbot that says it's done.">
          The agent's tools are the same backend actions the application uses, with the same permissions. Status comes from the database — never from the AI's own words.
        </SectionIntro>
        <div className="mt-10"><ConversationToAction /></div>
        <div className="mt-10 grid grid-cols-1 items-start gap-8 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          <ProductShot shot="assistCoverage" caption="Aurelia on an insurance case: the follow-up was approved by a different person and the task was created. Synthetic data; rule-based mode." sizes="(min-width: 1024px) 55vw, 100vw" />
          <Conversation turns={AGENTS[0].example} agent={AGENTS[0]} />
        </div>
      </Section>

      {/* 8. 22 monitors */}
      <Section tone="subtle" labelledBy="monitors-home-title">
        <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
          <div>
            <SectionIntro eyebrow={`${MONITOR_COUNT} automation monitors`} id="monitors-home-title" title="Rules find the problem. People and AI agents handle it.">
              Rule-based monitors check hospital records on a schedule. When a defined condition is true they open one case for the owning team, and close it when the record shows the problem is gone.
            </SectionIntro>
            <dl className="mt-8 grid grid-cols-3 gap-3" data-testid="monitor-summary">
              {([[MONITOR_COUNT, "rule-based monitors"], [6, "with AI assistance on by default"], [3, "safety-critical — never AI"]] as const).map(([n, l]) => (
                <div key={l} className="rounded-xl border bg-card p-4"><dt className="text-label text-muted-foreground">{l}</dt><dd className="text-3xl font-semibold tabular text-heading">{n}</dd></div>))}
            </dl>
            <p className="mt-4 text-table text-muted-foreground">AI assistance can be switched on for 7 more monitors. Critical lab and imaging results and ED door-to-provider always stay rule-based.</p>
            <Link to="/ai-automation#monitors" className="mt-5 inline-flex items-center gap-1 text-body font-medium text-primary hover:underline">See all {MONITOR_COUNT} monitors<ArrowRight className="size-4" /></Link>
          </div>
          <ProductShot shot="monitors" caption="Monitors & rules with per-monitor AI switches. Synthetic data." sizes="(min-width: 1024px) 50vw, 100vw" />
        </div>
      </Section>

      {/* 9. Revenue and administration */}
      <FeatureBand id="revenue" eyebrow="Revenue & administration" title="Coverage, authorizations and claims, before they become denials." items={REVENUE} shot="insuranceGuardian"
        caption="Insurance Guardian: coverage of upcoming visits; the payer connection is simulated. Synthetic data." />

      {/* 10. Security and human control */}
      <Section tone="subtle" labelledBy="security-title">
        <SectionIntro eyebrow="Security & human control" id="security-title" title="Built so that people stay in charge.">
          Controls are enforced by the server and the database, not only by the screens. HMS Workflows is in development, tested with synthetic data, and is not certified or represented as HIPAA-compliant.
        </SectionIntro>
        <ul className="mt-10 grid gap-x-8 gap-y-7 sm:grid-cols-2 lg:grid-cols-3" data-testid="security">
          {SECURITY.map((w) => (
            <li key={w.title} className="flex gap-3"><w.icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
              <span><span className="block text-section font-semibold text-heading">{w.title}</span><span className="mt-1 block text-body leading-relaxed text-muted-foreground">{w.text}</span></span></li>
          ))}
        </ul>
      </Section>

      {/* 11. Product screens */}
      <Section labelledBy="screens-title" width="max-w-7xl">
        <SectionIntro eyebrow="Product" id="screens-title" title="The real application." >Screenshots of HMS Workflows with synthetic data — nothing here is a mock-up.</SectionIntro>
        <ul className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-2" data-testid="screens">
          {(["assistChart", "myWork", "agentStudio", "doctorHome"] as const).map((k) => <li key={k}><ProductShot shot={k} caption={SHOTS[k].alt.replace(/ \(synthetic data\)$/, ".")} sizes="(min-width: 768px) 45vw, 100vw" /></li>)}
        </ul>
      </Section>

      {/* 12. Final CTA */}
      <FinalCta secondary={{ to: "/platform", label: "See how it works" }} />
    </PublicLayout>
  );
}

function FeatureBand({ id, eyebrow, title, items, shot, caption, tone = "plain", reverse }: {
  id: string; eyebrow: string; title: string; items: { title: string; text: string }[]; shot: ShotKey; caption: string; tone?: "plain" | "subtle"; reverse?: boolean;
}) {
  return (
    <Section id={id} tone={tone} labelledBy={`${id}-title`} width="max-w-7xl">
      <div className={cn("grid grid-cols-1 items-center gap-10 lg:grid-cols-2 lg:gap-14", reverse && "lg:[&>*:first-child]:order-2")}>
        <div>
          <SectionIntro eyebrow={eyebrow} id={`${id}-title`} title={title} />
          <ul className="mt-8 grid gap-x-6 gap-y-5 sm:grid-cols-2" data-testid={`${id}-features`}>
            {items.map((f) => <li key={f.title} className="border-l-2 border-primary/30 pl-3"><p className="text-section font-semibold text-heading">{f.title}</p><p className="mt-1 text-table leading-relaxed text-muted-foreground">{f.text}</p></li>)}
          </ul>
        </div>
        <ProductShot shot={shot} caption={caption} sizes="(min-width: 1024px) 50vw, 100vw" />
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------------------------- Platform / How it works

export function PlatformPage() {
  return (
    <PublicLayout>
      <PageHero eyebrow="How it works" title="Five connected layers, from the patient record to the whole hospital."
        text="HMS Workflows is built in layers. Each one depends on the layer below it: shared records make department workspaces possible, workspaces feed coordinated workflows, automation watches those workflows, and visibility shows the result."
        aside={
          <ol className="grid gap-2" aria-label="Platform layers" data-testid="layer-stack">
            {[...LAYERS].reverse().map((l) => (
              <li key={l.id}>
                <Link to={`#${l.id}`} className="group flex items-center gap-3 rounded-xl border bg-card px-4 py-3 shadow-sm transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
                  style={{ marginInline: `${(l.n - 1) * 0.6}rem` }}>
                  <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground"><l.icon className="size-4" aria-hidden /></span>
                  <span className="min-w-0"><span className="block text-label font-semibold text-primary">Layer {l.n}</span><span className="block text-body font-semibold text-heading">{l.title}</span></span>
                  <ArrowRight className="ml-auto size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" aria-hidden />
                </Link>
              </li>
            ))}
          </ol>
        }
      />
      {LAYERS.map((l, i) => (
        <Section key={l.id} id={l.id} tone={i % 2 ? "subtle" : "plain"} labelledBy={`${l.id}-title`}>
          <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-14">
            <div className={cn(i % 2 && "lg:order-2")}>
              <p className="flex items-center gap-2 text-label font-semibold uppercase tracking-[0.12em] text-primary"><l.icon className="size-4" aria-hidden />Layer {l.n} of 5</p>
              <H2 id={`${l.id}-title`} className="mt-3">{l.title}</H2>
              <p className="mt-3 text-lead font-medium leading-relaxed text-heading">{l.summary}</p>
              <p className="mt-4 text-body leading-relaxed text-muted-foreground">{l.body}</p>
              <CheckList items={l.points} className="mt-6 grid gap-2 space-y-0 sm:grid-cols-2" />
              <div className="mt-6 rounded-lg border-l-4 border-primary bg-accent/40 px-4 py-3">
                <p className="text-label font-semibold uppercase tracking-wider text-accent-foreground">In practice</p>
                <p className="mt-1 text-body leading-relaxed text-heading">{l.example}</p>
              </div>
              {l.status && <p className="mt-4 flex gap-2 text-table leading-relaxed text-muted-foreground"><Info className="mt-0.5 size-4 shrink-0" aria-hidden />{l.status}</p>}
              {l.id === "automation" && <Button asChild variant="outline" className="mt-6"><Link to="/ai-automation">Explore AI & Automation<ArrowRight /></Link></Button>}
            </div>
            {l.shot && <ProductShot shot={l.shot} className={cn(i % 2 && "lg:order-1")} caption={l.shotCaption ?? true} sizes="(min-width: 1024px) 50vw, 100vw" />}
          </div>
        </Section>
      ))}
      <Section tone="subtle" labelledBy="security-title">
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-14">
          <div>
            <Eyebrow>Underneath every layer</Eyebrow>
            <H2 id="security-title">Access by role. Actions on the record.</H2>
            <ul className="mt-6 space-y-4 text-body">
              {([[UsersRound, "Facilities, departments and staff invitations with role-based access, enforced again on the server."],
                [ScrollText, "An audit log of user actions, including AI runs and approvals."],
                [KeyRound, "AI provider keys are stored encrypted on the server and never shown in the browser."],
                [Lock, "Sending patient information to an external AI provider is off unless an administrator enables it."]] as const).map(([Icon, t]) => (
                <li key={t} className="flex gap-3"><Icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden /><span className="leading-relaxed text-muted-foreground">{t}</span></li>
              ))}
            </ul>
          </div>
          <div className="rounded-xl border bg-card p-6">
            <h3 className="text-xl font-semibold tracking-tight text-heading">Integration status</h3>
            <p className="mt-2 text-body leading-relaxed text-muted-foreground">External connections sit behind adapters. Until a real, contracted partner is connected, each one is simulated and labelled <em>Simulated</em> in the application:</p>
            <ul className="mt-4 flex flex-wrap gap-2">
              {["Payer eligibility", "Claims clearinghouse", "Card payments", "e-Prescribing", "Lab & imaging interfaces", "Imaging archive (PACS)", "Supplier orders", "Email & text delivery"].map((t) => (
                <li key={t}><Badge variant="neutral">{t}</Badge></li>
              ))}
            </ul>
            <Link to="/about#status" className="mt-5 inline-flex items-center gap-1 text-body font-medium text-primary hover:underline">Full development status<ArrowRight className="size-4" /></Link>
          </div>
        </div>
      </Section>
      <FinalCta secondary={{ to: "/solutions", label: "Solutions by team" }} />
    </PublicLayout>
  );
}

// ---------------------------------------------------------------------------------------------- Solutions

function TeamExample({ t }: { t: Team }) {
  if (!t.example) return null;
  return (
    <figure className="rounded-xl border bg-card p-6 shadow-[0_12px_40px_rgba(16,24,40,0.06)]">
      <figcaption className="text-section font-semibold text-heading">{t.example.title}</figcaption>
      <ol className="mt-5 space-y-0">
        {t.example.steps.map((s, i) => (
          <li key={s} className="relative flex items-center gap-3 pb-4 last:pb-0">
            {i < t.example!.steps.length - 1 && <span className="absolute left-4 top-8 h-[calc(100%-1.5rem)] w-px bg-border" aria-hidden />}
            <span className="relative grid size-8 shrink-0 place-items-center rounded-full bg-accent text-table font-semibold text-accent-foreground" aria-hidden>{i + 1}</span>
            <span className="text-body text-heading">{s}</span>
          </li>
        ))}
      </ol>
      <p className="mt-5 border-t pt-4 text-table text-muted-foreground">Workflow as implemented. Laboratory interface transmission is simulated.</p>
    </figure>
  );
}

export function SolutionsPage() {
  return (
    <PublicLayout>
      <PageHero eyebrow="Solutions" title="Built around the work each hospital team does."
        text="Every team has its own pressures. HMS Workflows gives each one a workspace for its responsibilities — and connects it to the teams it receives work from and hands work to.">
        <AnchorChips label="Teams" items={TEAMS} />
      </PageHero>
      {TEAMS.map((t, i) => (
        <Section key={t.id} id={t.id} tone={i % 2 ? "subtle" : "plain"} labelledBy={`${t.id}-title`}>
          <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-14">
            <div className={cn(i % 2 && "lg:order-2")}>
              <p className="flex items-center gap-2 text-label font-semibold uppercase tracking-[0.12em] text-primary"><t.icon className="size-4" aria-hidden />{t.title}</p>
              <H2 id={`${t.id}-title`} className="mt-3">{t.short}</H2>
              <div className="mt-6">
                <p className="text-label font-semibold uppercase tracking-wider text-muted-foreground">The challenge</p>
                <p className="mt-1.5 text-body leading-relaxed text-foreground">{t.struggle}</p>
              </div>
              <div className="mt-6">
                <p className="text-label font-semibold uppercase tracking-wider text-muted-foreground">How HMS Workflows supports it</p>
                <CheckList items={t.support} className="mt-2" />
              </div>
              <dl className="mt-6 grid gap-3 rounded-xl border bg-card p-4 sm:grid-cols-2">
                <div><dt className="text-label font-semibold text-accent-foreground">Receives</dt><dd className="mt-1 text-table leading-relaxed text-muted-foreground">{t.receives}</dd></div>
                <div><dt className="text-label font-semibold text-accent-foreground">Hands off</dt><dd className="mt-1 text-table leading-relaxed text-muted-foreground">{t.handsOff}</dd></div>
              </dl>
            </div>
            <div className={cn(i % 2 && "lg:order-1")}>
              {t.shot ? <ProductShot shot={t.shot} caption={t.shotCaption ?? true} sizes="(min-width: 1024px) 50vw, 100vw" /> : <TeamExample t={t} />}
            </div>
          </div>
        </Section>
      ))}
      <FinalCta secondary={{ to: "/ai-automation", label: "AI & Automation" }} />
    </PublicLayout>
  );
}

// ---------------------------------------------------------------------------------------------- AI & Automation

export function AiAutomationPage() {
  return (
    <PublicLayout>
      <section className="relative overflow-hidden bg-brand-navy px-4 pb-16 pt-14 text-white sm:px-6 lg:pb-24 lg:pt-20" aria-labelledby="ai-title">
        <div className="relative mx-auto max-w-7xl">
          <p className="mb-4 text-label font-semibold uppercase tracking-[0.14em] text-sky-300">HMS Intelligence · AI & Automation</p>
          <h1 id="ai-title" className="max-w-4xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl lg:text-6xl lg:leading-[1.05]">Meet your hospital's AI team.</h1>
          <p className="mt-6 max-w-3xl text-lead leading-relaxed text-white/85">{INTELLIGENCE.line} {INTELLIGENCE.text}</p>
          <div className="mt-10"><AgentTeamGrid dark /></div>
          <nav aria-label="On this page" className="mt-10 flex flex-wrap gap-2 text-table">
            {[["agents", "The ten agents"], ["conversation", "Conversation to action"], ["monitors", `${MONITOR_COUNT} monitors`], ["responsible-ai", "Governance"]].map(([id, t]) => (
              <a key={id} href={`#${id}`} className="rounded-full border border-white/25 px-3 py-1.5 text-white/85 hover:bg-white/10">{t}</a>))}
          </nav>
        </div>
      </section>

      <Section id="agents" labelledBy="agents-title" width="max-w-7xl">
        <span id="assistants" className="block scroll-mt-24" aria-hidden />
        <SectionIntro eyebrow="The ten agents" id="agents-title" title="Specialized teammates — not ten copies of one chatbot.">
          Each agent has its own department, tools, permissions and limits. Choose one to see where it works, what staff ask it, what it can prepare, what needs approval, and what it will never do.
        </SectionIntro>
        <div className="mt-10"><AgentExplorer /></div>
      </Section>

      <Section id="conversation" tone="brand" labelledBy="conv-title" width="max-w-7xl">
        <Eyebrow className="text-sky-300">From conversation to action</Eyebrow>
        <h2 id="conv-title" className="max-w-3xl text-3xl font-semibold tracking-tight text-balance text-white sm:text-4xl">Three ways an agent helps — and who decides.</h2>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {[["Read and explain", "Answers from the records the employee may see, with case references or cited chart sources."],
            ["Confirm in chat", "Small internal steps — a case note, an eligibility re-check, a claim re-scrub, a scribe draft edit — run only when the employee presses Confirm, with their own permissions."],
            ["Request approval", "Tasks, patient messages, insurance requests and purchase quantities become proposals that a different authorized person approves in My Work."]].map(([t, d]) => (
            <div key={t} className="rounded-xl border border-white/15 bg-white/[0.04] p-5"><p className="text-section font-semibold text-white">{t}</p><p className="mt-2 text-body leading-relaxed text-white/75">{d}</p></div>))}
        </div>
        <div className="mt-10"><ConversationToAction dark /></div>
        <div className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <ProductShot shot="assistCoverage" caption="Aurelia: a proposal approved by a different person; the conversation shows the executed result and the task." className="border-white/10" sizes="(min-width: 1024px) 45vw, 100vw" />
          <ProductShot shot="assistChart" caption="Aster: cited answers from one chart; prescribing questions are refused." className="border-white/10" sizes="(min-width: 1024px) 45vw, 100vw" />
        </div>
      </Section>

      <Section id="monitors" labelledBy="monitors-title">
        <SectionIntro eyebrow="Automation monitors" id="monitors-title" title={`${MONITOR_COUNT} rule-based monitors watching for known problems.`}>
          Each monitor is a predefined check with thresholds an administrator can adjust. When its condition is true it opens one case for the owning team. Monitors are not AI. For selected monitors, an agent can assist each new or escalated case once — within daily and monthly AI limits — and can only propose actions for approval.
        </SectionIntro>
        <p className="mt-5 flex flex-wrap items-center gap-2 text-table text-muted-foreground">
          <span className="inline-flex items-center gap-1 rounded-full border border-ai/30 bg-ai-soft px-2 py-0.5 text-label font-medium text-ai"><Sparkles className="size-3" aria-hidden />AI may assist</span>
          On by default for these six; seven more can be switched on per monitor; critical lab and imaging results and ED door-to-provider stay rule-based only.
        </p>
        <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3" data-testid="monitor-groups">
          {MONITOR_GROUPS.map((g) => (
            <section key={g.id} aria-labelledby={`mg-${g.id}`} className="rounded-xl border bg-card">
              <h3 id={`mg-${g.id}`} className="flex items-center gap-2 border-b bg-subtle px-4 py-3 text-section font-semibold text-heading">
                <g.icon className="size-4 text-primary" aria-hidden />{g.title}<span className="ml-auto text-table font-medium text-muted-foreground">{g.monitors.length}</span>
              </h3>
              <ul className="divide-y">
                {g.monitors.map((m) => (
                  <li key={m.key} className="px-4 py-3" data-monitor={m.key}>
                    <p className="flex flex-wrap items-center gap-2 text-body font-semibold text-heading">{m.name}
                      {m.aiAssist && <span className="inline-flex items-center gap-1 rounded-full border border-ai/30 bg-ai-soft px-1.5 py-0.5 text-label font-medium text-ai"><Sparkles className="size-3" aria-hidden />AI may assist</span>}</p>
                    <p className="mt-1 text-table leading-relaxed text-muted-foreground">{m.checks}</p>
                    <p className="mt-1 text-label text-muted-foreground"><span className="font-medium text-heading">Goes to:</span> {m.owner}</p>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <div className="mt-12 rounded-2xl border bg-subtle p-6">
          <h3 className="text-section font-semibold text-heading">How a problem is handled</h3>
          <p className="mt-1 text-table text-muted-foreground">Dashed steps are optional: AI runs only for selected case types and only when an AI provider is enabled. Without it, the case and its tasks continue normally.</p>
          <AutomationFlow className="mt-6" />
        </div>
      </Section>

      <Section id="responsible-ai" tone="subtle" labelledBy="responsible-title">
        <div className="grid items-start gap-12 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
          <div>
            <SectionIntro eyebrow="Governance" id="responsible-title" title="Controls built into how AI is used." />
            <ul className="mt-8 grid gap-6 sm:grid-cols-2">
              {RESPONSIBLE.map((r) => (
                <li key={r.title} className="flex gap-3"><r.icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
                  <span><span className="block text-section font-semibold text-heading">{r.title}</span><span className="mt-1 block text-body leading-relaxed text-muted-foreground">{r.text}</span></span></li>
              ))}
            </ul>
          </div>
          <div>
            <ProductShot shot="agentStudio" caption="Agent Studio: departments, tools, connected monitors, run history and audited conversation review. Synthetic data." sizes="(min-width: 1024px) 45vw, 100vw" />
            <h3 className="mt-8 text-section font-semibold text-heading">Every result says where it came from</h3>
            <ul className="mt-3 space-y-2.5">
              {([["live", "A live AI provider produced this; the model is named."], ["simulated", "No AI provider was used; a rule-based answer instead."],
                ["draft", "AI-generated text a person has not yet reviewed."], ["rule", "Found by a rule-based monitor, not by AI."],
                ["pending", "A proposal waiting for a different person with permission."], ["completed", "Approved by a named person and carried out."]] as const).map(([k, d]) => (
                <li key={k} className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-4"><ProvenanceChip kind={k} className="w-fit sm:w-48 sm:justify-center" /><span className="text-table text-muted-foreground">{d}</span></li>
              ))}
            </ul>
          </div>
        </div>
        <p className="mt-12 rounded-xl border border-dashed bg-card p-5 text-body leading-relaxed text-muted-foreground">
          <strong className="font-semibold text-heading">What we do not claim.</strong> HMS Workflows is not certified for clinical use and is not represented as HIPAA-compliant.
          AI output is assistance that requires human review. Payer, clearinghouse and messaging connections are simulated. Agent names are product names, not people. See the <Link to="/about#status" className="font-medium text-primary hover:underline">development status</Link>.
        </p>
      </Section>
      <FinalCta secondary={{ to: "/platform#automation", label: "Where automation fits" }} />
    </PublicLayout>
  );
}

// ---------------------------------------------------------------------------------------------- About

export function PublicAboutPage() {
  return (
    <PublicLayout>
      <PageHero eyebrow="About" title="Why HMS Workflows exists"
        text="Hospitals depend on coordinated work across clinical and operational departments. HMS Workflows explores how one unified platform can make that work more visible, organized and actionable." />
      <Section labelledBy="why-created-title">
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-14">
          <div>
            <H2 id="why-created-title">Why it was created</H2>
            <div className="mt-5 space-y-4 text-lead leading-relaxed text-muted-foreground">
              <p>A patient's care moves across registration, doctors, nurses, the laboratory, pharmacy, bed management, insurance and billing. Each team has different responsibilities, but the work is connected.</p>
              <p>When those teams rely on separate tools and manual hand-offs, it becomes hard to see what is unfinished, who owns it, and what should happen next. HMS Workflows was created to bring that work into one environment.</p>
            </div>
          </div>
          <figure className="flex flex-col justify-center rounded-2xl bg-brand-navy p-8 text-white sm:p-10">
            <Eyebrow className="text-white/70">Our vision</Eyebrow>
            <blockquote className="text-2xl font-semibold leading-snug tracking-tight text-balance sm:text-3xl">
              A hospital where the right information reaches the right team, pending work has clear ownership, and technology helps employees coordinate care.
            </blockquote>
            <figcaption className="mt-6 text-body text-white/75">{PHILOSOPHY}</figcaption>
          </figure>
        </div>
      </Section>
      <Section tone="subtle" labelledBy="approach-title">
        <SectionIntro eyebrow="Our approach" id="approach-title" title="Six principles behind the platform." />
        <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="approach">
          {APPROACH.map(([t, d], i) => (
            <li key={t} className="rounded-xl border bg-card p-5">
              <span className="text-label font-semibold tabular text-primary">0{i + 1}</span>
              <p className="mt-1 text-section font-semibold text-heading">{t}</p>
              <p className="mt-1.5 text-body leading-relaxed text-muted-foreground">{d}</p>
            </li>
          ))}
        </ul>
      </Section>
      <Section id="status" labelledBy="status-title">
        <SectionIntro eyebrow="Development status" id="status-title" title="Where HMS Workflows stands today.">
          HMS Workflows is a developing healthcare software system with implemented workflows, tested with synthetic data. It is not a certified or deployed hospital product.
        </SectionIntro>
        <div className="mt-8"><StatusList /></div>
        <p className="mt-3 text-table text-muted-foreground">Version {VERSION}</p>
      </Section>
      <Section id="legal" tone="subtle" labelledBy="legal-title">
        <H2 id="legal-title">Copyright & legal</H2>
        <div className="mt-8 grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border bg-card p-5">
            <p className="text-section font-semibold text-heading" data-testid="about-copyright">{COPYRIGHT_NOTICE}</p>
            <p className="mt-1.5 text-body text-muted-foreground">HMS Workflows' original source code, design and documentation are protected by copyright. No license is granted except as agreed in writing with the copyright holder.</p>
          </div>
          <div className="rounded-xl border bg-card p-5">
            <p className="flex items-center gap-2 text-body font-semibold text-heading"><ShieldAlert className="size-4 text-warning" aria-hidden />Use limitations</p>
            <p className="mt-1.5 text-body text-muted-foreground">For use with synthetic data only. Not HIPAA-certified, not ONC-certified and not validated for clinical use. AI output is a draft that requires human review.</p>
          </div>
          <div className="rounded-xl border bg-card p-5">
            <p className="text-body font-semibold text-heading">Third-party software</p>
            <p className="mt-1.5 text-body text-muted-foreground">Open-source components remain under their own licenses and copyrights, which are not affected by the notice above.</p>
            <ul className="mt-3 grid gap-x-6 gap-y-1 text-body sm:grid-cols-2">{THIRD_PARTY.map((t) => <li key={t.name} className="flex justify-between gap-3"><span>{t.name}</span><span className="text-muted-foreground">{t.license}</span></li>)}</ul>
          </div>
          <div className="rounded-xl border bg-card p-5">
            <p className="text-body font-semibold text-heading">Clinical code sets</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-table text-muted-foreground">{CODE_SET_NOTICES.map((n) => <li key={n}>{n}</li>)}</ul>
          </div>
        </div>
      </Section>
    </PublicLayout>
  );
}

// ---------------------------------------------------------------------------------------------- /login

export function PublicLoginPage() {
  return (
    <PublicLayout>
      <section className="bg-subtle px-4 py-12 sm:px-6 lg:py-20">
        <div className="mx-auto grid max-w-5xl items-center gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)]">
          <div className="hidden lg:block">
            <Eyebrow>HMS Workflows</Eyebrow>
            <h1 className="text-4xl font-semibold tracking-tight text-heading">Sign in to your hospital workspace.</h1>
            <p className="mt-4 text-lead leading-relaxed text-muted-foreground">Your role decides what you see: your priorities, your department's worklists and the patients in your care.</p>
            <p className="mt-6 text-body text-muted-foreground">New to HMS Workflows? See <Link to="/platform" className="font-medium text-primary hover:underline">how it works</Link> or read <Link to="/about" className="font-medium text-primary hover:underline">why it exists</Link>.</p>
          </div>
          <div className="rounded-2xl border bg-card p-6 shadow-[0_8px_30px_rgba(16,24,40,0.08)] sm:p-8">
            <LoginForm autoFocus emailId="login-email" />
          </div>
        </div>
      </section>
    </PublicLayout>
  );
}
