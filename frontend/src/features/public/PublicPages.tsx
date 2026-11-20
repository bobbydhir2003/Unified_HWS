import { ArrowRight, ArrowUpRight, Bot, Check, Info, Network, Scale, ShieldAlert, Sparkles, UsersRound } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LoginForm } from "@/features/auth/LoginForm";
import { CODE_SET_NOTICES, COPYRIGHT_NOTICE, THIRD_PARTY } from "@/lib/legal";
import { cn } from "@/lib/utils";
import { ADMIN_SOLUTION, AI_FEATURES, COMMAND_ITEMS, DIFFERENTIATORS, JOURNEY_STAGES, MODULE_GROUPS, MODULES, SOLUTIONS } from "./content";
import { Ecosystem } from "./Ecosystem";
import { HospitalBackdrop, PublicLayout } from "./PublicLayout";

const VERSION = import.meta.env.VITE_APP_VERSION ?? "development";
const HERO_POINTS: [React.ElementType, string][] = [[Network, "Connected departments"], [Bot, "AI-assisted documentation"], [UsersRound, "Role-based workspaces"]];

function SectionHeading({ eyebrow, title, text, as: H = "h2", className }: { eyebrow?: string; title: React.ReactNode; text?: string; as?: "h1" | "h2"; className?: string }) {
  return (
    <div className={cn("mx-auto max-w-3xl text-center", className)}>
      {eyebrow && <p className="mb-2 text-[12.5px] font-semibold uppercase tracking-[0.14em] text-primary">{eyebrow}</p>}
      <H className={cn("font-semibold tracking-tight text-balance", H === "h1" ? "text-3xl sm:text-[42px] sm:leading-[1.12]" : "text-2xl sm:text-[32px] sm:leading-tight")}>{title}</H>
      {text && <p className="mt-3 text-[15.5px] leading-relaxed text-muted-foreground text-pretty">{text}</p>}
    </div>
  );
}

function PageHero({ eyebrow, title, text }: { eyebrow: string; title: string; text: string }) {
  return (
    <section className="relative isolate overflow-hidden border-b bg-gradient-to-b from-accent/60 to-background px-4 pb-14 pt-14 sm:px-6 sm:pt-20">
      <div className="pointer-events-none absolute -right-32 -top-32 -z-10 size-[28rem] rounded-full bg-primary/10 blur-3xl" aria-hidden />
      <SectionHeading as="h1" eyebrow={eyebrow} title={title} text={text} />
    </section>
  );
}

// ---------------------------------------------------------------------------------------------- Home

export function HomePage() {
  return (
    <PublicLayout overlay>
      {/* Hero: headline left, existing sign-in card right (mobile order: headline → sign-in → highlights). */}
      <section className="relative isolate px-4 pb-14 pt-28 sm:px-6 lg:pb-20 lg:pt-32" aria-labelledby="home-title">
        <HospitalBackdrop />
        <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[1.15fr_minmax(0,440px)] lg:gap-x-14 lg:gap-y-8">
          <div className="order-1 text-white lg:order-none lg:col-start-1 lg:row-start-1 lg:self-end">
            <p className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3.5 py-1.5 text-[12.5px] font-medium backdrop-blur">
              <Sparkles className="size-3.5 text-sky-300" />Undeclared HMS · AI-powered hospital management
            </p>
            <h1 id="home-title" className="mt-5 text-[38px] font-semibold leading-[1.06] tracking-tight text-balance sm:text-[52px] lg:text-[60px]">
              Your Entire Hospital. <span className="bg-gradient-to-r from-sky-300 to-blue-300 bg-clip-text text-transparent">Working as One.</span>
            </h1>
            <p className="mt-4 text-[18px] font-medium text-sky-100 sm:text-[20px]">From the first appointment to the final follow-up.</p>
            <p className="mt-4 max-w-xl text-[15.5px] leading-relaxed text-blue-50/85 sm:text-[16.5px]">
              Undeclared HMS connects patient records, clinical care, hospital departments, insurance, billing, and everyday operations in one intelligent workspace. With AI-assisted documentation and coordinated workflows, healthcare teams can manage the patient journey through a connected platform.
            </p>
          </div>
          <div className="order-3 text-white lg:order-none lg:col-start-1 lg:row-start-2">
            <ul className="flex flex-wrap gap-2">
              {HERO_POINTS.map(([Icon, label]) => (
                <li key={label} className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.07] px-3.5 py-2 text-[13px] font-medium backdrop-blur-sm">
                  <Icon className="size-4 text-sky-300" />{label}
                </li>
              ))}
            </ul>
            <div className="mt-7 flex flex-wrap gap-3">
              <Button asChild size="lg" className="h-11 bg-white text-[#0b2a66] hover:bg-blue-50"><Link to="/modules">Explore modules<ArrowRight /></Link></Button>
              <Button asChild size="lg" variant="ghost" className="h-11 text-white hover:bg-white/10 hover:text-white"><a href="#ecosystem">See how it connects</a></Button>
            </div>
          </div>
          <div id="sign-in" className="order-2 scroll-mt-24 self-center rounded-3xl border border-white/40 bg-card/95 p-6 text-card-foreground shadow-2xl shadow-blue-950/40 backdrop-blur sm:p-8 lg:order-none lg:col-start-2 lg:row-span-2 lg:row-start-1">
            <LoginForm emailId="home-email" />
          </div>
        </div>
      </section>

      {/* Connected ecosystem, on a navy band continuing the hero. */}
      <section id="ecosystem" className="relative isolate scroll-mt-16 overflow-hidden bg-gradient-to-b from-[#071a44] via-[#0a2358] to-[#0b2a66] px-4 py-16 sm:px-6 lg:py-20" aria-labelledby="ecosystem-title">
        <div className="pointer-events-none absolute left-1/2 top-1/2 -z-10 size-[44rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-sky-500/10 blur-3xl" aria-hidden />
        <div className="mx-auto max-w-3xl text-center text-white">
          <p className="mb-2 text-[12.5px] font-semibold uppercase tracking-[0.14em] text-sky-300">The Undeclared HMS ecosystem</p>
          <h2 id="ecosystem-title" className="text-2xl font-semibold tracking-tight sm:text-[34px] sm:leading-tight">Six connected systems. One platform.</h2>
          <p className="mt-3 text-[15.5px] leading-relaxed text-blue-100/80">Every department works on the same patient record, so information follows the patient wherever care happens. Select a system to see what it does.</p>
        </div>
        <div className="mt-10"><Ecosystem /></div>
      </section>

      {/* Patient journey. */}
      <section className="px-4 py-16 sm:px-6 sm:py-20" aria-labelledby="journey-title">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Patient journey" title={<span id="journey-title">From Arrival to Follow-Up. All Connected.</span>}
            text="Each stage hands information to the next, so nothing has to be re-entered or chased by phone." />
          <ol className="relative mt-12 grid gap-0 lg:grid-cols-7 lg:gap-3" data-testid="journey">
            <span className="absolute left-[19px] top-2 bottom-2 w-px bg-gradient-to-b from-primary/50 via-primary/30 to-primary/10 lg:hidden" aria-hidden />
            <span className="absolute left-[7%] right-[7%] top-[22px] hidden h-px bg-gradient-to-r from-primary/20 via-primary/50 to-primary/20 lg:block" aria-hidden />
            {JOURNEY_STAGES.map((st, i) => (
              <li key={st.id} className="relative flex gap-4 pb-6 lg:flex-col lg:items-center lg:gap-3 lg:pb-0 lg:text-center">
                <span className="relative z-10 grid size-10 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground shadow-md shadow-primary/30 ring-4 ring-background lg:size-11"><st.icon className="size-[18px]" /></span>
                <Link to={st.to} className="group block flex-1 rounded-2xl border bg-card p-4 shadow-sm transition-all hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 lg:h-full motion-safe:hover:-translate-y-0.5">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-primary">Step {i + 1}</span>
                  <span className="mt-0.5 block text-[14.5px] font-semibold leading-snug">{st.title}</span>
                  <span className="mt-1.5 block text-[13px] leading-relaxed text-muted-foreground">{st.text}</span>
                  <span className="mt-3 inline-flex items-center gap-1 rounded-full bg-accent px-2.5 py-1 text-[11.5px] font-medium text-accent-foreground">{st.module}<ArrowUpRight className="size-3" /></span>
                </Link>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Undeclared AI. */}
      <section className="relative isolate overflow-hidden bg-[#071a44] px-4 py-16 text-white sm:px-6 sm:py-20" aria-labelledby="ai-title">
        <div className="pointer-events-none absolute -right-40 -top-40 -z-10 size-[36rem] rounded-full bg-blue-500/15 blur-3xl" aria-hidden />
        <div className="mx-auto max-w-7xl">
          <div className="mx-auto max-w-3xl text-center">
            <p className="mb-2 text-[12.5px] font-semibold uppercase tracking-[0.14em] text-sky-300">Undeclared AI</p>
            <h2 id="ai-title" className="text-2xl font-semibold tracking-tight sm:text-[34px] sm:leading-tight">Meet Undeclared AI</h2>
            <p className="mt-3 text-[15.5px] leading-relaxed text-blue-100/80">Practical AI assistance built into everyday healthcare workflows.</p>
          </div>
          <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="ai-features">
            {AI_FEATURES.map((f) => (
              <li key={f.title} className="rounded-2xl border border-white/12 bg-white/[0.05] p-5 backdrop-blur-sm transition-colors hover:border-sky-300/40">
                <span className="grid size-10 place-items-center rounded-xl bg-gradient-to-br from-sky-400 to-blue-600"><f.icon className="size-5" /></span>
                <h3 className="mt-4 text-[16px] font-semibold">{f.title}</h3>
                <p className="mt-1.5 text-[13.5px] leading-relaxed text-blue-100/75">{f.text}</p>
                <p className="mt-4 inline-flex items-center gap-1.5 rounded-full border border-sky-300/25 bg-sky-300/10 px-2.5 py-1 text-[11.5px] font-medium text-sky-100"><Info className="size-3" />{f.status}</p>
              </li>
            ))}
          </ul>
          <p className="mx-auto mt-8 max-w-3xl text-center text-[13px] leading-relaxed text-blue-100/70">AI assists staff; it doesn't make clinical decisions. Features that use an external AI provider run in a clearly labeled simulation mode until an administrator configures one.</p>
        </div>
      </section>

      {/* Command Center. */}
      <section className="px-4 py-16 sm:px-6 sm:py-20" aria-labelledby="command-title">
        <div className="mx-auto grid max-w-7xl items-center gap-10 lg:grid-cols-[minmax(0,380px)_1fr]">
          <div>
            <p className="mb-2 text-[12.5px] font-semibold uppercase tracking-[0.14em] text-primary">Hospital Command Center</p>
            <h2 id="command-title" className="text-2xl font-semibold tracking-tight text-balance sm:text-[34px] sm:leading-tight">See the Whole Hospital. In One Workspace.</h2>
            <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">Live operational status for administrators and department leads. Every number shows its source and opens the cases or patients behind it.</p>
            <ul className="mt-6 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-1">
              {COMMAND_ITEMS.map((c) => <li key={c.label} className="flex items-center gap-2.5 text-[14px]"><span className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><c.icon className="size-4" /></span>{c.label}</li>)}
            </ul>
            <Button asChild variant="outline" className="mt-7"><Link to="/modules#command">Command Center details<ArrowRight /></Link></Button>
          </div>
          <figure className="overflow-hidden rounded-2xl border bg-card shadow-2xl shadow-blue-950/15 ring-1 ring-black/5">
            <div className="flex items-center gap-1.5 border-b bg-muted/60 px-4 py-2.5" aria-hidden>
              <span className="size-2.5 rounded-full bg-red-400/80" /><span className="size-2.5 rounded-full bg-amber-400/80" /><span className="size-2.5 rounded-full bg-emerald-400/80" />
            </div>
            <picture>
              <source media="(max-width: 767px)" srcSet="/images/command-center-800.webp" type="image/webp" />
              <img src="/images/command-center.webp" width={1600} height={868} loading="lazy" decoding="async" className="block h-auto w-full"
                alt="Undeclared HMS Command Center showing inpatient census, available beds, emergency department, discharges, pharmacy alerts, claims and occupancy by department" />
            </picture>
            <figcaption className="border-t px-4 py-2.5 text-[12px] text-muted-foreground">Screenshot of the Command Center in the synthetic-data demonstration environment.</figcaption>
          </figure>
        </div>
      </section>

      <section className="border-t bg-muted/40 px-4 py-12 sm:px-6" aria-label="Explore further">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-5 text-center sm:flex-row sm:text-left">
          <div>
            <h2 className="text-xl font-semibold tracking-tight">Explore every module and role</h2>
            <p className="mt-1 text-[14.5px] text-muted-foreground">See what each department can do in Undeclared HMS, and how each role works.</p>
          </div>
          <div className="flex flex-wrap justify-center gap-3">
            <Button asChild><Link to="/modules">View modules<ArrowRight /></Link></Button>
            <Button asChild variant="outline"><Link to="/solutions">Solutions by role</Link></Button>
          </div>
        </div>
      </section>
    </PublicLayout>
  );
}

// ---------------------------------------------------------------------------------------------- Modules

export function ModulesPage() {
  const byId = (id: string) => MODULES.find((m) => m.id === id)!;
  return (
    <PublicLayout>
      <PageHero eyebrow="Modules" title="Everything Your Hospital Needs, Connected." text="Explore the systems that bring clinical care, administration, and hospital operations into one workspace." />
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[230px_1fr]">
        <nav aria-label="Modules on this page" className="hidden lg:block">
          <ul className="sticky top-24 space-y-4 text-[13.5px]">
            {MODULE_GROUPS.map((g) => (
              <li key={g.id}>
                <a href={`#${g.id}`} className="block px-2.5 text-[12px] font-semibold uppercase tracking-wider text-foreground/80 hover:text-primary">{g.title}</a>
                <ul className="mt-1 space-y-0.5">
                  {g.modules.map((id) => { const m = byId(id); return <li key={id}><a href={`#${id}`} className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"><m.icon className="size-4" />{m.title}</a></li>; })}
                </ul>
              </li>
            ))}
          </ul>
        </nav>
        <div className="space-y-12">
          {MODULE_GROUPS.map((g) => (
            <section key={g.id} id={g.id} aria-labelledby={`${g.id}-title`} className="scroll-mt-24">
              <div className="mb-4">
                <h2 id={`${g.id}-title`} className="text-2xl font-semibold tracking-tight">{g.title}</h2>
                <p className="mt-1 text-[15px] text-muted-foreground">{g.intro}</p>
              </div>
              <div className="space-y-4">
                {g.modules.map((id) => {
                  const m = byId(id);
                  return (
                    <article key={m.id} id={m.id} aria-labelledby={`${m.id}-title`} className="scroll-mt-24 rounded-3xl border bg-card p-6 shadow-sm sm:p-8">
                      <div className="flex items-start gap-4">
                        <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-primary/10 text-primary"><m.icon className="size-6" /></span>
                        <div className="min-w-0">
                          <h3 id={`${m.id}-title`} className="text-xl font-semibold tracking-tight">{m.title}</h3>
                          <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{m.description}</p>
                        </div>
                      </div>
                      <ul className="mt-5 grid gap-2 sm:grid-cols-2">
                        {m.capabilities.map((c) => <li key={c} className="flex items-start gap-2 text-[14px]"><Check className="mt-0.5 size-4 shrink-0 text-primary" />{c}</li>)}
                      </ul>
                      {m.note && <p className="mt-4 flex items-start gap-2 rounded-xl bg-warning-soft/60 px-3 py-2 text-[13px]"><Info className="mt-0.5 size-4 shrink-0" />{m.note}</p>}
                    </article>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      </div>
    </PublicLayout>
  );
}

// ---------------------------------------------------------------------------------------------- Solutions

export function SolutionsPage() {
  const title = (id: string) => MODULES.find((m) => m.id === id)?.title ?? id;
  return (
    <PublicLayout>
      <PageHero eyebrow="Solutions" title="Designed Around the People Who Run Healthcare." text="Each role gets a workspace focused on its own work, connected to everyone else's." />
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6">
        <ul className="grid gap-4 md:grid-cols-2">
          {SOLUTIONS.map((s) => (
            <li key={s.id} id={s.id} className="scroll-mt-24 rounded-3xl border bg-card p-6 shadow-sm">
              <div className="flex items-center gap-3">
                <span className="grid size-11 place-items-center rounded-2xl bg-primary/10 text-primary"><s.icon className="size-5" /></span>
                <h2 className="text-lg font-semibold tracking-tight">{s.title}</h2>
              </div>
              <p className="mt-3 text-[14.5px] leading-relaxed text-muted-foreground">{s.intro}</p>
              <ul className="mt-4 space-y-2">
                {s.points.map((p) => <li key={p} className="flex items-start gap-2 text-[14px]"><Check className="mt-0.5 size-4 shrink-0 text-primary" />{p}</li>)}
              </ul>
              <div className="mt-5 flex flex-wrap gap-2">
                {s.modules.map((id) => <Link key={id} to={`/modules#${id}`} className="rounded-full border px-3 py-1 text-[12.5px] font-medium text-muted-foreground hover:border-primary/40 hover:text-foreground">{title(id)}</Link>)}
              </div>
            </li>
          ))}
        </ul>
        <section className="mt-6 rounded-3xl border bg-gradient-to-br from-[#0b2a66] to-[#123a8a] p-6 text-white shadow-lg sm:p-8" aria-labelledby="admin-title">
          <div className="flex items-center gap-3">
            <span className="grid size-11 place-items-center rounded-2xl bg-white/15"><ADMIN_SOLUTION.icon className="size-5" /></span>
            <h2 id="admin-title" className="text-lg font-semibold tracking-tight">{ADMIN_SOLUTION.title}</h2>
          </div>
          <ul className="mt-4 grid gap-2 md:grid-cols-2">
            {ADMIN_SOLUTION.points.map((p) => <li key={p} className="flex items-start gap-2 text-[14px] text-blue-50/90"><Check className="mt-0.5 size-4 shrink-0 text-sky-300" />{p}</li>)}
          </ul>
        </section>
      </div>
    </PublicLayout>
  );
}

// ---------------------------------------------------------------------------------------------- About (+ legal)

const STATUS: { label: string; tone: "success" | "info" | "warning" | "danger"; text: string }[] = [
  { label: "Implemented", tone: "success", text: "The application features described on this site: clinical records, scheduling, emergency and inpatient care, pharmacy, laboratory, radiology, insurance and billing, the Command Center, the patient portal and AI Agent Studio." },
  { label: "Synthetic data", tone: "info", text: "Demonstrations use made-up patients and records only." },
  { label: "Simulated", tone: "warning", text: "Connections to payers, clearinghouses, pharmacy suppliers, imaging archives (PACS), email and text messaging, and card payments are simulated and labeled in the app." },
  { label: "Live integrations", tone: "info", text: "No external integration has been verified live yet. Everything that connects outside the platform is either simulated or waiting for credentials." },
  { label: "Requires credentials", tone: "warning", text: "External AI (text and realtime voice) works only after an administrator configures a provider key; otherwise AI features run in a labeled simulation mode." },
  { label: "Not certified", tone: "danger", text: "Undeclared HMS has not been certified for clinical use and is not represented as HIPAA-compliant." },
];

export function PublicAboutPage() {
  return (
    <PublicLayout>
      <PageHero eyebrow="About" title="About Undeclared HMS" text="Undeclared HMS brings clinical care, hospital operations, and intelligent automation together in one connected platform." />
      <div className="mx-auto max-w-5xl space-y-12 px-4 py-12 sm:px-6">
        <section aria-labelledby="vision" className="rounded-3xl border bg-card p-6 text-center shadow-sm sm:p-10">
          <h2 id="vision" className="text-xl font-semibold tracking-tight">Our Vision</h2>
          <p className="mx-auto mt-3 max-w-2xl text-[17px] leading-relaxed text-muted-foreground">To make complex hospital workflows easier to coordinate through connected information, practical automation, and software designed around the people delivering care.</p>
        </section>

        <section aria-labelledby="different">
          <h2 id="different" className="text-2xl font-semibold tracking-tight">What Makes Undeclared Different</h2>
          <ul className="mt-5 grid gap-3 sm:grid-cols-2">
            {DIFFERENTIATORS.map(([t, d]) => (
              <li key={t} className="rounded-2xl border bg-card p-5 shadow-sm">
                <p className="flex items-center gap-2 text-[15px] font-semibold"><Check className="size-4 text-primary" />{t}</p>
                <p className="mt-1.5 text-[14px] leading-relaxed text-muted-foreground">{d}</p>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="ai" className="rounded-3xl border border-primary/25 bg-primary/5 p-6 sm:p-8">
          <h2 id="ai" className="flex items-center gap-2 text-2xl font-semibold tracking-tight"><Sparkles className="size-5 text-primary" />How AI Works</h2>
          <div className="mt-3 space-y-3 text-[15px] leading-relaxed">
            <p>AI can help with documents, summaries, transcription, patient communications and operational tasks: it drafts a visit note from a consented conversation, reads and classifies an uploaded document, summarizes a chart with citations, or explains an operational alert.</p>
            <p><strong>Authorized people remain responsible for sensitive clinical and administrative decisions.</strong> AI does not diagnose, prescribe, sign notes, change claims or message patients on its own. Anything an AI agent proposes waits for a person's approval, and every step is recorded.</p>
          </div>
        </section>

        <section aria-labelledby="status">
          <h2 id="status" className="text-2xl font-semibold tracking-tight">Current Platform Status</h2>
          <ul className="mt-5 space-y-3">
            {STATUS.map((s) => (
              <li key={s.label} className="flex flex-col gap-2 rounded-2xl border bg-card p-4 shadow-sm sm:flex-row sm:items-start sm:gap-4">
                <Badge variant={s.tone} className="w-fit shrink-0">{s.label}</Badge>
                <p className="text-[14px] leading-relaxed text-muted-foreground">{s.text}</p>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[13px] text-muted-foreground">Version {VERSION}</p>
        </section>

        <section id="legal" aria-labelledby="legal-title" className="scroll-mt-24 space-y-4">
          <h2 id="legal-title" className="flex items-center gap-2 text-2xl font-semibold tracking-tight"><Scale className="size-5" />Copyright & legal</h2>
          <div className="rounded-2xl border bg-card p-5 shadow-sm">
            <p className="text-[15px] font-semibold" data-testid="about-copyright">{COPYRIGHT_NOTICE}</p>
            <p className="mt-1.5 text-[14px] text-muted-foreground">This application's original source code, design and documentation are protected by copyright. No license is granted except as agreed in writing with the copyright holder.</p>
          </div>
          <div className="rounded-2xl border border-warning/40 bg-card p-5 shadow-sm">
            <p className="flex items-center gap-2 text-[14.5px] font-semibold"><ShieldAlert className="size-4 text-warning" />Use limitations</p>
            <p className="mt-1.5 text-[14px] text-muted-foreground">Demonstration build for synthetic data only. It is not HIPAA-certified, not ONC-certified and not validated for clinical use. AI output is a draft that requires human review.</p>
          </div>
          <div className="rounded-2xl border bg-card p-5 shadow-sm">
            <p className="text-[14.5px] font-semibold">Third-party software</p>
            <p className="mt-1.5 text-[13.5px] text-muted-foreground">Open-source components remain under their own licenses and copyrights, which are not affected by the notice above.</p>
            <ul className="mt-3 grid gap-x-6 gap-y-1 text-[13.5px] sm:grid-cols-2">{THIRD_PARTY.map((t) => <li key={t.name} className="flex justify-between gap-3"><span>{t.name}</span><span className="text-muted-foreground">{t.license}</span></li>)}</ul>
          </div>
          <div className="rounded-2xl border bg-card p-5 shadow-sm">
            <p className="text-[14.5px] font-semibold">Clinical code sets</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px] text-muted-foreground">{CODE_SET_NOTICES.map((n) => <li key={n}>{n}</li>)}</ul>
          </div>
        </section>
      </div>
    </PublicLayout>
  );
}

// ---------------------------------------------------------------------------------------------- /login

export function PublicLoginPage() {
  return (
    <PublicLayout overlay>
      <section className="relative isolate flex min-h-[calc(100dvh-1px)] items-center px-4 pb-16 pt-28 sm:px-6">
        <HospitalBackdrop />
        <div className="mx-auto w-full max-w-md rounded-3xl border border-white/40 bg-card/95 p-6 shadow-2xl shadow-blue-950/40 backdrop-blur sm:p-8">
          <LoginForm autoFocus emailId="login-email" />
        </div>
      </section>
    </PublicLayout>
  );
}
