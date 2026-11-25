import {
  ArrowRight, Bot, ClipboardCheck, FlaskConical, HeartPulse, Info, KeyRound, Lock, Pill, Receipt, ScanLine, ScrollText,
  ShieldAlert, Siren, Sparkles, Stethoscope, UserPlus, UsersRound, BedDouble, Hospital,
} from "lucide-react";
import { Link } from "react-router-dom";
import { ProvenanceChip } from "@/components/common/Status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LoginForm } from "@/features/auth/LoginForm";
import { CODE_SET_NOTICES, COPYRIGHT_NOTICE, PRODUCT_TAGLINE, THIRD_PARTY } from "@/lib/legal";
import { cn } from "@/lib/utils";
import {
  AccessButton, AnchorChips, AutomationFlow, CheckList, ConnectedHospitalDiagram, Eyebrow, H2, PageHero, PathwayExplorer,
  ProductShot, Section, SectionIntro, StatusList,
} from "./components";
import {
  APPROACH, ASSISTANTS, BLOCKS, DEFINITION, GUARDIAN_STEPS, LAYERS, MONITOR_COUNT, MONITOR_GROUPS, PHILOSOPHY, PILLARS,
  PROBLEMS, RESPONSIBLE, TEAMS, type Team, WHY,
} from "./content";
import { BrandMark, PublicLayout } from "./PublicLayout";

const VERSION = import.meta.env.VITE_APP_VERSION ?? "development";

const QUESTIONS = [
  "What is happening with this patient?", "Which department is responsible?", "What needs to happen next?", "Is anything delayed or missing?",
  "Who should resolve the problem?", "Can automation detect it?", "Can AI help staff understand and act?", "Has the problem actually been resolved?",
];

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
      {/* A. Hero */}
      <section className="overflow-hidden border-b bg-gradient-to-b from-accent/50 via-card to-card px-4 pb-16 pt-12 sm:px-6 lg:pb-24 lg:pt-20" aria-labelledby="home-title">
        <div className="mx-auto grid max-w-7xl items-center gap-12 lg:grid-cols-[minmax(0,6fr)_minmax(0,6fr)] lg:gap-14">
          <div>
            <Eyebrow>HMS Workflows — Connected hospital operations</Eyebrow>
            <h1 id="home-title" className="text-4xl font-semibold tracking-tight text-balance text-heading sm:text-5xl lg:leading-[1.1]">
              One Patient. One Connected Hospital. <span className="text-primary">Every Task Accounted For.</span>
            </h1>
            <p className="mt-6 text-lead leading-relaxed text-foreground text-pretty">{DEFINITION}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <AccessButton />
              <Button asChild size="lg" variant="outline"><Link to="/platform">See how it works<ArrowRight /></Link></Button>
            </div>
            <p className="mt-6 flex items-center gap-2 text-body font-medium text-heading" data-testid="hero-tagline">
              <BrandMark className="size-6" />{PRODUCT_TAGLINE}
            </p>
          </div>
          <div className="relative lg:pb-12">
            <ProductShot shot="commandCenter" priority caption="Command Center — synthetic data." sizes="(min-width: 1024px) 58vw, 100vw" />
            <ProductShot shot="myWork" caption={false} sizes="320px" className="absolute -bottom-2 -left-8 hidden w-[44%] lg:block" />
          </div>
        </div>
      </section>

      {/* Questions band */}
      <section aria-labelledby="questions-title" className="border-b bg-card px-4 py-10 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <h2 id="questions-title" className="text-center text-label font-semibold uppercase tracking-[0.12em] text-muted-foreground">Built to help every team answer</h2>
          <ul className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {QUESTIONS.map((q) => <li key={q} className="rounded-lg border bg-subtle px-3 py-2.5 text-body font-medium text-heading">{q}</li>)}
          </ul>
        </div>
      </section>

      {/* B. The coordination problem */}
      <Section tone="subtle" labelledBy="problem-title">
        <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-14">
          <SectionIntro eyebrow="The coordination problem" id="problem-title" title="A hospital has many teams. The patient journey is one connected process.">
            A single stay can involve registration, doctors, nurses, the laboratory, pharmacy, bed management, insurance and billing. Each team has its own
            responsibilities — but every one of them depends on what the others have done, and on knowing what is still left to do.
          </SectionIntro>
          <ConnectedHospitalDiagram departments={DEPARTMENTS} />
        </div>
        <ul className="mt-14 grid gap-4 md:grid-cols-2" data-testid="problems">
          {PROBLEMS.map((p) => (
            <li key={p.title} className="flex flex-col overflow-hidden rounded-xl border bg-card">
              <div className="flex-1 p-5">
                <p className="flex items-center gap-2.5 text-section font-semibold text-heading"><span className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted"><p.icon className="size-5 text-muted-foreground" aria-hidden /></span>{p.title}</p>
                <p className="mt-3 text-body leading-relaxed text-muted-foreground">{p.problem}</p>
              </div>
              <div className="border-t border-primary/15 bg-accent/40 px-5 py-4">
                <p className="text-label font-semibold uppercase tracking-wider text-accent-foreground">How HMS Workflows helps</p>
                <p className="mt-1 text-body leading-relaxed text-heading">{p.helps}</p>
              </div>
            </li>
          ))}
        </ul>
      </Section>

      {/* C. Solution: four pillars */}
      <Section labelledBy="pillars-title">
        <SectionIntro eyebrow="Our solution" id="pillars-title" title="Four connected parts of one platform.">
          HMS Workflows is not only a place to store records. It connects the information employees need with the work they must do — and keeps track of that work until it is done.
        </SectionIntro>
        <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4" data-testid="pillars">
          {PILLARS.map((p) => (
            <li key={p.id}>
              <Link to={p.to} className="group flex h-full flex-col rounded-xl border bg-card p-5 transition-colors hover:border-primary/40 hover:bg-accent/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
                <span className="grid size-10 place-items-center rounded-lg bg-primary text-primary-foreground"><p.icon className="size-5" aria-hidden /></span>
                <span className="mt-4 text-lg font-semibold text-heading">{p.title}</span>
                <span className="mt-1.5 text-body leading-relaxed text-muted-foreground">{p.text}</span>
                <CheckList items={p.includes} className="mt-4 flex-1 text-table" />
                <span className="mt-5 inline-flex items-center gap-1 text-table font-medium text-primary">Learn more<ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" /></span>
              </Link>
            </li>
          ))}
        </ul>
      </Section>

      {/* D. One patient journey */}
      <Section tone="subtle" labelledBy="journey-title">
        <SectionIntro eyebrow="One patient journey" id="journey-title" title="Follow a patient through the hospital.">
          Choose a pathway. At each step the next team works from the same record, and where something can stall, a monitor watches for it.
        </SectionIntro>
        <PathwayExplorer />
      </Section>

      {/* E. When something goes wrong */}
      <Section labelledBy="guardian-title">
        <div className="grid items-start gap-12 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
          <div>
            <SectionIntro eyebrow="When something goes wrong" id="guardian-title" title="An insurance problem, from detection to resolution.">
              A worked example using Insurance Guardian. It shows how a monitor, a case, an AI assistant and a person each play their part.
            </SectionIntro>
            <ol className="mt-8 space-y-0" data-testid="guardian-steps">
              {GUARDIAN_STEPS.map((s, i) => (
                <li key={s.title} className="relative flex gap-4 pb-6 last:pb-0">
                  {i < GUARDIAN_STEPS.length - 1 && <span className="absolute left-4 top-9 h-[calc(100%-2.25rem)] w-px bg-border" aria-hidden />}
                  <span className={cn("relative grid size-8 shrink-0 place-items-center rounded-full text-table font-semibold tabular",
                    s.who === "AI (optional)" ? "border-2 border-dashed border-ai/50 bg-ai-soft text-ai" : s.who === "Person" ? "bg-success text-white" : "bg-primary text-primary-foreground")} aria-hidden>{i + 1}</span>
                  <div className="min-w-0 pt-0.5">
                    <p className="flex flex-wrap items-center gap-2">
                      <span className="text-section font-semibold text-heading">{s.title}</span>
                      <span className={cn("rounded-full border px-2 py-0.5 text-label font-medium",
                        s.who === "AI (optional)" ? "border-ai/30 bg-ai-soft text-ai" : s.who === "Person" ? "border-success/30 bg-success-soft text-success" : "bg-muted text-muted-foreground")}>{s.who}</span>
                    </p>
                    <p className="mt-1 text-body leading-relaxed text-muted-foreground">{s.text}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
          <div className="lg:sticky lg:top-24">
            <ProductShot shot="insuranceGuardian" caption="Insurance Guardian: coverage of upcoming visits and open insurance cases. The payer connection is simulated." sizes="(min-width: 1024px) 45vw, 100vw" />
            <p className="mt-4 flex gap-2 rounded-lg border bg-subtle p-4 text-table leading-relaxed text-muted-foreground">
              <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>This is supported workflow coordination, not autonomous resolution. AI steps run only when an administrator has enabled an AI provider; otherwise the case, tasks and reminders continue without them. Payer eligibility checks are simulated.</span>
            </p>
          </div>
        </div>
      </Section>

      {/* F. Departments working together */}
      <Section tone="subtle" labelledBy="teams-title">
        <SectionIntro eyebrow="Departments working together" id="teams-title" title="A workspace for each team, connected to all the others." />
        <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="team-cards">
          {TEAMS.map((t) => (
            <li key={t.id}>
              <Link to={`/solutions#${t.id}`} className="group flex h-full flex-col rounded-xl border bg-card p-5 transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
                <p className="flex items-center gap-2.5 text-section font-semibold text-heading"><t.icon className="size-5 text-primary" aria-hidden />{t.title}</p>
                <p className="mt-2 text-body leading-relaxed text-muted-foreground">{t.short}</p>
                <p className="mt-3 flex-1 text-table leading-relaxed text-muted-foreground"><span className="font-medium text-heading">Hands off: </span>{t.handsOff}</p>
                <span className="mt-4 inline-flex items-center gap-1 text-table font-medium text-primary">How it helps<ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" /></span>
              </Link>
            </li>
          ))}
        </ul>
      </Section>

      {/* G. Why our approach matters */}
      <Section labelledBy="why-title">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)] lg:gap-14">
          <SectionIntro eyebrow="Why our approach matters" id="why-title" title="Built for coordination, not only record-keeping.">
            {PHILOSOPHY} Our aim is a hospital where the right information reaches the right team, pending work has a clear owner, and technology helps employees coordinate care.
          </SectionIntro>
          <ul className="grid gap-x-8 gap-y-7 sm:grid-cols-2">
            {WHY.map((w) => (
              <li key={w.title} className="flex gap-3">
                <w.icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
                <span><span className="block text-section font-semibold text-heading">{w.title}</span><span className="mt-1 block text-body leading-relaxed text-muted-foreground">{w.text}</span></span>
              </li>
            ))}
          </ul>
        </div>
      </Section>

      {/* H. Final CTA */}
      <FinalCta />
    </PublicLayout>
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
  const launched = ASSISTANTS.filter((a) => a.start === "Launched by staff");
  const embedded = ASSISTANTS.filter((a) => a.start === "Runs inside a workflow");
  return (
    <PublicLayout>
      <PageHero eyebrow="AI & Automation" title="Rules find the problem. AI helps with the work. People decide."
        text={`HMS Workflows uses ${MONITOR_COUNT} rule-based automation monitors, ${ASSISTANTS.length} specialized AI assistants, tracked cases and tasks, and human approvals. Each does a different job, and each is labelled so nobody mistakes a rule for AI or a draft for a decision.`}>
        <AnchorChips label="On this page" items={[{ id: "building-blocks", title: "Building blocks", icon: ClipboardCheck }, { id: "monitors", title: `${MONITOR_COUNT} monitors`, icon: Siren },
          { id: "assistants", title: `${ASSISTANTS.length} AI assistants`, icon: Bot }, { id: "responsible-ai", title: "Responsible AI", icon: ShieldAlert }]} />
      </PageHero>

      <Section id="building-blocks" labelledBy="blocks-title">
        <SectionIntro eyebrow="Building blocks" id="blocks-title" title="Five parts that work together." />
        <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-5" data-testid="building-blocks">
          {BLOCKS.map((b) => (
            <li key={b.id} className="flex flex-col rounded-xl border bg-card p-5">
              <b.icon className={cn("size-6", b.kind === "AI" ? "text-ai" : "text-primary")} aria-hidden />
              <p className="mt-3 text-section font-semibold text-heading">{b.title}</p>
              <p className="text-label font-medium text-muted-foreground">{b.kind}</p>
              <p className="mt-2 text-table leading-relaxed text-muted-foreground">{b.text}</p>
            </li>
          ))}
        </ul>
      </Section>

      <Section tone="brand" labelledBy="flow-title">
        <Eyebrow className="text-white/70">How a problem is handled</Eyebrow>
        <h2 id="flow-title" className="max-w-3xl text-3xl font-semibold tracking-tight text-balance text-white sm:text-4xl">From detection to a verified outcome.</h2>
        <p className="mt-4 max-w-3xl text-section leading-relaxed text-white/80 sm:text-lead">Dashed steps are optional. AI assistance runs only for selected case types, only when an administrator has enabled an AI provider, and within a daily limit. Without it, the case and its tasks continue normally.</p>
        <AutomationFlow dark className="mt-10" />
        <div className="mt-8 grid gap-4 text-body text-white/85 md:grid-cols-3">
          <p><strong className="text-white">Detection is rule-based.</strong> Monitors evaluate the current state of records on a schedule — they are not AI models.</p>
          <p><strong className="text-white">Execution waits for a person.</strong> AI never executes anything itself; the backend carries out an action only after approval.</p>
          <p><strong className="text-white">Resolution is checked.</strong> When the monitor no longer detects the condition, the case closes automatically.</p>
        </div>
      </Section>

      <Section id="monitors" labelledBy="monitors-title">
        <SectionIntro eyebrow="Automation monitors" id="monitors-title" title={`${MONITOR_COUNT} monitors watching for known problems.`}>
          Each monitor is a predefined, rule-based check with thresholds an administrator can adjust. When its condition is true, it opens one case for the owning team.
          Results appear in that team's <strong className="font-semibold text-heading">My work</strong> and on the <strong className="font-semibold text-heading">Command Center</strong>; administrators configure monitors under Automation.
        </SectionIntro>
        <p className="mt-5 flex flex-wrap items-center gap-2 text-table text-muted-foreground">
          <span className="inline-flex items-center gap-1 rounded-full border border-ai/30 bg-ai-soft px-2 py-0.5 text-label font-medium text-ai"><Sparkles className="size-3" aria-hidden />AI may assist</span>
          New cases from these monitors can receive optional AI assistance when AI is enabled.
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
      </Section>

      <Section id="assistants" tone="subtle" labelledBy="assistants-title">
        <SectionIntro eyebrow="AI assistants" id="assistants-title" title={`${ASSISTANTS.length} specialized assistants, each with a narrow job.`}>
          Assistants are not interchangeable and do not all run continuously. Each has its own permitted tools, the permission a user needs to use it, and a short list of actions it may propose.
        </SectionIntro>
        {([["Launched by staff", launched, "Staff open these from the Ask AI panel in their workspace or from Agent Studio. Some also assist automatically on selected new cases."],
          ["Runs inside a workflow", embedded, "These work only inside a specific screen, as part of that task."]] as const).map(([title, list, note]) => (
          <div key={title} className="mt-10">
            <h3 className="text-xl font-semibold tracking-tight text-heading">{title} <span className="font-normal text-muted-foreground">({list.length})</span></h3>
            <p className="mt-1 text-body text-muted-foreground">{note}</p>
            <ul className="mt-5 grid gap-4 md:grid-cols-2" data-testid={title === "Launched by staff" ? "assistants-launched" : "assistants-embedded"}>
              {list.map((a) => (
                <li key={a.key} className="flex flex-col rounded-xl border bg-card p-5" data-assistant={a.key}>
                  <p className="flex items-center gap-2.5 text-section font-semibold text-heading"><span className="grid size-9 shrink-0 place-items-center rounded-lg bg-ai-soft"><a.icon className="size-5 text-ai" aria-hidden /></span>
                    <span className="min-w-0"><span className="block">{a.brand ?? a.name}</span>{a.brand && <span className="block text-label font-normal text-muted-foreground">{a.name}</span>}</span></p>
                  <p className="mt-3 text-body leading-relaxed text-foreground">{a.does}</p>
                  <dl className="mt-3 grid gap-1.5 text-table">
                    <div className="grid gap-x-3 sm:grid-cols-[7.5rem_1fr]"><dt className="font-medium text-heading">Where</dt><dd className="text-muted-foreground">{a.where}</dd></div>
                    <div className="grid gap-x-3 sm:grid-cols-[7.5rem_1fr]"><dt className="font-medium text-heading">May propose</dt><dd className="text-muted-foreground">{a.proposes}</dd></div>
                    {a.auto && <div className="grid gap-x-3 sm:grid-cols-[7.5rem_1fr]"><dt className="font-medium text-heading">Also assists on</dt><dd className="text-muted-foreground">{a.auto}</dd></div>}
                  </dl>
                  <p className="mt-3 border-t pt-3 text-table text-muted-foreground"><ShieldAlert className="mr-1.5 inline size-3.5 -translate-y-px text-warning" aria-hidden />{a.never}</p>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <p className="mt-8 text-table text-muted-foreground">A separate realtime voice receptionist is available for practising administrative calls. It has no tools: it cannot look up or change hospital records or book real appointments.</p>
      </Section>

      <Section id="responsible-ai" labelledBy="responsible-title">
        <div className="grid items-start gap-12 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
          <div>
            <SectionIntro eyebrow="Responsible AI" id="responsible-title" title="Controls built into how AI is used." />
            <ul className="mt-8 grid gap-6 sm:grid-cols-2">
              {RESPONSIBLE.map((r) => (
                <li key={r.title} className="flex gap-3">
                  <r.icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
                  <span><span className="block text-section font-semibold text-heading">{r.title}</span><span className="mt-1 block text-body leading-relaxed text-muted-foreground">{r.text}</span></span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <ProductShot shot="agentStudio" caption="Agent Studio: what each assistant reads, what it may propose for approval, and its limits. Synthetic data." sizes="(min-width: 1024px) 45vw, 100vw" />
            <h3 className="mt-8 text-section font-semibold text-heading">Every result says where it came from</h3>
            <ul className="mt-3 space-y-2.5">
              {([["live", "A live AI provider produced this; the model is named."], ["simulated", "No AI provider was used; a rule-based summary instead."],
                ["draft", "AI-generated text a person has not yet reviewed."], ["rule", "Found by a rule-based monitor, not by AI."],
                ["pending", "A proposal waiting for a person with permission."], ["completed", "Approved by a named person and carried out."]] as const).map(([k, d]) => (
                <li key={k} className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-4"><ProvenanceChip kind={k} className="w-fit sm:w-48 sm:justify-center" /><span className="text-table text-muted-foreground">{d}</span></li>
              ))}
            </ul>
          </div>
        </div>
        <p className="mt-12 rounded-xl border border-dashed bg-subtle p-5 text-body leading-relaxed text-muted-foreground">
          <strong className="font-semibold text-heading">What we do not claim.</strong> HMS Workflows is not certified for clinical use and is not represented as HIPAA-compliant.
          AI output is assistance that requires human review. Live-provider verification is still in progress for several AI features — see the <Link to="/about#status" className="font-medium text-primary hover:underline">development status</Link>.
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
