import { ArrowRight, LogIn, Menu, X } from "lucide-react";
import * as React from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { LogoMark } from "@/components/common/Logo";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { COPYRIGHT_NOTICE, PRODUCT_TAGLINE } from "@/lib/legal";
import { cn } from "@/lib/utils";

/** Public navigation: Platform · Solutions · AI & Automation · About · [Sign in]. */
const NAV = [
  { to: "/platform", label: "Platform" },
  { to: "/solutions", label: "Solutions" },
  { to: "/ai-automation", label: "AI & Automation" },
  { to: "/about", label: "About" },
];

/** HMS Workflows continuous-route "W" mark (shared with the app); sized by className. */
export function BrandMark({ className }: { className?: string }) {
  return <span className={cn("inline-grid size-9 shrink-0", className)}><LogoMark size={36} className="size-full" /></span>;
}

function Wordmark() {
  return (
    <Link to="/" className="flex min-w-0 items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60" aria-label="HMS Workflows home">
      <BrandMark />
      <span className="min-w-0 leading-tight">
        <span className="block text-section font-semibold tracking-tight text-heading">HMS <span className="font-normal">Workflows</span></span>
        <span className="hidden text-label text-muted-foreground lg:block">{PRODUCT_TAGLINE}</span>
      </span>
    </Link>
  );
}

function Header() {
  const { status } = useAuth();
  const [open, setOpen] = React.useState(false);
  const { pathname, hash } = useLocation();
  React.useEffect(() => setOpen(false), [pathname, hash]);
  const authed = status === "authenticated";
  const linkCls = ({ isActive }: { isActive: boolean }) => cn(
    "relative whitespace-nowrap rounded-md px-3 py-2 text-body font-medium text-muted-foreground transition-colors hover:text-heading focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
    isActive && "text-heading after:absolute after:inset-x-3 after:-bottom-[13px] after:h-0.5 after:rounded after:bg-primary",
  );
  const actions = authed
    ? <Button asChild size="sm"><Link to="/">Open workspace<ArrowRight /></Link></Button>
    : <Button asChild size="sm"><Link to="/login"><LogIn />Sign in</Link></Button>;
  return (
    <header className="sticky top-0 z-30 border-b bg-card/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Wordmark />
        <nav aria-label="Primary" className="ml-auto hidden items-center gap-1 lg:flex">
          {NAV.map((n) => <NavLink key={n.to} to={n.to} className={linkCls}>{n.label}</NavLink>)}
        </nav>
        <div className="ml-auto hidden items-center gap-2 lg:ml-4 lg:flex">{actions}</div>
        <button type="button" className="ml-auto grid size-11 place-items-center rounded-md hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 lg:hidden"
          aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} aria-controls="public-mobile-nav" onClick={() => setOpen((o) => !o)}>
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </div>
      {open && (
        <div id="public-mobile-nav" className="border-t bg-card px-4 pb-4 pt-2 lg:hidden">
          <nav aria-label="Mobile" className="grid">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} className={({ isActive }) => cn("rounded-md px-3 py-3 text-section font-medium", isActive ? "bg-accent text-accent-foreground" : "text-foreground hover:bg-muted")}>{n.label}</NavLink>
            ))}
          </nav>
          <div className="mt-3 grid gap-2 border-t pt-3 [&_a]:h-11 [&_a]:w-full">{actions}</div>
        </div>
      )}
    </header>
  );
}

function Footer() {
  const col = "grid content-start gap-2 text-body";
  const a = "text-muted-foreground hover:text-heading hover:underline underline-offset-4";
  return (
    <footer className="border-t bg-card">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-2 lg:grid-cols-[1.6fr_1fr_1fr_1fr]">
        <div className="space-y-3">
          <div className="flex items-center gap-2.5"><BrandMark className="size-8" /><span className="text-section font-semibold text-heading">HMS <span className="font-normal">Workflows</span></span></div>
          <p className="max-w-sm text-body leading-relaxed text-muted-foreground">A hospital management platform: one shared patient record, owned and tracked work, one live view of the hospital, and AI that assists while people decide.</p>
        </div>
        <nav aria-label="Platform" className={col}>
          <p className="font-semibold text-heading">Platform</p>
          <Link to="/platform" className={a}>Overview</Link>
          <Link to="/platform#coordination" className={a}>Command Center</Link>
          <Link to="/ai-automation" className={a}>AI & Automation</Link>
          <Link to="/platform#clinical-care" className={a}>Patient portal</Link>
        </nav>
        <nav aria-label="Company" className={col}>
          <p className="font-semibold text-heading">Company</p>
          <Link to="/solutions" className={a}>Solutions by team</Link>
          <Link to="/about" className={a}>About</Link>
          <Link to="/about#status" className={a}>Product status</Link>
          <Link to="/about#legal" className={a}>Legal notices</Link>
        </nav>
        <nav aria-label="Access" className={col}>
          <p className="font-semibold text-heading">Access</p>
          <Link to="/login" className={a}>Sign in</Link>
        </nav>
      </div>
      <div className="border-t">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-5 text-table text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p data-testid="public-copyright">{COPYRIGHT_NOTICE}</p>
          <p>Demonstration build with synthetic data · not certified for clinical use · <Link to="/about#legal" className="hover:text-heading hover:underline">About &amp; legal</Link></p>
        </div>
      </div>
    </footer>
  );
}

/** Public website shell: light header, content, footer. Scrolls to #hash targets. */
export function PublicLayout({ children }: { children: React.ReactNode }) {
  const { hash, pathname } = useLocation();
  React.useEffect(() => {
    if (hash) {
      const t = window.setTimeout(() => document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView({ block: "start" }), 50);
      return () => window.clearTimeout(t);
    }
    window.scrollTo(0, 0);
  }, [hash, pathname]);
  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-card focus:px-4 focus:py-2 focus:shadow-lg">Skip to content</a>
      <Header />
      <main id="main" className="flex-1">{children}</main>
      <Footer />
    </div>
  );
}
