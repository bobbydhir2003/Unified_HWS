import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { ECOSYSTEM } from "./content";
import { BrandMark } from "./PublicLayout";

/** Node centers (percent of the radial canvas), clockwise from top-left. */
const POS: [number, number][] = [[19, 15], [81, 15], [90, 50], [81, 85], [19, 85], [10, 50]];

function NodeCard({ n, className }: { n: (typeof ECOSYSTEM)[number]; className?: string }) {
  return (
    <Link to={n.to} aria-label={`${n.title}: ${n.text}`}
      className={cn("group block rounded-2xl border border-white/15 bg-white/[0.06] p-4 text-left text-white shadow-lg shadow-blue-950/30 backdrop-blur-md transition-all",
        "hover:border-sky-300/60 hover:bg-white/[0.11] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 motion-safe:hover:-translate-y-0.5", className)}>
      <span className="flex items-center gap-2.5">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-sky-400 to-blue-600 shadow-md shadow-blue-900/40"><n.icon className="size-[18px]" /></span>
        <span className="text-body font-semibold leading-tight">{n.title}</span>
        <ArrowUpRight className="ml-auto size-4 shrink-0 text-sky-200/60 transition-colors group-hover:text-sky-200" aria-hidden />
      </span>
      <span className="mt-2 block text-table leading-relaxed text-blue-100/75">{n.text}</span>
    </Link>
  );
}

function Hub({ className }: { className?: string }) {
  return (
    <div className={cn("relative grid place-items-center", className)}>
      <span className="eco-ring absolute size-full rounded-full border border-sky-300/30" aria-hidden />
      <span className="eco-ring eco-ring-delay absolute size-full rounded-full border border-sky-300/20" aria-hidden />
      <div className="relative grid size-full place-items-center rounded-full bg-[radial-gradient(circle_at_30%_25%,#3b82f6,#1d4ed8_45%,#0b2a66)] p-4 text-center text-white shadow-[0_0_60px_rgba(56,189,248,0.35)] ring-1 ring-white/25">
        <div>
          <BrandMark className="mx-auto size-11" />
          <p className="mt-2 text-section font-semibold leading-tight">HMS Workflows</p>
          <p className="mt-0.5 text-label text-blue-100/80">One connected workspace</p>
        </div>
      </div>
    </div>
  );
}

export function Ecosystem() {
  return (
    <div data-testid="ecosystem">
      {/* Radial layout (wide screens). */}
      <div className="relative mx-auto hidden h-[560px] max-w-6xl xl:block">
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
          <ellipse cx="50" cy="50" rx="34" ry="30" fill="none" stroke="#7dd3fc" strokeOpacity="0.12" strokeDasharray="1 2" vectorEffect="non-scaling-stroke" />
          {POS.map(([x, y], i) => (
            <g key={i}>
              <line x1="50" y1="50" x2={x} y2={y} stroke="#7dd3fc" strokeOpacity="0.32" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
              <line x1="50" y1="50" x2={x} y2={y} className="eco-flow" stroke="#bae6fd" strokeOpacity="0.8" strokeWidth="2" strokeDasharray="4 18"
                strokeLinecap="round" vectorEffect="non-scaling-stroke" style={{ animationDelay: `${i * -0.4}s` }} />
            </g>
          ))}
        </svg>
        <Hub className="absolute left-1/2 top-1/2 size-48 -translate-x-1/2 -translate-y-1/2" />
        <ul>
          {ECOSYSTEM.map((n, i) => (
            <li key={n.id} className="absolute w-60 -translate-x-1/2 -translate-y-1/2" style={{ left: `${POS[i][0]}%`, top: `${POS[i][1]}%` }}>
              <NodeCard n={n} />
            </li>
          ))}
        </ul>
      </div>
      {/* Stacked layout (tablet and mobile). */}
      <div className="mx-auto max-w-3xl xl:hidden">
        <Hub className="mx-auto size-40" />
        <div className="mx-auto h-6 w-px bg-gradient-to-b from-sky-300/60 to-sky-300/10" aria-hidden />
        <ul className="grid gap-3 sm:grid-cols-2">
          {ECOSYSTEM.map((n) => <li key={n.id}><NodeCard n={n} className="h-full" /></li>)}
        </ul>
      </div>
    </div>
  );
}
