import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LegalFooter } from "@/components/common/LegalFooter";
import { LogoMark } from "@/components/common/Logo";
import { useLiveConnection } from "@/lib/live";
import { Bell, Building2, Check, Rows3, Rows4, ChevronDown, ChevronRight, ChevronsLeft, ChevronsUpDown, FlaskConical, Info, LifeBuoy, LogOut, Menu, Monitor, MoreHorizontal, Moon, Search, Sun, UserRound } from "lucide-react";
import * as React from "react";
import { Link, NavLink, Outlet, useLocation, useMatches, useNavigate } from "react-router-dom";
import { Dialog, SheetContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
  Popover, PopoverContent, PopoverTrigger, Tooltip,
} from "@/components/ui/menu";
import { Avatar, Kbd, Skeleton } from "@/components/ui/misc";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fromNow } from "@/lib/format";
import { ROLE_LABELS } from "@/lib/types";
import { cn } from "@/lib/utils";
import { CommandSearch } from "./CommandSearch";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";
import { PRODUCT_NAME } from "@/lib/legal";
import { NAV, type NavItem, primaryNav, profileFor } from "./nav";

// ---------- Breadcrumb label overrides (e.g. patient name for /patients/:id) ----------
const CrumbCtx = React.createContext<{ set: (path: string, label: string | null) => void; labels: Record<string, string> }>({
  set: () => {}, labels: {},
});
export function useCrumb(label: string | null | undefined) {
  const { set } = React.useContext(CrumbCtx);
  const { pathname } = useLocation();
  const matches = useMatches();
  const path = matches[matches.length - 1]?.pathname ?? pathname;
  React.useEffect(() => {
    if (!label) return;
    set(path, label);
    return () => set(path, null);
  }, [label, path, set]);
}

// ---------- Theme ----------
type Theme = "light" | "dark" | "system";
function applyTheme(t: Theme) {
  const dark = t === "dark" || (t === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  try {
    if (t === "system") localStorage.removeItem("ud-theme");
    else localStorage.setItem("ud-theme", t);
  } catch { /* ignore */ }
}
function useTheme() {
  const [theme, setTheme] = React.useState<Theme>(() => {
    try { return (localStorage.getItem("ud-theme") as Theme) || "system"; } catch { return "system"; }
  });
  React.useEffect(() => applyTheme(theme), [theme]);
  return [theme, setTheme] as const;
}

function Brand({ collapsed }: { collapsed?: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-2.5 rounded-md px-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50" aria-label={`${PRODUCT_NAME} home`}>
      <LogoMark size={28} />
      {!collapsed && <span className="text-section font-semibold tracking-tight text-heading">HMS <span className="font-normal text-muted-foreground">Workflows</span></span>}
    </Link>
  );
}

function SidebarLink({ it, collapsed, onNavigate, count }: { it: NavItem; collapsed: boolean; onNavigate?: () => void; count?: number }) {
  return (
    <li>
      <Tooltip content={collapsed ? it.label : null} side="right">
        <NavLink
          to={it.to}
          end={it.to === "/"}
          onClick={onNavigate}
          className={({ isActive }) => cn(
            "group flex h-9 items-center gap-3 rounded-md px-2.5 text-body font-medium text-sidebar-foreground transition-colors hover:bg-sidebar-accent hover:text-heading focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
            isActive && "bg-sidebar-active font-semibold text-sidebar-active-foreground hover:bg-sidebar-active hover:text-sidebar-active-foreground",
            collapsed && "justify-center px-0",
          )}
        >
          <it.icon className="size-[18px] shrink-0" />
          {!collapsed && <span className="truncate">{it.label}</span>}
          {!collapsed && !!count && <span className="ml-auto rounded-full bg-muted px-1.5 text-label font-semibold tabular text-muted-foreground" aria-label={`${count} open`}>{count}</span>}
        </NavLink>
      </Tooltip>
    </li>
  );
}

const MORE_KEY = "ud-nav-more";

/** Role-based sidebar: a short primary list for daily work, everything else permitted under "All tools". */
function SidebarNav({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const { can, membership } = useAuth();
  const { pathname } = useLocation();
  const allowed = (it: NavItem) => (!it.perm || can(it.perm)) && (!it.any || it.any.some((p) => can(p))) && (!it.providerOnly || !!membership?.provider_id);
  const primary = primaryNav(profileFor(membership?.roles)).filter(allowed);
  const primaryPaths = new Set(primary.map((p) => p.to));
  const rest = NAV.map((sec) => ({ ...sec, items: sec.items.filter((it) => allowed(it) && !primaryPaths.has(it.to)) })).filter((sec) => sec.items.length);
  const restActive = rest.some((sec) => sec.items.some((it) => it.to !== "/" && pathname.startsWith(it.to)));
  const [open, setOpen] = React.useState<boolean>(() => { try { return localStorage.getItem(MORE_KEY) === "1"; } catch { return false; } });
  const showMore = open || restActive;
  const toggle = () => { const v = !showMore; setOpen(v); try { localStorage.setItem(MORE_KEY, v ? "1" : "0"); } catch { /* ignore */ } };
  // Open-work count from the Home query cache (no extra request from the shell).
  const home = useQuery<{ counts?: Record<string, number> }>({ queryKey: ["home"], queryFn: () => get("/home"), enabled: false });
  const c = home.data?.counts;
  const workCount = c ? (c.cases ?? 0) + (c.tasks ?? 0) + (c.approvals ?? 0) + (c.critical_results ?? 0) : undefined;
  return (
    <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-2 scrollbar-thin" aria-label="Main">
      <ul className="space-y-0.5">{primary.map((it) => <SidebarLink key={it.to} it={it} collapsed={collapsed} onNavigate={onNavigate} count={it.to === "/worklist" ? workCount : undefined} />)}</ul>
      {!!rest.length && (
        <div>
          <button type="button" onClick={toggle} aria-expanded={showMore} aria-controls="nav-all-tools"
            className={cn("flex h-8 w-full items-center gap-2 rounded-md px-2.5 text-label font-medium text-sidebar-muted hover:bg-sidebar-accent hover:text-heading focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50", collapsed && "justify-center px-0")}>
            {collapsed ? <MoreHorizontal className="size-4" /> : <>All tools<ChevronDown className={cn("ml-auto size-3.5 transition-transform", showMore && "rotate-180")} /></>}
          </button>
          {showMore && (
            <div id="nav-all-tools" className="mt-1 space-y-4">
              {rest.map((section, i) => (
                <div key={i}>
                  {section.title && !collapsed && <p className="mb-1 px-2.5 text-label font-medium text-sidebar-muted">{section.title}</p>}
                  <ul className="space-y-0.5">{section.items.map((it) => <SidebarLink key={it.to} it={it} collapsed={collapsed} onNavigate={onNavigate} />)}</ul>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </nav>
  );
}

/** Facility context — always visible in the top bar: organization · location. */
function OrgSwitcher() {
  const { me, membership, clinic, switchOrg, switchClinic } = useAuth();
  if (!membership) return null;
  const multiOrg = (me?.memberships.length ?? 0) > 1;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex h-9 min-w-0 max-w-24 items-center gap-1.5 rounded-md border border-control bg-card px-2 text-left sm:max-w-[22rem] sm:gap-2 sm:px-2.5 text-table text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
          aria-label="Switch organization or clinic">
          <Building2 className="size-4 shrink-0" />
          <span className="min-w-0 truncate"><span className="font-semibold text-heading">{membership.organization_name}</span><span className="hidden md:inline"> · {clinic?.name ?? "All locations"}</span></span>
          <ChevronsUpDown className="size-3.5 shrink-0" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        {multiOrg && (
          <>
            <DropdownMenuLabel>Organization</DropdownMenuLabel>
            {me!.memberships.map((m) => (
              <DropdownMenuItem key={m.organization_id} onSelect={() => switchOrg(m.organization_id)}>
                <span className="flex-1 truncate">{m.organization_name}</span>
                {m.organization_id === membership.organization_id && <Check className="!text-primary" />}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
          </>
        )}
        <DropdownMenuLabel>Location</DropdownMenuLabel>
        {membership.clinics.map((c) => (
          <DropdownMenuItem key={c.id} onSelect={() => switchClinic(c.id)}>
            <span className="flex-1 truncate">{c.name}</span>
            <span className="text-xs text-muted-foreground">{c.code}</span>
            {c.id === clinic?.id && <Check className="!text-primary" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function Notifications() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => get<{ unread: number; items: { id: string; title: string; body: string | null; link: string | null; read_at: string | null; created_at: string }[] }>("/notifications"),
    refetchInterval: 30_000,
  });
  const markAll = async () => { await post("/notifications/read", []); qc.invalidateQueries({ queryKey: ["notifications"] }); };
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Notifications${data?.unread ? `, ${data.unread} unread` : ""}`} className="relative">
          <Bell />
          {!!data?.unread && (
            <span className="absolute right-0.5 top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-destructive px-1 text-label font-semibold leading-none tabular text-on-status">
              {data.unread > 9 ? "9+" : data.unread}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[22rem] p-0">
        <div className="flex items-center justify-between border-b px-4 py-2.5">
          <p className="text-sm font-semibold">Notifications</p>
          <Button variant="link" size="xs" onClick={markAll} disabled={!data?.unread}>Mark all read</Button>
        </div>
        <ul className="max-h-96 overflow-y-auto">
          {!data?.items.length && <li className="px-4 py-8 text-center text-table text-muted-foreground">You're all caught up.</li>}
          {data?.items.map((n) => (
            <li key={n.id}>
              <button
                className="flex w-full gap-3 border-b px-4 py-3 text-left last:border-0 hover:bg-muted/60"
                onClick={async () => {
                  if (!n.read_at) { await post("/notifications/read", [n.id]); qc.invalidateQueries({ queryKey: ["notifications"] }); }
                  if (n.link) navigate(n.link);
                }}
              >
                <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read_at ? "bg-transparent" : "bg-primary")} />
                <span className="min-w-0">
                  <span className="block text-table font-medium">{n.title}</span>
                  {n.body && <span className="block truncate text-xs text-muted-foreground">{n.body}</span>}
                  <span className="mt-0.5 block text-label text-muted-foreground">{fromNow(n.created_at)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}

// ---------- Density (Comfortable / Compact) ----------
type Density = "comfortable" | "compact";
function useDensity() {
  const [d, setD] = React.useState<Density>(() => { try { return localStorage.getItem("ud-density") === "compact" ? "compact" : "comfortable"; } catch { return "comfortable"; } });
  React.useEffect(() => {
    if (d === "compact") document.documentElement.dataset.density = "compact"; else delete document.documentElement.dataset.density;
    try { if (d === "compact") localStorage.setItem("ud-density", "compact"); else localStorage.removeItem("ud-density"); } catch { /* ignore */ }
  }, [d]);
  return [d, setD] as const;
}

function UserMenu() {
  const { me, membership, logout } = useAuth();
  const [theme, setTheme] = useTheme();
  const [density, setDensity] = useDensity();
  const navigate = useNavigate();
  if (!me) return null;
  const name = `${me.user.first_name} ${me.user.last_name}`;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex items-center gap-2 rounded-full p-0.5 pr-2 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50" aria-label="Account menu">
          <Avatar name={name} className="size-8" />
          <span className="hidden whitespace-nowrap text-left leading-tight 2xl:block">
            <span className="block text-table font-medium">{name}{me.user.title ? `, ${me.user.title}` : ""}</span>
            <span className="block text-label text-muted-foreground">{membership?.roles.map((r) => ROLE_LABELS[r]).join(" · ")}</span>
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-60">
        <DropdownMenuLabel className="font-normal">
          <span className="block text-body font-medium text-foreground">{name}</span>
          <span className="block truncate">{me.user.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate("/account")}><UserRound />Account & security</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate("/help")}><LifeBuoy />Help & About</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate("/about")}><Info />Legal notices</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        {([["light", Sun, "Light"], ["dark", Moon, "Dark"], ["system", Monitor, "System"]] as const).map(([t, Icon, label]) => (
          <DropdownMenuItem key={t} onSelect={(e) => { e.preventDefault(); setTheme(t); }}>
            <Icon />{label}{theme === t && <Check className="ml-auto !text-primary" />}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Density</DropdownMenuLabel>
        {([["comfortable", Rows3, "Comfortable"], ["compact", Rows4, "Compact"]] as const).map(([v, Icon, label]) => (
          <DropdownMenuItem key={v} onSelect={(e) => { e.preventDefault(); setDensity(v); }}>
            <Icon />{label}{density === v && <Check className="ml-auto !text-primary" />}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => logout()}><LogOut />Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Breadcrumbs({ labels }: { labels: Record<string, string> }) {
  const matches = useMatches() as { pathname: string; handle?: { crumb?: string } }[];
  const crumbs = matches
    .filter((m) => m.handle?.crumb || labels[m.pathname])
    .map((m) => ({ path: m.pathname, label: labels[m.pathname] ?? m.handle!.crumb! }));
  // Top-level pages already show their title; breadcrumbs only help one level down (e.g. Patients › name). "Home" is implied.
  if (crumbs.length < 3) return null;
  crumbs.shift();
  return (
    <nav aria-label="Breadcrumb" className="hidden min-w-0 shrink items-center gap-1 whitespace-nowrap text-table xl:flex">
      {crumbs.map((c, i) => (
        <React.Fragment key={c.path}>
          {i > 0 && <ChevronRight className="size-3.5 text-muted-foreground/60" />}
          {i < crumbs.length - 1 ? (
            <Link to={c.path} className="truncate text-muted-foreground hover:text-foreground">{c.label}</Link>
          ) : (
            <span className="truncate font-medium" aria-current="page">{c.label}</span>
          )}
        </React.Fragment>
      ))}
    </nav>
  );
}

export function AppShell() {
  const [collapsed, setCollapsed] = React.useState(() => {
    try { return localStorage.getItem("ud-sidebar") === "1"; } catch { return false; }
  });
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [labels, setLabels] = React.useState<Record<string, string>>({});
  const { membership } = useAuth();
  const org = useQuery({ queryKey: ["organization", membership?.organization_id], queryFn: () => get<{ settings: { synthetic_data?: boolean } }>("/organization"), enabled: !!membership, staleTime: 300_000 });
  const synthetic = !!org.data?.settings.synthetic_data;
  useLiveConnection(membership?.organization_id);
  const setCrumb = React.useCallback((path: string, label: string | null) => {
    setLabels((l) => {
      const n = { ...l };
      if (label) n[path] = label; else delete n[path];
      return n;
    });
  }, []);

  React.useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const typing = /input|textarea|select/i.test(target.tagName) || target.isContentEditable;
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing)) {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const toggle = () => {
    setCollapsed((c) => {
      try { localStorage.setItem("ud-sidebar", c ? "0" : "1"); } catch { /* ignore */ }
      return !c;
    });
  };

  return (
    <CrumbCtx.Provider value={{ set: setCrumb, labels }}>
      <div className="flex min-h-dvh">
        <aside className={cn("sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200 lg:flex", collapsed ? "w-[64px]" : "w-[232px]")}>
          <div className={cn("flex h-14 items-center px-4", collapsed && "justify-center px-0")}><Brand collapsed={collapsed} /></div>
          <SidebarNav collapsed={collapsed} />
          <div className="border-t border-sidebar-border p-3">
            <button onClick={toggle} className={cn("flex h-8 w-full items-center gap-2 rounded-md px-2.5 text-table text-sidebar-muted hover:bg-sidebar-accent hover:text-heading", collapsed && "justify-center px-0")}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
              <ChevronsLeft className={cn("size-4 transition-transform", collapsed && "rotate-180")} />
              {!collapsed && "Collapse"}
            </button>
            {!collapsed && <LegalFooter stacked className="px-2.5 pb-0 pt-2" />}
          </div>
        </aside>

        <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetContent side="left" className="w-72 max-w-[85vw] border-0 bg-sidebar" aria-describedby={undefined}>
            <div className="flex h-14 items-center px-4"><Brand /></div>
            <SidebarNav collapsed={false} onNavigate={() => setMobileOpen(false)} />
            <LegalFooter stacked className="border-t px-4" />
          </SheetContent>
        </Dialog>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-card px-3 sm:gap-3 sm:px-6">
            <Button variant="ghost" size="icon" className="shrink-0 lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu /></Button>
            <span className="hidden sm:inline lg:hidden"><Brand collapsed /></span>
            <OrgSwitcher />
            <WorkspaceSwitcher />
            <Breadcrumbs labels={labels} />
            <div className="ml-auto flex min-w-0 items-center gap-1.5 sm:gap-2">
              {membership?.permissions.includes("patients:read") && (
                <button onClick={() => setSearchOpen(true)}
                  className="flex h-9 items-center gap-2 rounded-md border border-control bg-subtle px-3 text-table text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 md:w-64 xl:w-96"
                  aria-label="Search patients">
                  <Search className="size-4" />
                  <span className="hidden flex-1 truncate text-left md:inline">Search patients by name, MRN or DOB</span>
                  <span className="hidden md:inline"><Kbd>⌘K</Kbd></span>
                </button>
              )}
              {synthetic && (
                <Tooltip content="This environment contains only fictional, synthetic records. Do not enter real patient information.">
                  <span className="hidden shrink-0 items-center gap-1 whitespace-nowrap rounded-full border border-dashed border-warning/50 bg-warning-soft px-2 py-0.5 text-label font-medium text-warning-foreground md:inline-flex">
                    <FlaskConical className="size-3" />Synthetic data
                  </span>
                </Tooltip>
              )}
              <Notifications />
              <UserMenu />
            </div>
          </header>
          <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-5 sm:px-6 lg:py-6 min-[1600px]:px-8">
            <React.Suspense fallback={<div className="space-y-3" aria-busy="true"><Skeleton className="h-8 w-56" /><Skeleton className="h-64 w-full rounded-lg" /></div>}>
              <Outlet />
            </React.Suspense>
          </main>
        </div>
      </div>
      <CommandSearch open={searchOpen} onOpenChange={setSearchOpen} />
    </CrumbCtx.Provider>
  );
}
