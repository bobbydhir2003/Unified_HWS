import { ArrowRight, Check, Info, Scale, ShieldAlert, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LoginForm } from "@/features/auth/LoginForm";
import { CODE_SET_NOTICES, COPYRIGHT_NOTICE, THIRD_PARTY } from "@/lib/legal";
import { cn } from "@/lib/utils";
import { ADMIN_SOLUTION, DIFFERENTIATORS, HIGHLIGHTS, HOME_MODULES, MODULES, SOLUTIONS } from "./content";
import { HospitalBackdrop, PublicLayout } from "./PublicLayout";

const VERSION = import.meta.env.VITE_APP_VERSION ?? "development";

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
      <section className="relative isolate px-4 pb-16 pt-28 sm:px-6 lg:pb-24 lg:pt-32" aria-labelledby="home-title">
        <HospitalBackdrop />
        {/* Mobile order: headline → sign-in → highlights. Desktop: copy + highlights left, sign-in card right. */}
        <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[1.15fr_minmax(0,440px)] lg:gap-x-14 lg:gap-y-8">
          <div className="order-1 text-white lg:order-none lg:col-start-1 lg:row-start-1 lg:self-end">
            <p className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3.5 py-1.5 text-[12.5px] font-medium backdrop-blur">
              <Sparkles className="size-3.5 text-sky-300" />AI-assisted · Role-based · Unified
            </p>
            <h1 id="home-title" className="mt-5 text-[34px] font-semibold leading-[1.1] tracking-tight text-balance sm:text-5xl lg:text-[54px]">
              A Unified Hospital Management Platform for <span className="bg-gradient-to-r from-sky-300 to-blue-300 bg-clip-text text-transparent">Modern Healthcare</span>
            </h1>
            <p className="mt-5 max-w-xl text-[16px] leading-relaxed text-blue-50/85 sm:text-[17px]">
              Undeclared HMS connects patient care, clinical records, hospital operations, insurance, billing, and intelligent automation in one integrated platform. From the first appointment to discharge and follow-up, teams can coordinate their work in a single connected workspace.
            </p>
          </div>
          <div className="order-3 text-white lg:order-none lg:col-start-1 lg:row-start-2">
            <ul className="grid gap-3 sm:grid-cols-3">
              {HIGHLIGHTS.map((h) => (
                <li key={h.title} className="rounded-2xl border border-white/15 bg-white/[0.07] p-4 backdrop-blur-sm">
                  <span className="grid size-9 place-items-center rounded-lg bg-sky-400/20 text-sky-200"><h.icon className="size-[18px]" /></span>
                  <p className="mt-3 text-[14px] font-semibold leading-snug">{h.title}</p>
                  <p className="mt-1 text-[13px] leading-relaxed text-blue-50/75">{h.text}</p>
                </li>
              ))}
            </ul>
            <div className="mt-8">
              <Button asChild size="lg" className="h-11 bg-white text-[#0b2a66] hover:bg-blue-50"><Link to="/modules">Explore modules<ArrowRight /></Link></Button>
            </div>
          </div>
          <div id="sign-in" className="order-2 scroll-mt-24 self-center lg:order-none lg:col-start-2 lg:row-span-2 lg:row-start-1 rounded-3xl border border-white/40 bg-card/95 p-6 text-card-foreground shadow-2xl shadow-blue-950/40 backdrop-blur sm:p-8">
            <LoginForm emailId="home-email" />
          </div>
        </div>
      </section>

      <section className="px-4 py-16 sm:px-6 sm:py-20" aria-labelledby="overview-title">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Platform" title={<span id="overview-title">One Platform. Every Hospital Workflow.</span>} text="Connected tools for clinical teams, hospital departments, administrators, and patients." />
          <ul className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {HOME_MODULES.map((m) => (
              <li key={m.id}>
                <Link to={`/modules#${m.id}`} className="group flex h-full gap-3.5 rounded-2xl border bg-card p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 motion-reduce:transition-none motion-reduce:hover:translate-y-0">
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground"><m.icon className="size-5" /></span>
                  <span className="min-w-0">
                    <span className="block text-[14.5px] font-semibold leading-snug">{m.title}</span>
                    <span className="mt-1 block text-[13px] leading-relaxed text-muted-foreground">{m.short}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="border-t bg-muted/40 px-4 py-16 sm:px-6" aria-labelledby="journey-title">
        <div className="mx-auto max-w-7xl">
          <SectionHeading title={<span id="journey-title">One patient journey, every department</span>} text="Information follows the patient, so each team sees what it needs when it needs it." />
          <ol className="mx-auto mt-10 grid max-w-5xl gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {["Registration", "Insurance check", "Visit or ED", "Tests & medication", "Admission & discharge", "Billing & follow-up"].map((s, i) => (
              <li key={s} className="flex items-center gap-3 rounded-xl border bg-card px-3.5 py-3 text-[13.5px] font-medium shadow-sm lg:flex-col lg:text-center">
                <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary text-[12px] font-semibold text-primary-foreground">{i + 1}</span>{s}
              </li>
            ))}
          </ol>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button asChild variant="outline"><Link to="/solutions">See solutions by role<ArrowRight /></Link></Button>
            <Button asChild variant="ghost"><Link to="/about">About the platform</Link></Button>
          </div>
        </div>
      </section>
    </PublicLayout>
  );
}

// ---------------------------------------------------------------------------------------------- Modules

export function ModulesPage() {
  return (
    <PublicLayout>
      <PageHero eyebrow="Modules" title="Everything Your Hospital Needs, Connected." text="Explore the systems that bring clinical care, administration, and hospital operations into one workspace." />
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[220px_1fr]">
        <nav aria-label="Modules on this page" className="hidden lg:block">
          <ul className="sticky top-24 space-y-0.5 text-[13.5px]">
            {MODULES.map((m) => <li key={m.id}><a href={`#${m.id}`} className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"><m.icon className="size-4" />{m.title}</a></li>)}
          </ul>
        </nav>
        <div className="space-y-5">
          {MODULES.map((m) => (
            <section key={m.id} id={m.id} aria-labelledby={`${m.id}-title`} className="scroll-mt-24 rounded-3xl border bg-card p-6 shadow-sm sm:p-8">
              <div className="flex items-start gap-4">
                <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-primary/10 text-primary"><m.icon className="size-6" /></span>
                <div className="min-w-0">
                  <h2 id={`${m.id}-title`} className="text-xl font-semibold tracking-tight">{m.title}</h2>
                  <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{m.description}</p>
                </div>
              </div>
              <ul className="mt-5 grid gap-2 sm:grid-cols-2">
                {m.capabilities.map((c) => <li key={c} className="flex items-start gap-2 text-[14px]"><Check className="mt-0.5 size-4 shrink-0 text-primary" />{c}</li>)}
              </ul>
              {m.note && <p className="mt-4 flex items-start gap-2 rounded-xl bg-warning-soft/60 px-3 py-2 text-[13px]"><Info className="mt-0.5 size-4 shrink-0" />{m.note}</p>}
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
  { label: "Requires credentials", tone: "warning", text: "External AI (text and realtime voice) works only after an administrator configures a provider key; otherwise AI features run in a labeled simulation mode." },
  { label: "Not certified", tone: "danger", text: "Undeclared HMS has not been certified for clinical use and is not represented as HIPAA-compliant." },
];

export function PublicAboutPage() {
  return (
    <PublicLayout>
      <PageHero eyebrow="About" title="About Undeclared HMS" text="Undeclared HMS is a unified, AI-powered hospital management platform designed to bring clinical care, hospital operations, administrative workflows, and intelligent assistance into one connected environment." />
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
