/** Public website building blocks and original diagrams (HTML/CSS, theme tokens; readable at phone widths). */
import { ArrowDown, ArrowRight, Check, LogIn } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { FLOW, PATHWAYS, PRODUCT_STATUS, SHOTS, type ShotKey } from "./content";

// ---------------------------------------------------------------------------------------------- layout primitives

export function Section({ id, tone = "plain", className, children, labelledBy, width = "max-w-6xl" }: {
  id?: string; tone?: "plain" | "subtle" | "brand"; className?: string; children: React.ReactNode; labelledBy?: string; width?: string;
}) {
  return (
    <section id={id} aria-labelledby={labelledBy} className={cn("scroll-mt-20 px-4 py-16 sm:px-6 lg:py-24",
      tone === "subtle" && "border-y bg-subtle", tone === "plain" && "bg-card", tone === "brand" && "bg-brand-navy text-white", className)}>
      <div className={cn("mx-auto", width)}>{children}</div>
    </section>
  );
}

export function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn("mb-3 text-label font-semibold uppercase tracking-[0.12em] text-primary", className)}>{children}</p>;
}

export function H2({ id, children, className }: { id?: string; children: React.ReactNode; className?: string }) {
  return <h2 id={id} className={cn("text-3xl font-semibold tracking-tight text-balance text-heading sm:text-4xl", className)}>{children}</h2>;
}

export function Lead({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn("mt-4 max-w-2xl text-section leading-relaxed text-muted-foreground text-pretty sm:text-lead", className)}>{children}</p>;
}

export function SectionIntro({ eyebrow, title, id, children, className }: { eyebrow: string; title: React.ReactNode; id: string; children?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("max-w-3xl", className)}>
      <Eyebrow>{eyebrow}</Eyebrow>
      <H2 id={id}>{title}</H2>
      {children && <Lead>{children}</Lead>}
    </div>
  );
}

export function CheckList({ items, className }: { items: string[]; className?: string }) {
  return (
    <ul className={cn("space-y-2 text-body", className)}>
      {items.map((t) => <li key={t} className="flex items-start gap-2"><Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden /><span>{t}</span></li>)}
    </ul>
  );
}

/** A real screenshot of the application (synthetic data), WebP at 720/1440 widths, in a light browser frame. */
export function ProductShot({ shot, className, priority, caption = true, sizes = "(min-width: 1024px) 60vw, 100vw", crop }: {
  shot: ShotKey; className?: string; priority?: boolean; caption?: boolean | string; sizes?: string; crop?: string;
}) {
  const s = SHOTS[shot];
  return (
    <figure className={cn("overflow-hidden rounded-xl border bg-card shadow-[0_12px_40px_rgba(16,24,40,0.10)]", className)}>
      <div className="flex items-center gap-1.5 border-b bg-subtle px-3 py-2" aria-hidden>
        <span className="size-2.5 rounded-full bg-border" /><span className="size-2.5 rounded-full bg-border" /><span className="size-2.5 rounded-full bg-border" />
      </div>
      <img src={`/images/product/${s.src}.webp`} srcSet={`/images/product/${s.src}-720.webp 720w, /images/product/${s.src}.webp 1440w`} sizes={sizes}
        width={s.w} height={s.h} alt={s.alt} loading={priority ? "eager" : "lazy"} decoding="async" fetchPriority={priority ? "high" : undefined}
        className={cn("block h-auto w-full", crop && "object-cover", crop)} />
      {caption && <figcaption className="border-t bg-subtle px-4 py-2 text-label text-muted-foreground">{typeof caption === "string" ? caption : "Screenshot of HMS Workflows with synthetic data."}</figcaption>}
    </figure>
  );
}

export function PageHero({ eyebrow, title, text, children, aside }: { eyebrow: string; title: string; text: string; children?: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="border-b bg-gradient-to-b from-accent/40 to-card px-4 pb-16 pt-14 sm:px-6 lg:pb-20 lg:pt-20" aria-labelledby="page-title">
      <div className={cn("mx-auto max-w-6xl", aside && "grid items-center gap-12 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]")}>
        <div>
          <Eyebrow>{eyebrow}</Eyebrow>
          <h1 id="page-title" className="max-w-3xl text-4xl font-semibold tracking-tight text-balance text-heading sm:text-5xl">{title}</h1>
          <Lead>{text}</Lead>
          {children}
        </div>
        {aside}
      </div>
    </section>
  );
}

export function AnchorChips({ label, items }: { label: string; items: { id: string; title: string; icon: React.ElementType }[] }) {
  return (
    <nav aria-label={label} className="mt-8 flex flex-wrap gap-2">
      {items.map((a) => (
        <Link key={a.id} to={`#${a.id}`} className="inline-flex min-h-10 items-center gap-2 rounded-full border bg-card px-3.5 py-2 text-table font-medium text-foreground hover:border-primary/40 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
          <a.icon className="size-4 text-primary" aria-hidden />{a.title}
        </Link>
      ))}
    </nav>
  );
}

export function StatusList() {
  return (
    <ul className="divide-y rounded-xl border bg-card" data-testid="product-status">
      {PRODUCT_STATUS.map((s) => (
        <li key={s.label} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-start sm:gap-5">
          <Badge variant={s.tone} className="w-fit shrink-0 sm:w-36 sm:justify-center">{s.label}</Badge>
          <p className="text-body leading-relaxed text-muted-foreground">{s.text}</p>
        </li>
      ))}
    </ul>
  );
}

/** Primary access action: Sign in for visitors, Open workspace for signed-in users. Never a demo login. */
export function AccessButton({ size = "lg", variant = "default", className }: { size?: "sm" | "lg" | "default"; variant?: "default" | "outline"; className?: string }) {
  const { status } = useAuth();
  if (status === "authenticated") return <Button asChild size={size} variant={variant} className={className}><Link to="/">Open your workspace<ArrowRight /></Link></Button>;
  return <Button asChild size={size} variant={variant} className={className}><Link to="/login"><LogIn />Sign in</Link></Button>;
}

// ---------------------------------------------------------------------------------------------- diagrams

/** "Many teams, one record": departments → shared foundation → My work / Command Center. */
export function ConnectedHospitalDiagram({ departments }: { departments: { name: string; icon: React.ElementType }[] }) {
  return (
    <figure aria-labelledby="hub-caption" className="rounded-2xl border bg-card p-4 shadow-[0_12px_40px_rgba(16,24,40,0.06)] sm:p-6">
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Departments">
        {departments.map((d) => (
          <li key={d.name} className="flex min-w-0 items-center gap-2 rounded-lg border bg-subtle px-2.5 py-2 text-table font-medium text-heading">
            <d.icon className="size-4 shrink-0 text-primary" aria-hidden /><span className="truncate">{d.name}</span>
          </li>
        ))}
      </ul>
      <Connector />
      <div className="rounded-xl bg-primary px-4 py-4 text-center text-primary-foreground">
        <p className="text-section font-semibold">One patient record · one list of owned work</p>
        <p className="mt-1 text-table opacity-90">Shared identity, visits, orders and results · cases, tasks and approvals · role-based access</p>
      </div>
      <Connector />
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="rounded-lg border border-primary/30 bg-accent/50 px-3 py-2.5"><p className="text-body font-semibold text-heading">My work</p><p className="text-table text-muted-foreground">What each person is responsible for</p></div>
        <div className="rounded-lg border border-primary/30 bg-accent/50 px-3 py-2.5"><p className="text-body font-semibold text-heading">Command Center</p><p className="text-table text-muted-foreground">What the whole hospital is waiting on</p></div>
      </div>
      <figcaption id="hub-caption" className="mt-4 text-center text-label text-muted-foreground">Each department works in its own workspace, on the same shared foundation.</figcaption>
    </figure>
  );
}

function Connector() {
  return <div className="flex justify-center py-2 text-primary/60" aria-hidden><ArrowDown className="size-5" /></div>;
}

/** Tabbed patient pathways: outpatient, emergency and inpatient are shown separately. */
export function PathwayExplorer() {
  const [active, setActive] = React.useState(PATHWAYS[0].id);
  const tabs = React.useRef<(HTMLButtonElement | null)[]>([]);
  const p = PATHWAYS.find((x) => x.id === active) ?? PATHWAYS[0];
  const onKey = (e: React.KeyboardEvent, i: number) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (e.key === "Home" || e.key === "End" || d) {
      e.preventDefault();
      const n = e.key === "Home" ? 0 : e.key === "End" ? PATHWAYS.length - 1 : (i + d + PATHWAYS.length) % PATHWAYS.length;
      setActive(PATHWAYS[n].id);
      tabs.current[n]?.focus();
    }
  };
  return (
    <div className="mt-10">
      <div role="tablist" aria-label="Patient pathway" className="inline-flex max-w-full flex-wrap gap-1 rounded-xl border bg-card p-1">
        {PATHWAYS.map((x, i) => (
          <button key={x.id} ref={(el) => { tabs.current[i] = el; }} type="button" role="tab" id={`tab-${x.id}`} aria-selected={x.id === active}
            aria-controls={`panel-${x.id}`} tabIndex={x.id === active ? 0 : -1} onClick={() => setActive(x.id)} onKeyDown={(e) => onKey(e, i)}
            className={cn("inline-flex min-h-10 items-center gap-2 rounded-lg px-3.5 py-2 text-body font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
              x.id === active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-heading")}>
            <x.icon className="size-4" aria-hidden />{x.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${p.id}`} aria-labelledby={`tab-${p.id}`} tabIndex={0} className="mt-6 focus-visible:outline-none" data-testid="journey">
        <p className="text-body text-muted-foreground"><span className="font-semibold text-heading">Illustrative example: </span>{p.scenario}</p>
        <ol className="mt-5 grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          {p.steps.map((s, i) => (
            <li key={s.title} className="relative flex flex-col rounded-xl border bg-card p-4">
              <div className="flex items-center gap-3">
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary text-table font-semibold tabular text-primary-foreground" aria-hidden>{i + 1}</span>
                <div className="min-w-0">
                  <h3 className="text-section font-semibold leading-tight text-heading">{s.title}</h3>
                  <p className="text-label text-muted-foreground">{s.team}</p>
                </div>
              </div>
              <p className="mt-3 text-table leading-relaxed text-foreground">{s.happens}</p>
              <p className="mt-2 flex-1 text-table leading-relaxed text-muted-foreground"><span className="font-medium text-heading">Platform: </span>{s.platform}</p>
              {s.monitor && <p className="mt-3 w-fit rounded-full border border-warning/35 bg-warning-soft px-2 py-0.5 text-label font-medium text-warning-foreground">Monitor: {s.monitor}</p>}
            </li>
          ))}
        </ol>
        <p className="mt-4 text-table text-muted-foreground">Fictional patient. Pathways vary: not every patient follows every step, and steps can happen in a different order.</p>
      </div>
    </div>
  );
}

/** Monitor → case → (AI) → (proposal) → approval → task → outcome, with optional steps marked. */
export function AutomationFlow({ className, dark }: { className?: string; dark?: boolean }) {
  return (
    <ol className={cn("grid gap-2 sm:grid-cols-2 lg:flex lg:items-stretch lg:gap-0", className)} aria-label="How a problem is handled" data-testid="automation-flow">
      {FLOW.map((s, i) => (
        <li key={s.title} className="flex items-center lg:flex-1">
          <div className={cn("flex h-full w-full flex-col justify-center rounded-lg px-3 py-3 text-center",
            s.optional ? "border-2 border-dashed" : "border",
            dark ? (s.optional ? "border-white/40 bg-white/5" : "border-white/20 bg-white/10") : (s.optional ? "border-primary/40 bg-card" : "border-primary/25 bg-accent/60"))}>
            <span className={cn("text-label font-semibold tabular", dark ? "text-white/70" : "text-primary")}>{i + 1}{s.optional ? " · optional" : ""}</span>
            <span className={cn("mt-0.5 text-body font-semibold leading-snug", dark ? "text-white" : "text-heading")}>{s.title}</span>
          </div>
          {i < FLOW.length - 1 && <ArrowRight className={cn("mx-1 hidden size-4 shrink-0 lg:block", dark ? "text-white/50" : "text-primary/50")} aria-hidden />}
        </li>
      ))}
    </ol>
  );
}
