import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLiveConnection } from "@/lib/live";
import {
  Bell, Building, Check, ChevronRight, ChevronsLeft, ChevronsUpDown, FlaskConical, LogOut, Menu, Monitor, Moon, Search, Sun, UserRound,
} from "lucide-react";
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
import { NAV } from "./nav";

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
    <Link to="/" className="flex items-center gap-2.5 px-1">
      <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 shadow-lg shadow-blue-900/30">
        <svg viewBox="0 0 32 32" className="size-5" aria-hidden><path d="M10 9v8a6 6 0 0 0 12 0V9" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" /><circle cx="16" cy="24.5" r="1.8" fill="#bfdbfe" /></svg>
      </span>
      {!collapsed && <span className="text-[15px] font-semibold tracking-tight text-white">Undeclared</span>}
    </Link>
  );
}

function SidebarNav({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const { can, membership } = useAuth();
  return (
    <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-2 scrollbar-thin" aria-label="Main">
      {NAV.map((section, i) => {
        const items = section.items.filter((it) => (!it.perm || can(it.perm)) && (!it.any || it.any.some((p) => can(p))) && (!it.providerOnly || membership?.provider_id));
        if (!items.length) return null;
        return (
          <div key={i}>
            {section.title && !collapsed && (
              <p className="mb-1.5 px-2.5 text-[11px] font-semibold uppercase tracking-wider text-sidebar-muted">{section.title}</p>
            )}
            <ul className="space-y-0.5">
              {items.map((it) => (
                <li key={it.to}>
                  <Tooltip content={collapsed ? it.label : null} side="right">
                    <NavLink
                      to={it.to}
                      end={it.to === "/"}
                      onClick={onNavigate}
                      className={({ isActive }) => cn(
                        "group flex h-9 items-center gap-3 rounded-lg px-2.5 text-[13.5px] font-medium text-sidebar-foreground transition-colors hover:bg-sidebar-accent hover:text-white",
                        isActive && "bg-sidebar-active text-white shadow-inner",
                        collapsed && "justify-center px-0",
                      )}
                    >
                      <it.icon className="size-[18px] shrink-0 opacity-90" />
                      {!collapsed && <span className="truncate">{it.label}</span>}
                    </NavLink>
                  </Tooltip>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

function OrgSwitcher({ collapsed }: { collapsed: boolean }) {
  const { me, membership, clinic, switchOrg, switchClinic } = useAuth();
  if (!membership) return null;
  const multiOrg = (me?.memberships.length ?? 0) > 1;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className={cn("mx-3 mb-2 flex items-center gap-2.5 rounded-lg border border-sidebar-border bg-sidebar-accent/60 p-2 text-left text-sidebar-foreground hover:bg-sidebar-accent", collapsed && "justify-center")}
          aria-label="Switch organization or clinic">
          <Building className="size-4 shrink-0 text-sidebar-muted" />
          {!collapsed && (
            <>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px] font-semibold text-white">{membership.organization_name}</span>
                <span className="block truncate text-[11.5px] text-sidebar-muted">{clinic?.name ?? "All locations"}</span>
              </span>
              <ChevronsUpDown className="size-3.5 text-sidebar-muted" />
            </>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="right" className="w-64">
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
            <span className="absolute right-1.5 top-1.5 grid min-w-4 place-items-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-4 text-white">
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
          {!data?.items.length && <li className="px-4 py-8 text-center text-[13px] text-muted-foreground">You're all caught up.</li>}
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
                  <span className="block text-[13px] font-medium">{n.title}</span>
                  {n.body && <span className="block truncate text-xs text-muted-foreground">{n.body}</span>}
                  <span className="mt-0.5 block text-[11px] text-muted-foreground">{fromNow(n.created_at)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}

function UserMenu() {
  const { me, membership, logout } = useAuth();
  const [theme, setTheme] = useTheme();
  const navigate = useNavigate();
  if (!me) return null;
  const name = `${me.user.first_name} ${me.user.last_name}`;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex items-center gap-2 rounded-full p-0.5 pr-2 hover:bg-muted" aria-label="Account menu">
          <Avatar name={name} className="size-8" />
          <span className="hidden text-left leading-tight md:block">
            <span className="block text-[13px] font-medium">{name}{me.user.title ? `, ${me.user.title}` : ""}</span>
            <span className="block text-[11.5px] text-muted-foreground">{membership?.roles.map((r) => ROLE_LABELS[r]).join(" · ")}</span>
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-60">
        <DropdownMenuLabel className="font-normal">
          <span className="block text-sm font-medium text-foreground">{name}</span>
          <span className="block truncate">{me.user.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate("/account")}><UserRound />Account & security</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        {([["light", Sun, "Light"], ["dark", Moon, "Dark"], ["system", Monitor, "System"]] as const).map(([t, Icon, label]) => (
          <DropdownMenuItem key={t} onSelect={(e) => { e.preventDefault(); setTheme(t); }}>
            <Icon />{label}{theme === t && <Check className="ml-auto !text-primary" />}
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
  if (!crumbs.length) return null;
  return (
    <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1 text-[13px] sm:flex">
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
        <aside className={cn("sticky top-0 hidden h-dvh shrink-0 flex-col bg-sidebar transition-[width] duration-200 lg:flex", collapsed ? "w-[68px]" : "w-60")}>
          <div className={cn("flex h-14 items-center px-4", collapsed && "justify-center px-0")}><Brand collapsed={collapsed} /></div>
          <OrgSwitcher collapsed={collapsed} />
          <SidebarNav collapsed={collapsed} />
          <div className="border-t border-sidebar-border p-3">
            <button onClick={toggle} className={cn("flex h-8 w-full items-center gap-2 rounded-md px-2.5 text-[12.5px] text-sidebar-muted hover:bg-sidebar-accent hover:text-white", collapsed && "justify-center px-0")}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
              <ChevronsLeft className={cn("size-4 transition-transform", collapsed && "rotate-180")} />
              {!collapsed && "Collapse"}
            </button>
          </div>
        </aside>

        <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetContent side="left" className="w-72 max-w-[85vw] border-0 bg-sidebar" aria-describedby={undefined}>
            <div className="flex h-14 items-center px-4"><Brand /></div>
            <OrgSwitcher collapsed={false} />
            <SidebarNav collapsed={false} onNavigate={() => setMobileOpen(false)} />
          </SheetContent>
        </Dialog>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-background/85 px-4 backdrop-blur-md sm:px-6">
            <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu /></Button>
            <Breadcrumbs labels={labels} />
            <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
              {synthetic && (
                <Tooltip content="This environment contains only fictional, synthetic records. Do not enter real patient information.">
                  <span className="hidden items-center gap-1 rounded-full border border-warning/30 bg-warning-soft px-2 py-0.5 text-[11px] font-medium text-[color-mix(in_oklch,var(--warning)_70%,var(--foreground))] md:inline-flex">
                    <FlaskConical className="size-3" />Synthetic data
                  </span>
                </Tooltip>
              )}
              {membership?.permissions.includes("patients:read") && (
                <button onClick={() => setSearchOpen(true)}
                  className="flex h-9 items-center gap-2 rounded-lg border bg-card px-3 text-[13px] text-muted-foreground shadow-xs hover:bg-muted sm:w-64"
                  aria-label="Search patients">
                  <Search className="size-4" />
                  <span className="hidden flex-1 text-left sm:inline">Search patients…</span>
                  <span className="hidden sm:inline"><Kbd>⌘K</Kbd></span>
                </button>
              )}
              <Notifications />
              <UserMenu />
            </div>
          </header>
          <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-5 sm:px-6 lg:py-6">
            <React.Suspense fallback={<div className="space-y-3" aria-busy="true"><Skeleton className="h-8 w-56" /><Skeleton className="h-64 w-full rounded-xl" /></div>}>
              <Outlet />
            </React.Suspense>
          </main>
        </div>
      </div>
      <CommandSearch open={searchOpen} onOpenChange={setSearchOpen} />
    </CrumbCtx.Provider>
  );
}
