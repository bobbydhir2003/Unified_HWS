import { ArrowRight, LogIn, Menu, X } from "lucide-react";
import * as React from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { COPYRIGHT_NOTICE } from "@/lib/legal";
import { LogoMark } from "@/components/common/Logo";
import { PRODUCT_TAGLINE } from "@/lib/legal";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Home", end: true },
  { to: "/modules", label: "Modules" },
  { to: "/solutions", label: "Solutions" },
  { to: "/about", label: "About" },
];

/** HMS Workflows continuous-route "W" mark (shared with the app); sized by className. */
export function BrandMark({ className }: { className?: string }) {
  return <span className={cn("inline-grid size-9 shrink-0", className)}><LogoMark size={36} className="size-full" /></span>;
}

/** Sign In: on the homepage it moves focus to the hero sign-in form; elsewhere it opens /login. */
function useSignIn() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  return React.useCallback(() => {
    const email = pathname === "/" ? document.getElementById("home-email") : null;
    if (email) {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      email.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
      (email as HTMLInputElement).focus({ preventScroll: true });
    } else navigate("/login");
  }, [navigate, pathname]);
}

function Header({ overlay }: { overlay: boolean }) {
  const { status } = useAuth();
  const [open, setOpen] = React.useState(false);
  const signIn = useSignIn();
  const { pathname } = useLocation();
  React.useEffect(() => setOpen(false), [pathname]);
  const authed = status === "authenticated";
  const linkCls = ({ isActive }: { isActive: boolean }) => cn(
    "relative rounded-md px-3 py-2 text-body font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300",
    overlay ? "text-white/80 hover:text-white" : "text-muted-foreground hover:text-foreground",
    isActive && (overlay ? "text-white after:absolute after:inset-x-3 after:-bottom-0.5 after:h-0.5 after:rounded after:bg-sky-300" : "text-foreground after:absolute after:inset-x-3 after:-bottom-0.5 after:h-0.5 after:rounded after:bg-primary"),
  );
  const action = authed
    ? <Button asChild size="sm" className="h-9"><Link to="/">Open workspace<ArrowRight /></Link></Button>
    : <Button size="sm" className="h-9" onClick={signIn}><LogIn />Sign In</Button>;
  return (
    <header className={cn("z-30", overlay ? "absolute inset-x-0 top-0" : "sticky top-0 border-b bg-card/90 backdrop-blur")}>
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Link to="/" className="flex min-w-0 items-center gap-2.5 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300" aria-label="HMS Workflows home">
          <BrandMark />
          <span className="min-w-0">
            <span className={cn("block text-section font-semibold leading-tight tracking-tight", overlay ? "text-white" : "text-heading")}>HMS <span className="font-normal">Workflows</span></span>
            <span className={cn("hidden text-label leading-tight sm:block", overlay ? "text-white/75" : "text-muted-foreground")}>{PRODUCT_TAGLINE}</span>
          </span>
        </Link>
        <nav aria-label="Primary" className="ml-auto hidden items-center gap-1 md:flex">
          {NAV.map((n) => <NavLink key={n.to} to={n.to} end={n.end} className={linkCls}>{n.label}</NavLink>)}
        </nav>
        <div className="ml-auto hidden md:ml-4 md:block">{action}</div>
        <button type="button" className={cn("ml-auto grid size-10 place-items-center rounded-lg md:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300", overlay ? "text-white hover:bg-white/10" : "hover:bg-muted")}
          aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} aria-controls="public-mobile-nav" onClick={() => setOpen((o) => !o)}>
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </div>
      {open && (
        <div id="public-mobile-nav" className="mx-4 mb-3 rounded-2xl border bg-card p-2 shadow-xl md:hidden">
          <nav aria-label="Mobile" className="grid">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cn("rounded-lg px-3 py-3 text-section font-medium", isActive ? "bg-accent text-accent-foreground" : "text-foreground hover:bg-muted")}>{n.label}</NavLink>
            ))}
          </nav>
          <div className="border-t p-2 pt-3">{authed ? action : <Button className="h-11 w-full" onClick={() => { setOpen(false); signIn(); }}><LogIn />Sign In</Button>}</div>
        </div>
      )}
    </header>
  );
}

function Footer() {
  return (
    <footer className="border-t bg-card">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
        <div className="space-y-3">
          <div className="flex items-center gap-2.5"><BrandMark className="size-8" /><span className="text-section font-semibold">HMS Workflows</span></div>
          <p className="max-w-sm text-body leading-relaxed text-muted-foreground">A unified, AI-powered hospital management platform. Demonstration build with synthetic data; not certified for clinical use.</p>
        </div>
        <nav aria-label="Footer" className="grid content-start gap-2 text-body">
          <p className="font-medium">Platform</p>
          <Link to="/modules" className="text-muted-foreground hover:text-foreground">Modules</Link>
          <Link to="/solutions" className="text-muted-foreground hover:text-foreground">Solutions</Link>
          <Link to="/about" className="text-muted-foreground hover:text-foreground">About</Link>
        </nav>
        <nav aria-label="Account and legal" className="grid content-start gap-2 text-body">
          <p className="font-medium">Account & legal</p>
          <Link to="/login" className="text-muted-foreground hover:text-foreground">Sign in</Link>
          <Link to="/forgot-password" className="text-muted-foreground hover:text-foreground">Reset password</Link>
          <Link to="/about#legal" className="text-muted-foreground hover:text-foreground">Legal notices</Link>
        </nav>
      </div>
      <div className="bg-[#071a44] text-blue-100/85">
        <div className="mx-auto flex max-w-7xl flex-col items-center gap-2 px-4 py-5 text-center text-table sm:flex-row sm:justify-between sm:px-6 sm:text-left">
          <p data-testid="public-copyright">{COPYRIGHT_NOTICE}</p>
          <p className="flex items-center gap-2">
            <span className="font-medium text-white">HMS Workflows</span>
            <span aria-hidden className="text-blue-100/40">|</span>
            <Link to="/about#legal" className="rounded underline-offset-4 hover:text-white hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300">About &amp; Legal</Link>
          </p>
        </div>
      </div>
    </footer>
  );
}

/** Public website shell. `overlay` puts a transparent header over a full-bleed hero. */
export function PublicLayout({ children, overlay = false }: { children: React.ReactNode; overlay?: boolean }) {
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
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-card focus:px-4 focus:py-2 focus:shadow-lg">Skip to content</a>
      <Header overlay={overlay} />
      <main id="main" className="flex-1">{children}</main>
      <Footer />
    </div>
  );
}

/** Shared full-bleed hospital background with readable overlays (used by the homepage hero and /login). */
export function HospitalBackdrop({ className }: { className?: string }) {
  return (
    <div className={cn("absolute inset-0 -z-10 overflow-hidden bg-[#0b1f4d]", className)} aria-hidden>
      <picture>
        <source media="(max-width: 767px)" srcSet="/images/hospital-hero-960.webp" type="image/webp" />
        <img src="/images/hospital-hero.webp" alt="" fetchPriority="high" decoding="async"
          className="h-full w-full object-cover object-[70%_center]" />
      </picture>
      <div className="absolute inset-0 bg-gradient-to-r from-[#071a44]/95 via-[#0b2a66]/75 to-[#0b2a66]/10" />
      <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-[#071a44]/70 to-transparent" />
    </div>
  );
}
