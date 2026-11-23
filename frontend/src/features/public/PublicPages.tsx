import { ArrowRight, Check, Info, KeyRound, Lock, LogIn, ScrollText, ShieldAlert, UsersRound } from "lucide-react";
import { Link } from "react-router-dom";
import { ProvenanceChip } from "@/components/common/Status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDemoAccounts, useDemoLogin } from "@/features/auth/demo";
import { LoginForm } from "@/features/auth/LoginForm";
import { CODE_SET_NOTICES, COPYRIGHT_NOTICE, THIRD_PARTY } from "@/lib/legal";
import { cn } from "@/lib/utils";
import {
  AI_TIERS, APPROACH, AREAS, AUDIENCES, DEFINITION, DEMO_ROLE_INFO, JOURNEY, PRINCIPLES, PROBLEMS, PRODUCT_STATUS, SHOTS,
  type ShotKey, TAG_LABEL,
} from "./content";
import { PublicLayout } from "./PublicLayout";

const VERSION = import.meta.env.VITE_APP_VERSION ?? "development";

// ---------------------------------------------------------------------------------------------- building blocks

function Section({ id, tone = "plain", className, children, labelledBy }: { id?: string; tone?: "plain" | "subtle"; className?: string; children: React.ReactNode; labelledBy?: string }) {
  return (
    <section id={id} aria-labelledby={labelledBy} className={cn("scroll-mt-20 px-4 py-14 sm:px-6 lg:py-20", tone === "subtle" ? "border-y bg-subtle" : "bg-card", className)}>
      <div className="mx-auto max-w-6xl">{children}</div>
    </section>
  );
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="mb-3 text-label font-semibold uppercase tracking-wider text-primary">{children}</p>;
}

function H2({ id, children, className }: { id?: string; children: React.ReactNode; className?: string }) {
  return <h2 id={id} className={cn("text-3xl font-semibold tracking-tight text-balance text-heading sm:text-4xl", className)}>{children}</h2>;
}

function Lead({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn("mt-4 max-w-2xl text-section leading-relaxed text-muted-foreground text-pretty sm:text-lead", className)}>{children}</p>;
}

/** A real screenshot of the application (synthetic data), WebP at 720/1440 widths. */
function ProductShot({ shot, className, priority, caption = true, sizes = "(min-width: 1024px) 60vw, 100vw", crop }: {
  shot: ShotKey; className?: string; priority?: boolean; caption?: boolean | string; sizes?: string; crop?: string;
}) {
  const s = SHOTS[shot];
  return (
    <figure className={cn("overflow-hidden rounded-xl border bg-card shadow-[0_8px_30px_rgba(16,24,40,0.08)]", className)}>
      <img src={`/images/product/${s.src}.webp`} srcSet={`/images/product/${s.src}-720.webp 720w, /images/product/${s.src}.webp 1440w`} sizes={sizes}
        width={s.w} height={s.h} alt={s.alt} loading={priority ? "eager" : "lazy"} decoding="async" fetchPriority={priority ? "high" : undefined}
        className={cn("block h-auto w-full", crop && "object-cover", crop)} />
      {caption && <figcaption className="border-t bg-subtle px-4 py-2 text-label text-muted-foreground">{typeof caption === "string" ? caption : "Screenshot of HMS Workflows with synthetic demonstration data."}</figcaption>}
    </figure>
  );
}

function PageHero({ eyebrow, title, text, children }: { eyebrow: string; title: string; text: string; children?: React.ReactNode }) {
  return (
    <section className="border-b bg-card px-4 pb-14 pt-14 sm:px-6 lg:pb-20 lg:pt-20">
      <div className="mx-auto max-w-6xl">
        <Eyebrow>{eyebrow}</Eyebrow>
        <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-balance text-heading sm:text-5xl">{title}</h1>
        <Lead>{text}</Lead>
        {children}
      </div>
    </section>
  );
}

function StatusList({ id }: { id?: string }) {
  return (
    <ul id={id} className="divide-y rounded-xl border bg-card">
      {PRODUCT_STATUS.map((s) => (
        <li key={s.label} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-start sm:gap-5">
          <Badge variant={s.tone} className="w-fit shrink-0 sm:w-36 sm:justify-center">{s.label}</Badge>
          <p className="text-body leading-relaxed text-muted-foreground">{s.text}</p>
        </li>
      ))}
    </ul>
  );
}

/** One-click demo sign-in button (uses the shared demo-login flow; falls back to /login where demo mode is off). */
function DemoButton({ demoKey, label, variant = "default", className }: { demoKey: string; label: string; variant?: "default" | "outline"; className?: string }) {
  const { accounts } = useDemoAccounts();
  const { signIn, busy } = useDemoLogin();
  const available = accounts?.some((a) => a.key === demoKey);
  if (!available) return <Button asChild variant="outline" className={className}><Link to="/login"><LogIn />Sign in</Link></Button>;
  return <Button variant={variant} className={className} onClick={() => signIn(demoKey)} loading={busy === demoKey}>Try as {label}<ArrowRight /></Button>;
}

// ---------------------------------------------------------------------------------------------- Home

export function HomePage() {
  return (
    <PublicLayout>
      {/* 1. Hero — product first. */}
      <section className="overflow-hidden border-b bg-card px-4 pb-16 pt-12 sm:px-6 lg:pb-24 lg:pt-20" aria-labelledby="home-title">
        <div className="mx-auto grid max-w-7xl items-center gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-14">
          <div>
            <Eyebrow>Hospital management platform</Eyebrow>
            <h1 id="home-title" className="text-4xl font-semibold tracking-tight text-balance text-heading sm:text-5xl lg:text-6xl">
              Your Entire Hospital. <span className="text-primary">Working as One.</span>
            </h1>
            <p className="mt-6 text-lead leading-relaxed text-foreground text-pretty">
              One connected platform for patient care, hospital operations and coordinated workflows. HMS Workflows brings clinical teams, departments and administrators together around a shared patient record.
            </p>
            <p className="mt-3 text-body leading-relaxed text-muted-foreground">For hospital leadership, clinical teams and the departments that keep patients moving.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg"><Link to="/#demo">Explore the Demo<ArrowRight /></Link></Button>
              <Button asChild size="lg" variant="outline"><Link to="/platform">Explore the Platform</Link></Button>
            </div>
            <p className="mt-4 text-table text-muted-foreground">Seven one-click demo roles · synthetic data only · no account needed</p>
          </div>
          <ProductShot shot="commandCenter" priority caption="The Command Center, with synthetic demonstration data." sizes="(min-width: 1024px) 58vw, 100vw" />
        </div>
      </section>

      {/* 2. The problem → how HMS Workflows addresses it. */}
      <Section tone="subtle" labelledBy="problem-title">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-14">
          <div>
            <Eyebrow>The problem</Eyebrow>
            <H2 id="problem-title">Hospital work crosses departments. Most hospital software doesn't.</H2>
            <Lead>A single stay involves registration, doctors, nurses, the laboratory, pharmacy, bed management and billing. When each works in its own system, coordination falls back on people.</Lead>
          </div>
          <ol className="divide-y rounded-xl border bg-card">
            {PROBLEMS.map((p, i) => (
              <li key={p.title} className="flex gap-4 p-5">
                <span className="grid size-7 shrink-0 place-items-center rounded-full bg-muted text-table font-semibold tabular text-muted-foreground" aria-hidden>{i + 1}</span>
                <span><span className="block text-section font-semibold text-heading">{p.title}</span><span className="mt-1 block text-body leading-relaxed text-muted-foreground">{p.text}</span></span>
              </li>
            ))}
          </ol>
        </div>
        <div className="mt-16">
          <h3 className="text-2xl font-semibold tracking-tight text-heading">How HMS Workflows addresses it</h3>
          <ul className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {APPROACH.map((a, i) => (
              <li key={a.title} className="flex flex-col rounded-xl border bg-card">
                <div className="p-5">
                  <p className="flex items-center gap-2 text-label font-semibold text-primary"><a.icon className="size-4" aria-hidden />Step {i + 1}</p>
                  <p className="mt-1.5 text-section font-semibold text-heading">{a.title}</p>
                  <p className="mt-1.5 text-body leading-relaxed text-muted-foreground">{a.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </Section>

      {/* 3. How the hospital connects — the five capability areas on one shared foundation. */}
      <Section labelledBy="areas-title">
        <div className="max-w-3xl">
          <Eyebrow>The platform</Eyebrow>
          <H2 id="areas-title">Five capability areas. One shared foundation.</H2>
          <Lead>Each area serves its own teams, and all of them read and write the same patient record and the same list of owned work.</Lead>
        </div>
        <div className="mt-10">
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {AREAS.map((a) => (
              <li key={a.id}>
                <Link to={`/platform#${a.id}`} className="group flex h-full flex-col rounded-xl border bg-card p-5 transition-colors hover:border-primary/40 hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
                  <a.icon className="size-5 text-primary" aria-hidden />
                  <span className="mt-3 text-section font-semibold text-heading">{a.title}</span>
                  <span className="mt-1.5 flex-1 text-table leading-relaxed text-muted-foreground">{a.short}</span>
                  <span className="mt-3 inline-flex items-center gap-1 text-table font-medium text-primary">Details<ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" /></span>
                </Link>
              </li>
            ))}
          </ul>
          <div className="mt-4 rounded-xl border border-primary/25 bg-accent/50 p-5" aria-label="Shared foundation">
            <p className="text-label font-semibold uppercase tracking-wider text-accent-foreground">Shared by every area</p>
            <ul className="mt-2 grid gap-x-6 gap-y-1.5 text-body text-heading sm:grid-cols-2 lg:grid-cols-4">
              {["One patient record and timeline", "Cases and tasks with owners and deadlines", "Role-based permissions, enforced on the server", "An audit log of user actions"].map((t) => (
                <li key={t} className="flex items-start gap-2"><Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />{t}</li>
              ))}
            </ul>
          </div>
        </div>
      </Section>

      {/* 4. Patient journey. */}
      <Section tone="subtle" labelledBy="journey-title">
        <div className="max-w-3xl">
          <Eyebrow>Patient journey</Eyebrow>
          <H2 id="journey-title">Follow one patient through the hospital.</H2>
          <Lead>At each stage the next team sees what it needs on the same record, and anything left undone becomes someone's task.</Lead>
        </div>
        <ul className="mt-6 flex flex-wrap gap-2" aria-label="Legend">
          {Object.entries(TAG_LABEL).map(([k, v]) => <li key={k}><JourneyTag tag={k as keyof typeof TAG_LABEL} label={v} /></li>)}
        </ul>
        <ol className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-4" data-testid="journey">
          {JOURNEY.map((s, i) => (
            <li key={s.title} className="flex flex-col rounded-xl border bg-card p-5">
              <div className="flex items-center gap-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary text-table font-semibold tabular text-primary-foreground" aria-hidden>{i + 1}</span>
                <h3 className="flex items-center gap-2 text-section font-semibold text-heading"><s.icon className="size-4 text-muted-foreground" aria-hidden />{s.title}</h3>
              </div>
              <p className="mt-3 text-body leading-relaxed text-foreground">{s.happens}</p>
              <p className="mt-2 flex-1 text-table leading-relaxed text-muted-foreground"><span className="font-medium text-heading">Then: </span>{s.next}</p>
              <ul className="mt-4 flex flex-wrap gap-1.5">{s.tags.map((t) => <li key={t}><JourneyTag tag={t} label={TAG_LABEL[t]} /></li>)}</ul>
            </li>
          ))}
        </ol>
      </Section>

      {/* 5. Command Center showcase. */}
      <Section labelledBy="command-title">
        <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] lg:gap-12">
          <div>
            <Eyebrow>Hospital Command Center</Eyebrow>
            <H2 id="command-title">See where the hospital is waiting.</H2>
            <Lead>Administrators see capacity, emergency pressure, discharges, staffing and unresolved work in one place.</Lead>
            <ol className="mt-8 space-y-5">
              {[["Hospital status", "Occupancy, available beds, emergency activity, patients waiting for a bed, discharges and staffing gaps."],
                ["Problems requiring attention", "Open problems grouped by area, clinical risk first, each with an owner and how overdue it is."],
                ["Department details", "Capacity by unit, department queues and automation health."]].map(([t, d], i) => (
                <li key={t} className="flex gap-4">
                  <span className="grid size-8 shrink-0 place-items-center rounded-full border-2 border-primary text-table font-semibold text-primary" aria-hidden>{i + 1}</span>
                  <span><span className="block text-section font-semibold text-heading">{t}</span><span className="mt-1 block text-body leading-relaxed text-muted-foreground">{d}</span></span>
                </li>
              ))}
            </ol>
            <p className="mt-6 flex gap-2 rounded-lg border bg-subtle p-4 text-table leading-relaxed text-muted-foreground"><Info className="mt-0.5 size-4 shrink-0" aria-hidden />Figures are calculated from the application's own records, and every number opens the cases or patients behind it.</p>
          </div>
          <ProductShot shot="commandCenter" sizes="(min-width: 1024px) 66vw, 100vw" crop="object-[center_58%] aspect-[16/11]"
            caption="Problems requiring attention, grouped by area with owners and overdue times. Synthetic demonstration data." />
        </div>
      </Section>

      {/* 6. Automation and AI, explained. */}
      <Section tone="subtle" labelledBy="ai-title">
        <div className="max-w-3xl">
          <Eyebrow>AI & automation</Eyebrow>
          <H2 id="ai-title">Automation finds the problem. AI helps with the work. People decide.</H2>
          <Lead>HMS Workflows uses deterministic rules and AI for different jobs, and keeps people responsible for consequential actions.</Lead>
        </div>
        <div className="mt-10 overflow-hidden rounded-xl border bg-card">
          <div className="hidden grid-cols-[minmax(0,1.1fr)_minmax(0,1.6fr)_minmax(0,1.5fr)] gap-6 border-b bg-subtle px-5 py-3 text-label font-semibold text-muted-foreground md:grid">
            <span>Kind</span><span>What it does</span><span>Who stays in control</span>
          </div>
          <ul className="divide-y">
            {AI_TIERS.map((t) => (
              <li key={t.id} className="grid gap-2 px-5 py-5 md:grid-cols-[minmax(0,1.1fr)_minmax(0,1.6fr)_minmax(0,1.5fr)] md:gap-6">
                <div className="flex items-start gap-3"><t.icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
                  <div><p className="text-section font-semibold text-heading">{t.title}</p><p className="text-label text-muted-foreground">{t.kind}</p></div></div>
                <p className="text-body leading-relaxed text-foreground">{t.does} <span className="text-muted-foreground">Example: {t.examples[0]}.</span></p>
                <p className="text-body leading-relaxed text-muted-foreground">{t.control}</p>
              </li>
            ))}
          </ul>
        </div>
        <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-2xl text-table text-muted-foreground">AI features use a configured AI provider, such as OpenAI, when an administrator enables one, and otherwise run in a clearly labelled simulation. Every answer shows which.</p>
          <Button asChild variant="outline"><Link to="/ai-automation">How AI & automation work<ArrowRight /></Link></Button>
        </div>
      </Section>

      {/* 7. Explore the demo. */}
      <DemoSection />
    </PublicLayout>
  );
}

const TAG_STYLE: Record<string, string> = {
  record: "border-primary/25 bg-accent text-accent-foreground", task: "border-warning/35 bg-warning-soft text-warning-foreground",
  review: "border-success/30 bg-success-soft text-success", visibility: "border-border bg-muted text-muted-foreground",
};
function JourneyTag({ tag, label }: { tag: keyof typeof TAG_LABEL; label: string }) {
  return <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-label font-medium", TAG_STYLE[tag])}>{label}</span>;
}

function DemoSection() {
  const { accounts, isLoading } = useDemoAccounts();
  const { signIn, busy, error } = useDemoLogin();
  return (
    <Section id="demo" labelledBy="demo-title">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] lg:gap-12">
        <div>
          <Eyebrow>Explore the demo</Eyebrow>
          <H2 id="demo-title">Try HMS Workflows as a hospital role.</H2>
          <Lead>Choose a role and you are signed straight in to a demonstration hospital with synthetic patients.</Lead>
          <ul className="mt-6 space-y-2.5 text-body text-muted-foreground">
            {["Synthetic data only — no real patient information.", "Demo sessions can't change real settings, accounts or credentials.", "AI answers are labelled Simulated unless you add your own key in the demo's isolated AI settings."].map((t) => (
              <li key={t} className="flex gap-2"><Check className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />{t}</li>
            ))}
          </ul>
          <p className="mt-6 text-table text-muted-foreground">Not sure where to start? <strong className="font-semibold text-heading">Super Admin</strong> shows the whole hospital; <strong className="font-semibold text-heading">Doctor</strong> shows clinical care.</p>
        </div>
        <div>
          {error && <p role="alert" className="mb-3 rounded-lg border border-destructive/30 bg-destructive-soft p-3 text-body text-destructive">{error}</p>}
          {!accounts && !isLoading && (
            <div className="mb-4 rounded-lg border bg-subtle p-4 text-body text-muted-foreground">
              One-click demo access is enabled on the public demonstration site. Here, <Link to="/login" className="font-medium text-primary hover:underline">sign in</Link> with your account.
            </div>
          )}
          <ul className="grid gap-3 sm:grid-cols-2" data-testid="demo-roles">
            {(accounts ?? Object.keys(DEMO_ROLE_INFO).map((key) => ({ key, label: key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()), role: key }))).map((a) => {
              const info = DEMO_ROLE_INFO[a.key] ?? { sees: "Explore this role's workspace.", icon: UsersRound };
              return (
                <li key={a.key} className="flex flex-col rounded-xl border bg-card p-5">
                  <p className="flex items-center gap-2 text-section font-semibold text-heading"><info.icon className="size-5 text-primary" aria-hidden />{a.label}</p>
                  {info.start && <p className="mt-1 text-label font-medium text-primary">{info.start}</p>}
                  <p className="mt-2 flex-1 text-table leading-relaxed text-muted-foreground">{info.sees}</p>
                  <Button className="mt-4 w-full sm:w-auto sm:self-start" variant={info.start ? "default" : "outline"} disabled={!accounts || !!busy} loading={busy === a.key}
                    onClick={() => signIn(a.key)} aria-label={`Start the demo as ${a.label}`}>Start as {a.label}<ArrowRight /></Button>
                </li>
              );
            })}
          </ul>
          <p className="mt-4 text-table text-muted-foreground">Returning user? <Link to="/login" className="font-medium text-primary hover:underline">Sign in</Link></p>
        </div>
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------------------------- Platform

export function PlatformPage() {
  return (
    <PublicLayout>
      <PageHero eyebrow="Platform" title="One platform for clinical, operational and financial work." text={DEFINITION}>
        <nav aria-label="Capability areas" className="mt-8 flex flex-wrap gap-2">
          {AREAS.map((a) => (
            <Link key={a.id} to={`#${a.id}`} className="inline-flex items-center gap-2 rounded-full border bg-card px-3.5 py-2 text-table font-medium text-foreground hover:border-primary/40 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
              <a.icon className="size-4 text-primary" aria-hidden />{a.title}
            </Link>
          ))}
        </nav>
      </PageHero>
      {AREAS.map((a, i) => (
        <Section key={a.id} id={a.id} tone={i % 2 ? "subtle" : "plain"} labelledBy={`${a.id}-title`}>
          <div className={cn("grid items-start gap-10", a.shot && "lg:grid-cols-2 lg:gap-12")}>
            <div className={cn(a.shot && i % 2 && "lg:order-2")}>
              <p className="flex items-center gap-2 text-label font-semibold uppercase tracking-wider text-primary"><a.icon className="size-4" aria-hidden />Capability area {i + 1} of 5</p>
              <H2 id={`${a.id}-title`} className="mt-3">{a.title}</H2>
              <p className="mt-4 text-lead leading-relaxed text-foreground">{a.what}</p>
              <dl className="mt-6 grid gap-4 text-body">
                {[["Used by", a.teams], ["Connects with", a.connects], ["Why it matters", a.why]].map(([t, d]) => (
                  <div key={t} className="grid gap-1 sm:grid-cols-[9rem_1fr]"><dt className="font-semibold text-heading">{t}</dt><dd className="leading-relaxed text-muted-foreground">{d}</dd></div>
                ))}
              </dl>
              <ul className="mt-6 grid gap-2 text-body sm:grid-cols-2">
                {a.includes.map((c) => <li key={c} className="flex items-start gap-2"><Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />{c}</li>)}
              </ul>
              {a.status && <p className="mt-6 flex gap-2 rounded-lg border border-dashed bg-card p-4 text-table leading-relaxed text-muted-foreground"><Info className="mt-0.5 size-4 shrink-0" aria-hidden /><span><strong className="font-semibold text-heading">Integration status: </strong>{a.status}</span></p>}
            </div>
            {a.shot && <ProductShot shot={a.shot} className={cn(i % 2 && "lg:order-1")} sizes="(min-width: 1024px) 50vw, 100vw" />}
          </div>
        </Section>
      ))}
      <Section tone="subtle" labelledBy="admin-title">
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-12">
          <div>
            <Eyebrow>Administration & security</Eyebrow>
            <H2 id="admin-title">Secure by role, recorded by default.</H2>
            <ul className="mt-6 space-y-3 text-body">
              {[[UsersRound, "Facilities, departments and staff invitations with role-based access, enforced again on the server."],
                [ScrollText, "An audit log of user actions, including AI-related actions."],
                [KeyRound, "AI provider keys are stored encrypted on the server and never shown in the browser."],
                [Lock, "Sending patient information to an external AI provider is off unless an administrator enables it."]].map(([I, t]) => {
                const Icon = I as React.ElementType;
                return <li key={t as string} className="flex gap-3"><Icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden /><span className="leading-relaxed text-muted-foreground">{t as string}</span></li>;
              })}
            </ul>
          </div>
          <div>
            <h3 className="text-2xl font-semibold tracking-tight text-heading">Product status</h3>
            <p className="mt-2 text-body text-muted-foreground">What works today, what is simulated, and what still needs an external connection.</p>
            <div className="mt-5"><StatusList /></div>
          </div>
        </div>
      </Section>
    </PublicLayout>
  );
}

// ---------------------------------------------------------------------------------------------- Solutions

export function SolutionsPage() {
  return (
    <PublicLayout>
      <PageHero eyebrow="Solutions" title="A workspace for every team in the hospital." text="Each role lands on the screens and actions it needs, on the same shared record as everyone else.">
        <nav aria-label="Teams" className="mt-8 flex flex-wrap gap-2">
          {AUDIENCES.map((a) => (
            <Link key={a.id} to={`#${a.id}`} className="inline-flex items-center gap-2 rounded-full border bg-card px-3.5 py-2 text-table font-medium hover:border-primary/40 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
              <a.icon className="size-4 text-primary" aria-hidden />{a.title.replace(/^For /, "")}
            </Link>
          ))}
        </nav>
      </PageHero>
      {AUDIENCES.map((a, i) => (
        <Section key={a.id} id={a.id} tone={i % 2 ? "subtle" : "plain"} labelledBy={`${a.id}-title`}>
          <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-12">
            <div className={cn(i % 2 && "lg:order-2")}>
              <p className="flex items-center gap-2 text-label font-semibold uppercase tracking-wider text-primary"><a.icon className="size-4" aria-hidden />{a.title}</p>
              <H2 id={`${a.id}-title`} className="mt-3">{a.need}</H2>
              <ul className="mt-6 space-y-2.5 text-body">
                {a.points.map((p) => <li key={p} className="flex items-start gap-2"><Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />{p}</li>)}
              </ul>
              <div className="mt-8"><DemoButton demoKey={a.demo.key} label={a.demo.label} variant="outline" /></div>
            </div>
            <ProductShot shot={a.shot} className={cn(i % 2 && "lg:order-1")} sizes="(min-width: 1024px) 50vw, 100vw" />
          </div>
        </Section>
      ))}
    </PublicLayout>
  );
}

// ---------------------------------------------------------------------------------------------- AI & Automation

export function AiAutomationPage() {
  return (
    <PublicLayout>
      <PageHero eyebrow="AI & Automation" title="Automation finds the problem. AI helps with the work. People decide."
        text="HMS Workflows separates deterministic rules from AI-generated content, labels every AI answer as live or simulated, and keeps consequential actions with the people responsible for them." />
      <Section labelledBy="kinds-title">
        <H2 id="kinds-title">Five kinds of help, and who stays in control</H2>
        <div className="mt-10 space-y-5">
          {AI_TIERS.map((t, i) => (
            <article key={t.id} id={t.id} className="scroll-mt-20 grid gap-6 rounded-xl border bg-card p-6 lg:grid-cols-[minmax(0,4fr)_minmax(0,4fr)_minmax(0,4fr)] lg:gap-8">
              <div>
                <p className="text-label font-semibold uppercase tracking-wider text-muted-foreground">{i + 1} · {t.kind}</p>
                <h3 className="mt-2 flex items-center gap-2 text-2xl font-semibold tracking-tight text-heading"><t.icon className="size-5 text-primary" aria-hidden />{t.title}</h3>
                <p className="mt-3 text-body leading-relaxed text-foreground">{t.does}</p>
              </div>
              <div>
                <p className="text-label font-semibold text-muted-foreground">Examples in HMS Workflows</p>
                <ul className="mt-2 space-y-1.5 text-body">{t.examples.map((e) => <li key={e} className="flex items-start gap-2"><Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />{e}</li>)}</ul>
              </div>
              <div className="rounded-lg bg-subtle p-4">
                <p className="text-label font-semibold text-muted-foreground">Who stays in control</p>
                <p className="mt-2 text-body leading-relaxed text-foreground">{t.control}</p>
              </div>
            </article>
          ))}
        </div>
      </Section>
      <Section tone="subtle" labelledBy="labels-title">
        <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-12">
          <div>
            <H2 id="labels-title">Every result says where it came from</H2>
            <Lead>The same labels appear throughout the application, so nobody mistakes a rule for AI, a simulation for a live model, or a draft for a decision.</Lead>
            <ul className="mt-6 space-y-3">
              {([["live", "A real AI provider produced this answer; the model is named."], ["simulated", "No AI provider was used; a rule-based summary was produced instead."],
                ["draft", "AI-generated text that a person has not yet reviewed."], ["rule", "Found by a deterministic monitor, not by AI."],
                ["pending", "A proposal that waits for a person with permission."], ["completed", "Approved by a named person and carried out."]] as const).map(([k, d]) => (
                <li key={k} className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-4"><ProvenanceChip kind={k} className="w-fit sm:w-52 sm:justify-center" /><span className="text-body text-muted-foreground">{d}</span></li>
              ))}
            </ul>
          </div>
          <div>
            <ProductShot shot="agentStudio" caption="AI Agent Studio: what each assistant reads, what it may propose for approval, and its limits. Synthetic demonstration data." sizes="(min-width: 1024px) 50vw, 100vw" />
            <ul className="mt-6 space-y-3 text-body text-muted-foreground">
              <li className="flex gap-3"><KeyRound className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />Provider keys are encrypted on the server and never sent to the browser.</li>
              <li className="flex gap-3"><Lock className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />Sending patient information to an external AI provider is off unless an administrator enables it.</li>
              <li className="flex gap-3"><UsersRound className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />Public demo sessions get isolated AI settings with per-session request, concurrency and cost limits.</li>
            </ul>
          </div>
        </div>
      </Section>
      <Section labelledBy="status-title">
        <H2 id="status-title">Product status</H2>
        <Lead>What has been built and tested, what has been verified with a live AI provider, and what is simulated.</Lead>
        <div className="mt-8"><StatusList /></div>
      </Section>
    </PublicLayout>
  );
}

// ---------------------------------------------------------------------------------------------- About

export function PublicAboutPage() {
  return (
    <PublicLayout>
      <PageHero eyebrow="About" title="Why HMS Workflows exists" text="Hospital work crosses departments, but hospital software usually doesn't. HMS Workflows was built to show what a hospital looks like when every team works from one record and every problem has an owner." />
      <Section labelledBy="aim-title">
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-12">
          <div>
            <H2 id="aim-title">The problem we set out to solve</H2>
            <div className="mt-5 space-y-4 text-lead leading-relaxed text-muted-foreground">
              <p>A patient's stay touches registration, doctors, nurses, the laboratory, pharmacy, bed management and billing. When each keeps its own system, information is re-entered, hand-offs depend on phone calls, and leaders find bottlenecks after patients have already waited.</p>
              <p>HMS Workflows puts these teams on one platform: one shared patient record, problems turned into owned and tracked work, and one live view of the hospital.</p>
            </div>
          </div>
          <div>
            <h3 className="text-2xl font-semibold tracking-tight text-heading">Principles</h3>
            <ul className="mt-5 divide-y rounded-xl border bg-card">
              {PRINCIPLES.map(([t, d]) => (
                <li key={t} className="p-5"><p className="text-section font-semibold text-heading">{t}</p><p className="mt-1 text-body leading-relaxed text-muted-foreground">{d}</p></li>
              ))}
            </ul>
          </div>
        </div>
      </Section>
      <Section tone="subtle" labelledBy="oversight-title">
        <div className="max-w-3xl">
          <H2 id="oversight-title">Automation and AI, with people responsible</H2>
          <div className="mt-5 space-y-4 text-lead leading-relaxed text-muted-foreground">
            <p>Deterministic rules watch for problems — expiring stock, unconfirmed insurance, missing discharge steps — and assign them to the right team. AI drafts notes, summarizes charts and explains operational issues within the user's permissions.</p>
            <p><strong className="font-semibold text-heading">Clinicians and authorized staff remain responsible for consequential decisions.</strong> AI does not diagnose, prescribe, sign notes, change claims or message patients on its own. Anything an AI agent proposes waits for a person's approval, and every step is recorded.</p>
          </div>
          <Button asChild variant="outline" className="mt-6"><Link to="/ai-automation">How AI & automation work<ArrowRight /></Link></Button>
        </div>
      </Section>
      <Section id="status" labelledBy="status-title">
        <H2 id="status-title">Current status</H2>
        <Lead>HMS Workflows is a working demonstration platform, not a deployed hospital product.</Lead>
        <div className="mt-8"><StatusList /></div>
        <p className="mt-3 text-table text-muted-foreground">Version {VERSION}</p>
      </Section>
      <Section id="legal" tone="subtle" labelledBy="legal-title">
        <H2 id="legal-title">Copyright & legal</H2>
        <div className="mt-8 grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border bg-card p-5">
            <p className="text-section font-semibold text-heading" data-testid="about-copyright">{COPYRIGHT_NOTICE}</p>
            <p className="mt-1.5 text-body text-muted-foreground">This application's original source code, design and documentation are protected by copyright. No license is granted except as agreed in writing with the copyright holder.</p>
          </div>
          <div className="rounded-xl border bg-card p-5">
            <p className="flex items-center gap-2 text-body font-semibold text-heading"><ShieldAlert className="size-4 text-warning" aria-hidden />Use limitations</p>
            <p className="mt-1.5 text-body text-muted-foreground">Demonstration build for synthetic data only. It is not HIPAA-certified, not ONC-certified and not validated for clinical use. AI output is a draft that requires human review.</p>
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
            <p className="mt-6 text-body text-muted-foreground">New here? <Link to="/#demo" className="font-medium text-primary hover:underline">Explore the demo</Link> or read about the <Link to="/platform" className="font-medium text-primary hover:underline">platform</Link>.</p>
          </div>
          <div className="rounded-2xl border bg-card p-6 shadow-[0_8px_30px_rgba(16,24,40,0.08)] sm:p-8">
            <LoginForm autoFocus emailId="login-email" />
          </div>
        </div>
      </section>
    </PublicLayout>
  );
}
