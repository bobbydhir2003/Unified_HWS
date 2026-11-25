/**
 * Homepage hero: message · connected-hospital diagram · real product screenshots.
 * Original SVG/CSS graphics; animations are disabled for people who prefer reduced motion.
 * Screenshots are captured from the application with synthetic data (never mocked).
 */
import { BedDouble, Bot, CalendarClock, Cog, FileHeart, Layers, Network, Receipt, ShieldCheck, Sparkles, Stethoscope, Zap, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { AccessButton } from "./components";
import { BrandMark } from "./PublicLayout";

const MODULES = [
  { id: "clinical", title: "Clinical Care", sub: "EHR · Orders · Results", icon: Stethoscope, x: 19, y: 30 },
  { id: "operations", title: "Hospital Operations", sub: "ED · Inpatient · Beds · OR", icon: BedDouble, x: 81, y: 30 },
  { id: "revenue", title: "Revenue Cycle", sub: "Insurance · Claims · Billing", icon: Receipt, x: 14, y: 61 },
  { id: "staff", title: "Staff & Scheduling", sub: "Roster · Coverage gaps", icon: CalendarClock, x: 86, y: 61 },
  { id: "automation", title: "Automation", sub: "22 monitors", icon: Cog, x: 29, y: 90 },
  { id: "record", title: "Shared Patient Record", sub: "One patient, every team", icon: FileHeart, x: 71, y: 90 },
] as const;
const H = 110; // SVG viewBox height (width 100)
const CENTER = { x: 50, y: 58 };
const AI = { x: 50, y: 8 };

const STRIP = [
  { icon: Layers, title: "10 specialized AI agents", text: "Department-focused, conversational, and able to prepare real work." },
  { icon: Zap, title: "22 automation monitors", text: "Spot problems, open cases and keep follow-ups moving." },
  { icon: ShieldCheck, title: "Built-in human control", text: "Confirmations, independent approvals, permissions and audit trails." },
  { icon: Network, title: "One unified platform", text: "Clinical, operational and revenue workflows in one system." },
];

function Keyframes() {
  return (
    <style>{`@keyframes hms-flow{to{stroke-dashoffset:-24}}@keyframes hms-pulse{0%,100%{opacity:.55}50%{opacity:1}}@keyframes hms-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}`}</style>
  );
}

/** Desktop/tablet diagram: modules positioned around the platform core, joined by thin animated connections. */
function ConnectedDiagram() {
  return (
    <div className="relative mx-auto hidden aspect-[100/110] w-full max-w-[34rem] xl:block" data-testid="hero-diagram" role="img"
      aria-label="HMS Workflows at the center, connected to Clinical Care, Hospital Operations, Revenue Cycle, Staff & Scheduling, Automation with 22 monitors and the Shared Patient Record, with 10 AI agents above">
      <svg viewBox={`0 0 100 ${H}`} className="absolute inset-0 size-full" aria-hidden>
        <defs>
          <radialGradient id="hms-core-glow"><stop offset="0%" stopColor="#38bdf8" stopOpacity="0.35" /><stop offset="100%" stopColor="#38bdf8" stopOpacity="0" /></radialGradient>
          <linearGradient id="hms-line" x1="0" x2="1"><stop offset="0%" stopColor="#67e8f9" stopOpacity="0.15" /><stop offset="50%" stopColor="#67e8f9" stopOpacity="0.75" /><stop offset="100%" stopColor="#67e8f9" stopOpacity="0.15" /></linearGradient>
        </defs>
        <circle cx={CENTER.x} cy={CENTER.y} r="30" fill="url(#hms-core-glow)" />
        <ellipse cx={CENTER.x} cy={CENTER.y + 2} rx="38" ry="36" fill="none" stroke="#7dd3fc" strokeOpacity="0.16" strokeWidth="0.25" strokeDasharray="0.8 1.6" />
        {[...MODULES, AI].map((m, i) => (
          <g key={i}>
            <line x1={CENTER.x} y1={CENTER.y} x2={m.x} y2={m.y} stroke="#38bdf8" strokeOpacity="0.18" strokeWidth="0.9" />
            <line x1={CENTER.x} y1={CENTER.y} x2={m.x} y2={m.y} stroke="#a5f3fc" strokeOpacity="0.85" strokeWidth="0.3" strokeDasharray="2 4"
              className="motion-safe:[animation:hms-flow_2.4s_linear_infinite]" style={{ animationDelay: `${i * 0.3}s` }} />
            <circle cx={(CENTER.x * 0.38 + m.x * 0.62)} cy={(CENTER.y * 0.38 + m.y * 0.62)} r="0.9" fill="#a5f3fc"
              className="motion-safe:[animation:hms-pulse_2.6s_ease-in-out_infinite]" style={{ animationDelay: `${i * 0.4}s` }} />
          </g>
        ))}
      </svg>

      {/* Platform core */}
      <div className="absolute grid size-[32%] -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-sky-300/40 bg-gradient-to-b from-sky-500/25 to-blue-900/60 text-center shadow-[0_0_60px_rgba(56,189,248,0.35)] ring-8 ring-sky-400/[0.06]"
        style={{ left: `${CENTER.x}%`, top: `${(CENTER.y / H) * 100}%` }}>
        <div className="px-3">
          <BrandMark className="mx-auto size-8 2xl:size-10" />
          <p className="mt-1 text-body font-semibold leading-tight text-white 2xl:text-section">HMS Workflows</p>
          <p className="mt-0.5 text-label font-semibold uppercase leading-tight tracking-[0.12em] text-cyan-200/90">One connected<br />platform</p>
        </div>
      </div>

      {/* 10 AI agents */}
      <Link to="/ai-automation#agents" className="group absolute -translate-x-1/2 -translate-y-1/2 focus-visible:outline-none" style={{ left: `${AI.x}%`, top: `${(AI.y / H) * 100}%` }}>
        <span className="flex items-center gap-2 rounded-full border border-cyan-300/50 bg-gradient-to-b from-sky-400/30 to-blue-700/40 px-3.5 py-2 text-body font-semibold text-white shadow-[0_0_30px_rgba(34,211,238,0.35)] transition-colors group-hover:border-cyan-200 group-focus-visible:ring-2 group-focus-visible:ring-cyan-200 motion-safe:[animation:hms-float_5s_ease-in-out_infinite]">
          <span className="grid size-7 place-items-center rounded-full bg-white text-blue-700"><Bot className="size-4" aria-hidden /></span>10 AI Agents
        </span>
      </Link>

      {MODULES.map((m) => (
        <div key={m.id} className="group absolute w-[27%] max-w-[9.5rem] -translate-x-1/2 -translate-y-1/2" style={{ left: `${m.x}%`, top: `${(m.y / H) * 100}%` }} data-module={m.id}>
          <div className="rounded-2xl border border-sky-300/20 bg-white/[0.06] px-2 py-2 text-center shadow-[0_8px_30px_rgba(2,6,23,0.35)] backdrop-blur-sm transition-[border-color,transform,background-color] duration-200 group-hover:-translate-y-0.5 group-hover:border-cyan-300/60 group-hover:bg-white/[0.1]">
            <m.icon className="mx-auto size-5 text-cyan-300 drop-shadow-[0_0_8px_rgba(103,232,249,0.55)]" aria-hidden />
            <p className="mt-1 text-table font-semibold leading-tight text-white">{m.title}</p>
            <p className="mt-0.5 hidden text-label leading-snug text-white/60 2xl:block">{m.sub}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

/** Phone: a simplified, readable version of the same idea. */
function CompactDiagram() {
  return (
    <div className="mx-auto max-w-md xl:hidden" data-testid="hero-diagram-compact">
      <div className="mx-auto flex w-fit items-center gap-2 rounded-full border border-cyan-300/50 bg-sky-400/15 px-3 py-1.5 text-table font-semibold text-white"><Bot className="size-4 text-cyan-200" aria-hidden />10 AI Agents</div>
      <div className="mx-auto mt-3 flex w-fit items-center gap-2 rounded-2xl border border-sky-300/40 bg-sky-500/15 px-4 py-2.5"><BrandMark className="size-7" /><span className="text-body font-semibold text-white">HMS Workflows</span></div>
      <ul className="mt-3 grid grid-cols-2 gap-2">
        {MODULES.map((m) => (
          <li key={m.id} className="flex items-center gap-2 rounded-xl border border-sky-300/20 bg-white/[0.06] px-3 py-2 text-table font-medium text-white">
            <m.icon className="size-4 shrink-0 text-cyan-300" aria-hidden /><span className="min-w-0">{m.title}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Window({ src, srcSet, sizes, width, height, alt, className, priority }: {
  src: string; srcSet?: string; sizes?: string; width: number; height: number; alt: string; className?: string; priority?: boolean;
}) {
  return (
    <figure className={cn("overflow-hidden rounded-xl border border-white/15 bg-card shadow-[0_24px_60px_rgba(2,6,23,0.55),0_0_40px_rgba(56,189,248,0.18)]", className)}>
      <div className="flex items-center gap-1.5 border-b bg-subtle px-3 py-1.5" aria-hidden><span className="size-2 rounded-full bg-border" /><span className="size-2 rounded-full bg-border" /><span className="size-2 rounded-full bg-border" /></div>
      <img src={src} srcSet={srcSet} sizes={sizes} width={width} height={height} alt={alt} className="block h-auto w-full" loading={priority ? "eager" : "lazy"}
        fetchPriority={priority ? "high" : undefined} decoding="async" />
    </figure>
  );
}

function Screens() {
  return (
    <div className="relative" data-testid="hero-screens">
      <Window src="/images/product/command-center.webp" srcSet="/images/product/command-center-720.webp 720w, /images/product/command-center.webp 1440w"
        sizes="(min-width: 1280px) 36vw, (min-width: 768px) 48vw, 100vw" width={1440} height={1000} priority
        alt="HMS Workflows Command Center: hospital status figures and problems grouped by area with owners (synthetic data)"
        className="xl:[transform:perspective(1600px)_rotateY(-9deg)_rotateX(2deg)] xl:origin-right" />
      <Window src="/images/product/assist-panel.webp" srcSet="/images/product/assist-panel-360.webp 360w, /images/product/assist-panel.webp 640w"
        sizes="(min-width: 1280px) 17vw, 40vw" width={640} height={860}
        alt="Aurelia, the insurance and coverage AI agent, on case C1015: a follow-up task proposal waiting for a different person's approval (synthetic data)"
        className="absolute -bottom-14 -left-4 hidden w-[46%] xl:block" />
      <p className="mt-3 text-label text-white/60 xl:mt-6 xl:pl-[48%]">Real screens with synthetic data: the Command Center and Aurelia on an insurance case.</p>
    </div>
  );
}

function DottedWave() {
  const dots: { x: number; y: number; o: number }[] = [];
  for (let row = 0; row < 7; row++) {
    for (let i = 0; i <= 120; i++) {
      const x = (i / 120) * 1440;
      const y = 90 + row * 14 + Math.sin(i / 9 + row * 0.6) * (26 - row * 2.5);
      dots.push({ x, y, o: 0.08 + (row / 7) * 0.22 });
    }
  }
  return (
    <svg viewBox="0 0 1440 220" preserveAspectRatio="none" className="pointer-events-none absolute inset-x-0 bottom-0 h-40 w-full" aria-hidden>
      {dots.map((d, i) => <circle key={i} cx={d.x} cy={d.y} r="1.3" fill="#38bdf8" opacity={d.o} />)}
    </svg>
  );
}

export function HomeHero() {
  return (
    <section className="relative overflow-hidden bg-brand-navy px-4 pt-12 text-white sm:px-6 lg:pt-16" aria-labelledby="home-title" data-testid="home-hero">
      <Keyframes />
      <div className="pointer-events-none absolute inset-0 opacity-[0.06] [background-image:linear-gradient(to_right,white_1px,transparent_1px),linear-gradient(to_bottom,white_1px,transparent_1px)] [background-size:48px_48px]" aria-hidden />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_35%,rgba(56,189,248,0.16),transparent_60%)]" aria-hidden />
      <DottedWave />
      <div className="relative mx-auto grid max-w-[90rem] grid-cols-1 items-center gap-10 md:grid-cols-2 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1fr)_minmax(0,1.04fr)] xl:gap-8">
        {/* Message */}
        <div className="md:col-span-2 xl:col-span-1">
          <p className="inline-flex items-center gap-2 rounded-full border border-sky-300/30 bg-sky-400/10 px-3 py-1.5 text-table font-medium text-sky-100"><Sparkles className="size-4 text-cyan-300" aria-hidden />HMS Intelligence</p>
          <h1 id="home-title" className="mt-5 text-4xl font-semibold tracking-tight text-balance sm:text-5xl 2xl:text-6xl xl:leading-[1.06]">
            {"Your Entire Hospital. "}
            <span className="relative mt-1 block w-fit whitespace-nowrap bg-gradient-to-r from-sky-300 via-cyan-200 to-sky-400 bg-clip-text pb-2 text-transparent">
              Working as One.
              <svg viewBox="0 0 220 12" className="absolute -bottom-1 left-0 h-2.5 w-3/5" aria-hidden><path d="M2 9 C 60 2, 140 2, 218 6" fill="none" stroke="#38bdf8" strokeWidth="3" strokeLinecap="round" /></svg>
            </span>
          </h1>
          <p className="mt-6 max-w-xl text-lead leading-relaxed text-white/85 text-pretty">
            A unified hospital platform connecting clinical care, operations, revenue, automation, and 10 specialized AI agents — so every team works from the same patient record and knows what happens next.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <AccessButton className="bg-white text-brand-navy hover:bg-white/90" />
            <Button asChild size="lg" variant="outline" className="border-white/40 bg-transparent text-white hover:bg-white/10 hover:text-white"><Link to="/ai-automation">Meet HMS Intelligence<ArrowRight /></Link></Button>
          </div>
          <p className="mt-5 text-label text-white/55">In development and tested with synthetic data; not certified for clinical use.</p>
        </div>
        {/* Diagram */}
        <div><ConnectedDiagram /><CompactDiagram /></div>
        {/* Screens */}
        <Screens />
      </div>
      {/* Capability strip */}
      <ul className="relative mx-auto mt-16 grid max-w-[90rem] grid-cols-1 gap-6 border-t border-white/10 py-8 sm:grid-cols-2 lg:grid-cols-4 xl:mt-24" data-testid="hero-strip">
        {STRIP.map((s) => (
          <li key={s.title} className="flex gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-xl border border-sky-300/30 bg-sky-400/10 shadow-[0_0_20px_rgba(56,189,248,0.2)]"><s.icon className="size-5 text-cyan-300" aria-hidden /></span>
            <span><span className="block text-section font-semibold text-white">{s.title}</span><span className="mt-0.5 block text-table leading-relaxed text-white/70">{s.text}</span></span>
          </li>
        ))}
      </ul>
    </section>
  );
}
