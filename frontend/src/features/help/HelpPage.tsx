import {
  ArrowRight, BookOpen, ChevronDown, CircleHelp, Compass, ExternalLink, Info, LifeBuoy, Lock, Search, ShieldAlert, Sparkles, UsersRound, X,
} from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";
import { COPYRIGHT_NOTICE, PRODUCT_DESCRIPTION } from "@/lib/legal";
import type { Role } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  ABOUT_MODULES, type Access, AI_TOPICS, FAQS, type HelpLink, JOURNEY, MODULES, type Module, PATIENT_TOPICS, ROLE_GUIDES, SECTION_ICONS,
} from "./content";

const VERSION = import.meta.env.VITE_APP_VERSION ?? "development";
const ADMIN_ROLES: Role[] = ["super_admin", "hospital_admin", "clinic_admin"];

function useAccess() {
  const { can } = useAuth();
  return React.useCallback((a?: Access) => !a || ((!a.perm || can(a.perm)) && (!a.any || a.any.some((p) => can(p)))), [can]);
}

// ---------------------------------------------------------------------------------------------- shared building blocks

function Steps({ steps }: { steps: string[] }) {
  return (
    <ol className="space-y-2">
      {steps.map((s, i) => (
        <li key={i} className="flex gap-3 text-body leading-relaxed">
          <span className="grid size-5 shrink-0 place-items-center rounded-full bg-primary/10 text-label font-semibold text-primary tabular" aria-hidden>{i + 1}</span>
          <span>{s}</span>
        </li>
      ))}
    </ol>
  );
}

function LinkChips({ links }: { links: HelpLink[] }) {
  const ok = useAccess();
  const mine = links.filter((l) => ok(l));
  if (!mine.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {mine.map((l) => (
        <Button key={l.to} size="xs" variant="outline" asChild><Link to={l.to}>{l.label}<ArrowRight /></Link></Button>
      ))}
    </div>
  );
}

/** Accessible accordion item (native <details>): keyboard and screen-reader friendly, controllable for search jumps. */
function Disclosure({ id, title, icon: Icon, meta, open, onToggle, children }: {
  id: string; title: React.ReactNode; icon?: React.ElementType; meta?: React.ReactNode; open: boolean; onToggle: (open: boolean) => void; children: React.ReactNode;
}) {
  return (
    <details id={`help-${id}`} open={open} onToggle={(e) => onToggle((e.currentTarget as HTMLDetailsElement).open)}
      className="group scroll-mt-24 rounded-xl border bg-card transition-colors open:shadow-sm">
      <summary className="flex cursor-pointer list-none items-center gap-3 rounded-xl px-4 py-3 outline-none hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring/50 [&::-webkit-details-marker]:hidden">
        {Icon && <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><Icon className="size-4" /></span>}
        <span className="min-w-0 flex-1 text-body font-medium">{title}</span>
        {meta}
        <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <div className="space-y-3 border-t px-4 py-4">{children}</div>
    </details>
  );
}

function useOpenSet() {
  const [open, setOpen] = React.useState<Set<string>>(new Set());
  const toggle = React.useCallback((id: string, v: boolean) => setOpen((s) => {
    if (s.has(id) === v) return s;
    const n = new Set(s);
    if (v) n.add(id); else n.delete(id);
    return n;
  }), []);
  return [open, toggle, setOpen] as const;
}

type SearchItem = { key: string; section: string; target: string; kind: string; title: string; text: string };

function match(items: SearchItem[], q: string) {
  const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  return items
    .map((it) => {
      const hay = `${it.title} ${it.text}`.toLowerCase();
      if (!terms.every((t) => hay.includes(t))) return null;
      const score = terms.reduce((n, t) => n + (it.title.toLowerCase().includes(t) ? 3 : 1), 0);
      const i = hay.indexOf(terms[0]);
      const snippet = it.text ? `${i > 40 ? "…" : ""}${`${it.title} ${it.text}`.slice(Math.max(0, i - 40), i + 120)}…` : "";
      return { ...it, score, snippet };
    })
    .filter((x): x is SearchItem & { score: number; snippet: string } => !!x)
    .sort((a, b) => b.score - a.score)
    .slice(0, 12);
}

function SearchBox({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <div className="relative w-full max-w-xl">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label="Search help" className="h-10 pl-9 pr-9" type="search" />
      {value && <button type="button" onClick={() => onChange("")} aria-label="Clear search" className="absolute right-2 top-1/2 grid size-6 -translate-y-1/2 place-items-center rounded text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50"><X className="size-4" /></button>}
    </div>
  );
}

function SearchResults({ results, onPick }: { results: ReturnType<typeof match>; onPick: (r: SearchItem) => void }) {
  return (
    <Card data-testid="help-search-results">
      <CardContent className="p-2">
        {!results.length ? <p className="p-4 text-body text-muted-foreground">No help topics match. Try a simpler word such as “bed”, “insurance” or “results”.</p> : (
          <ul className="divide-y" aria-label="Search results">
            {results.map((r) => (
              <li key={r.key}>
                <button type="button" onClick={() => onPick(r)} className="flex w-full flex-col items-start gap-0.5 rounded-lg px-3 py-2.5 text-left hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring/50">
                  <span className="flex items-center gap-2 text-body font-medium">{r.title}<Badge variant="neutral">{r.kind}</Badge></span>
                  {r.snippet && <span className="line-clamp-2 text-table text-muted-foreground">{r.snippet}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function Journey({ onOpen }: { onOpen?: (module: string) => void }) {
  return (
    <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-label="Patient journey" data-testid="help-journey">
      {JOURNEY.map((s, i) => (
        <li key={s.id} className="relative flex gap-3 rounded-xl border bg-card p-3.5">
          <div className="flex flex-col items-center">
            <span className="grid size-9 place-items-center rounded-full bg-primary/10 text-primary"><s.icon className="size-4" /></span>
            <span className="mt-1 text-label font-semibold text-muted-foreground tabular">{i + 1}</span>
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-body font-medium">{s.title}</p>
            <p className="text-table leading-relaxed text-muted-foreground">{s.text}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <Badge variant="outline"><UsersRound />{s.who}</Badge>
              {onOpen && s.module && <button type="button" onClick={() => onOpen(s.module!)} className="text-label font-medium text-primary hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring/50">How it works</button>}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function AboutCard({ patient }: { patient?: boolean }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2" data-testid="help-about">
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Info className="size-4" />HMS Workflows</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-body leading-relaxed">
          <p>{PRODUCT_DESCRIPTION} that brings patient care, hospital operations and helpful automation into one connected application.</p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
            <dt className="text-muted-foreground">Version</dt><dd className="tabular" data-testid="help-version">{VERSION}</dd>
            <dt className="text-muted-foreground">Status</dt><dd>Demonstration build using synthetic (made-up) patient data</dd>
          </dl>
          {!patient && (
            <>
              <p className="font-medium">Main modules</p>
              <ul className="grid gap-1 sm:grid-cols-2">{ABOUT_MODULES.map((m) => <li key={m} className="flex gap-2"><span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary" />{m}</li>)}</ul>
              <p className="font-medium">How it fits together</p>
              <p className="text-muted-foreground">Everyone works in one web application backed by one shared database, so a change in one department, such as an admission, shows up immediately everywhere it matters (the bed board, the Command Center, billing). Background checks watch for problems and turn them into cases for the right team. Each person only sees what their role allows, and the server checks this again on every request.</p>
            </>
          )}
        </CardContent>
      </Card>
      <div className="space-y-4">
        <Card className="border-warning/40">
          <CardHeader><CardTitle className="flex items-center gap-2"><ShieldAlert className="size-4 text-warning" />Privacy & limitations</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-body leading-relaxed text-muted-foreground">
            <p>This build is for demonstration and testing with synthetic data. It has not been certified for clinical use and should not be described as HIPAA-compliant.</p>
            {patient
              ? <p>Your information is shown only to you and to staff involved in your care. Some features, such as payments and messages to your phone, are simulated in this demo.</p>
              : <p>Access is limited by role, and important actions are recorded in an audit log. Patient data is sent to an external AI service only when the organization allows it. Connections to payers, suppliers, imaging archives, messaging and payments are simulated.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Copyright</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-body">
            <p className="font-medium" data-testid="help-copyright">{COPYRIGHT_NOTICE}</p>
            <p className="text-muted-foreground">Open-source components keep their own licenses. <Link to="/about" className="text-primary underline-offset-2 hover:underline">Legal notices & third-party software<ExternalLink className="ml-0.5 inline size-3" /></Link></p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function SimNote({ text }: { text: string }) {
  return <p className="flex items-start gap-2 rounded-lg bg-warning-soft/50 px-3 py-2 text-table"><Info className="mt-0.5 size-3.5 shrink-0" />{text}</p>;
}

function ModuleBody({ m, allowed }: { m: Module; allowed: boolean }) {
  return (
    <>
      <p className="text-body leading-relaxed">{m.summary}</p>
      {allowed ? (
        <>
          <div className="grid gap-2 text-table sm:grid-cols-2">
            <p><span className="font-medium">Who uses it: </span><span className="text-muted-foreground">{m.who}</span></p>
            <p><span className="font-medium">When: </span><span className="text-muted-foreground">{m.when}</span></p>
          </div>
          <div><p className="mb-2 text-table font-medium">How to use it</p><Steps steps={m.steps} /></div>
          <p className="rounded-lg bg-muted/50 px-3 py-2 text-table"><span className="font-medium">Example: </span>{m.example}</p>
          {m.simulated && <SimNote text={m.simulated} />}
          <LinkChips links={m.links} />
        </>
      ) : (
        <p className="flex items-center gap-2 text-table text-muted-foreground"><Lock className="size-3.5" />This area isn't part of your role. Ask your administrator if you need access for your work.</p>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------------------------- staff page

const SECTIONS = [
  { id: "overview", label: "Overview" }, { id: "start", label: "Getting started" }, { id: "features", label: "Features" },
  { id: "roles", label: "Role guides" }, { id: "ai", label: "AI & automation" }, { id: "faq", label: "FAQ" }, { id: "about", label: "About" },
] as const;
type SectionId = (typeof SECTIONS)[number]["id"];

const START_STEPS: { text: string; link?: HelpLink }[] = [
  { text: "Sign in with your own account. Never share your login." },
  { text: "Check the facility shown at the top of the sidebar and switch it if you work somewhere else today." },
  { text: "Open your Dashboard to see today at a glance.", link: { label: "Dashboard", to: "/" } },
  { text: "Open My work to see cases, tasks and approvals assigned to you, and check the bell for alerts.", link: { label: "My work", to: "/worklist", perm: "cases:read" } },
  { text: "Use the sidebar to open your department. You'll only see the areas your role can use." },
  { text: "Search for a patient with ⌘K (Ctrl+K), if your role allows it.", link: { label: "Patients", to: "/patients", perm: "patients:read" } },
  { text: "Complete your work using the buttons on each screen. Each step is saved and recorded." },
  { text: "Review and approve actions that need your sign-off under My work → Approvals. AI suggestions always need a person's check." },
];

export function HelpPage() {
  const { membership } = useAuth();
  const ok = useAccess();
  const [params, setParams] = useSearchParams();
  const section = (SECTIONS.some((s) => s.id === params.get("section")) ? params.get("section") : "overview") as SectionId;
  const setSection = (s: SectionId) => setParams((p) => { p.set("section", s); return p; }, { replace: true });
  const [q, setQ] = React.useState("");
  const [open, toggle, setOpen] = useOpenSet();
  const [scrollTo, setScrollTo] = React.useState<string | null>(null);
  const roles = (membership?.roles ?? []) as Role[];
  const isAdmin = roles.some((r) => ADMIN_ROLES.includes(r));
  const myGuides = ROLE_GUIDES.filter((g) => g.roles.some((r) => roles.includes(r)));
  const [guideId, setGuideId] = React.useState<string>("");
  const guide = ROLE_GUIDES.find((g) => g.id === guideId) ?? myGuides[0] ?? null;
  const browseable = isAdmin ? ROLE_GUIDES : myGuides;
  const mine = MODULES.filter((m) => ok(m.access));
  const others = MODULES.filter((m) => !ok(m.access));
  const faqs = FAQS.filter((f) => f.audience === "staff");

  React.useEffect(() => {
    if (!scrollTo) return;
    const t = window.setTimeout(() => { document.getElementById(`help-${scrollTo}`)?.scrollIntoView({ behavior: "smooth", block: "start" }); setScrollTo(null); }, 60);
    return () => window.clearTimeout(t);
  }, [scrollTo, section]);

  const goTo = (s: SectionId, target?: string) => {
    setQ("");
    setSection(s);
    if (target) { setOpen((o) => new Set(o).add(target)); setScrollTo(target); }
  };

  const index = React.useMemo<SearchItem[]>(() => [
    ...MODULES.map((m) => ({ key: `m-${m.id}`, section: "features", target: `mod-${m.id}`, kind: "Feature", title: m.title,
      text: ok(m.access) ? `${m.summary} ${m.steps.join(" ")} ${m.example}` : m.summary })),
    ...browseable.flatMap((g) => g.tasks.map((t, i) => ({ key: `g-${g.id}-${i}`, section: "roles", target: `role-${g.id}`, kind: `${g.title} guide`, title: t.title, text: t.steps.join(" ") }))),
    ...AI_TOPICS.map((a) => ({ key: `a-${a.id}`, section: "ai", target: `ai-${a.id}`, kind: "AI", title: a.title, text: a.body.join(" ") })),
    ...faqs.map((f) => ({ key: `f-${f.id}`, section: "faq", target: `faq-${f.id}`, kind: "FAQ", title: f.q, text: f.a })),
    ...JOURNEY.map((j) => ({ key: `j-${j.id}`, section: "overview", target: "journey", kind: "Patient journey", title: j.title, text: j.text })),
    { key: "about", section: "about", target: "about", kind: "About", title: "About HMS Workflows, version and copyright", text: `privacy data version ${COPYRIGHT_NOTICE}` },
  ], [ok, browseable, faqs]);
  const results = React.useMemo(() => match(index, q), [index, q]);

  return (
    <div className="mx-auto max-w-6xl space-y-5" data-testid="help-page">
      <header className="overflow-hidden rounded-2xl border bg-card">
        <div className="space-y-4 bg-gradient-to-br from-primary/10 via-transparent to-transparent p-5 sm:p-7">
          <div className="flex items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground"><LifeBuoy className="size-5" /></span>
            <div>
              <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">Help & About HMS Workflows</h1>
              <p className="mt-1 max-w-2xl text-body leading-relaxed text-muted-foreground">Learn how HMS Workflows connects patient care, hospital operations, and intelligent automation—all in one platform.</p>
            </div>
          </div>
          <SearchBox value={q} onChange={setQ} placeholder="Search help — e.g. “discharge”, “insurance alert”, “approve”" />
        </div>
      </header>

      {q.trim() ? <SearchResults results={results} onPick={(r) => goTo(r.section as SectionId, r.target)} /> : (
        <Tabs value={section} onValueChange={(v) => setSection(v as SectionId)}>
          <div className="-mx-4 overflow-x-auto px-4 scrollbar-thin sm:mx-0 sm:px-0">
            <TabsList aria-label="Help sections" className="w-max">
              {SECTIONS.map((s) => { const Icon = SECTION_ICONS[s.id]; return <TabsTrigger key={s.id} value={s.id}><Icon />{s.label}</TabsTrigger>; })}
            </TabsList>
          </div>

          <TabsContent value="overview" className="space-y-5">
            <Card>
              <CardContent className="space-y-3 p-5 text-body leading-relaxed">
                <p>HMS Workflows is a unified hospital management system that helps hospitals manage patients, appointments, medical records, admissions, nursing, pharmacy, laboratory tests, billing, insurance, and everyday hospital operations in one connected application.</p>
                <p className="text-muted-foreground">Because every department works in the same system, information follows the patient. When a doctor admits someone, the bed manager sees them waiting. When a discharge is ordered, the pharmacy, nursing and front desk each get their part. When something is missed, an automated check raises a case for the right team.</p>
              </CardContent>
            </Card>
            <section id="help-journey" className="scroll-mt-24 space-y-3">
              <h2 className="flex items-center gap-2 text-section font-semibold"><Compass className="size-4 text-primary" />A patient's journey through the hospital</h2>
              <Journey onOpen={(m) => goTo("features", `mod-${m}`)} />
            </section>
          </TabsContent>

          <TabsContent value="start">
            <Card>
              <CardHeader><CardTitle>Getting started</CardTitle></CardHeader>
              <CardContent>
                <ol className="space-y-3" data-testid="help-getting-started">
                  {START_STEPS.map((s, i) => (
                    <li key={i} className="flex flex-wrap items-center gap-3 text-body">
                      <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary text-label font-semibold text-primary-foreground tabular" aria-hidden>{i + 1}</span>
                      <span className="min-w-0 flex-1">{s.text}</span>
                      {s.link && ok(s.link) && <Button size="xs" variant="outline" asChild><Link to={s.link.to}>{s.link.label}<ArrowRight /></Link></Button>}
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="features" className="space-y-3">
            <p className="text-table text-muted-foreground">Areas you can use, with step-by-step instructions. Expand any topic to learn more.</p>
            <div className="space-y-2" data-testid="help-features">
              {mine.map((m) => (
                <Disclosure key={m.id} id={`mod-${m.id}`} title={m.title} icon={m.icon} open={open.has(`mod-${m.id}`)} onToggle={(v) => toggle(`mod-${m.id}`, v)}
                  meta={m.simulated ? <Badge variant="warning" className="hidden sm:inline-flex">Partly simulated</Badge> : undefined}>
                  <ModuleBody m={m} allowed />
                </Disclosure>
              ))}
            </div>
            {!!others.length && (
              <>
                <h2 className="pt-3 text-body font-semibold">Other areas of the hospital</h2>
                <p className="text-table text-muted-foreground">How the rest of the hospital works. These areas aren't part of your role.</p>
                <div className="space-y-2">
                  {others.map((m) => (
                    <Disclosure key={m.id} id={`mod-${m.id}`} title={m.title} icon={m.icon} open={open.has(`mod-${m.id}`)} onToggle={(v) => toggle(`mod-${m.id}`, v)}
                      meta={<Lock className="size-3.5 text-muted-foreground" aria-label="Not part of your role" />}>
                      <ModuleBody m={m} allowed={false} />
                    </Disclosure>
                  ))}
                </div>
              </>
            )}
          </TabsContent>

          <TabsContent value="roles" className="space-y-3">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-section font-semibold">How to use HMS Workflows for your role</h2>
                <p className="text-table text-muted-foreground">{isAdmin ? "As an administrator you can browse every role's guide, for example for training." : "Guides for the roles on your account."}</p>
              </div>
              {browseable.length > 1 && (
                <label className="flex items-center gap-2 text-table">Role
                  <NativeSelect value={guide?.id ?? ""} onChange={(e) => setGuideId(e.target.value)} className="h-8 w-56" aria-label="Choose a role guide">
                    {browseable.map((g) => <option key={g.id} value={g.id}>{g.title}</option>)}
                  </NativeSelect>
                </label>
              )}
            </div>
            {!guide ? <Card><CardContent className="p-5 text-body text-muted-foreground">There's no specific guide for your role yet. Use Getting started and Features.</CardContent></Card> : (
              <Card id={`help-role-${guide.id}`} className="scroll-mt-24" data-testid="help-role-guide">
                <CardHeader><CardTitle className="flex items-center gap-2"><BookOpen className="size-4 text-primary" />{guide.title}</CardTitle><p className="text-table text-muted-foreground">{guide.intro}</p></CardHeader>
                <CardContent className="grid gap-3 md:grid-cols-2">
                  {guide.tasks.map((t) => {
                    const m = MODULES.find((x) => x.id === t.module);
                    return (
                      <div key={t.title} className="space-y-2.5 rounded-xl border p-4">
                        <p className="text-body font-medium">{t.title}</p>
                        <Steps steps={t.steps} />
                        {m && ok(m.access) && (
                          <div className="flex flex-wrap gap-2 pt-1">
                            <LinkChips links={t.link ? [t.link] : m.links.slice(0, 1)} />
                            <Button size="xs" variant="ghost" onClick={() => goTo("features", `mod-${m.id}`)}>Learn more</Button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="ai" className="space-y-3">
            <Card className="border-primary/30 bg-primary/5">
              <CardContent className="flex items-start gap-3 p-4 text-body">
                <Sparkles className="mt-0.5 size-5 shrink-0 text-primary" />
                <p><strong>AI assists hospital staff. It does not replace professional clinical judgment.</strong> AI never diagnoses, prescribes, signs notes or makes clinical decisions on its own. When credentials or outside connections aren't set up, features run in a clearly labeled simulation mode.</p>
              </CardContent>
            </Card>
            <h2 className="text-section font-semibold">Understanding AI in HMS Workflows</h2>
            <div className="space-y-2" data-testid="help-ai">
              {AI_TOPICS.map((a) => (
                <Disclosure key={a.id} id={`ai-${a.id}`} title={a.title} open={open.has(`ai-${a.id}`)} onToggle={(v) => toggle(`ai-${a.id}`, v)}>
                  {a.body.map((p, i) => <p key={i} className="text-body leading-relaxed">{p}</p>)}
                </Disclosure>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="faq" className="space-y-2" data-testid="help-faq">
            {faqs.map((f) => (
              <Disclosure key={f.id} id={`faq-${f.id}`} title={f.q} icon={CircleHelp} open={open.has(`faq-${f.id}`)} onToggle={(v) => toggle(`faq-${f.id}`, v)}>
                <p className="text-body leading-relaxed">{f.a}</p>
                {f.link && <LinkChips links={[f.link]} />}
              </Disclosure>
            ))}
          </TabsContent>

          <TabsContent value="about" id="help-about"><AboutCard /></TabsContent>
        </Tabs>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- patient portal

export function PatientHelp() {
  const [q, setQ] = React.useState("");
  const [open, toggle, setOpen] = useOpenSet();
  const faqs = FAQS.filter((f) => f.audience === "patient");
  const index = React.useMemo<SearchItem[]>(() => [
    ...PATIENT_TOPICS.map((t) => ({ key: `t-${t.id}`, section: "topics", target: `pt-${t.id}`, kind: "How to", title: t.title, text: t.steps.join(" ") })),
    ...faqs.map((f) => ({ key: `f-${f.id}`, section: "faq", target: `pfaq-${f.id}`, kind: "FAQ", title: f.q, text: f.a })),
  ], [faqs]);
  const results = React.useMemo(() => match(index, q), [index, q]);
  const pick = (r: SearchItem) => {
    setQ("");
    setOpen((o) => new Set(o).add(r.target));
    window.setTimeout(() => document.getElementById(`help-${r.target}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  };

  return (
    <div className="space-y-6" data-testid="patient-help">
      <header className="space-y-3 rounded-2xl border bg-card p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground"><LifeBuoy className="size-5" /></span>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Help & About</h1>
            <p className="mt-1 text-body leading-relaxed text-muted-foreground">Your patient portal lets you book visits, message your care team, see your results and visit summaries, update insurance and pay bills, all in one place.</p>
          </div>
        </div>
        <SearchBox value={q} onChange={setQ} placeholder="Search help — e.g. “book”, “insurance”, “video”" />
      </header>

      {q.trim() ? <SearchResults results={results} onPick={pick} /> : null}

      <section className="space-y-3">
        <h2 className="text-section font-semibold">How to…</h2>
        <div className="grid items-start gap-2 md:grid-cols-2" data-testid="patient-help-topics">
          {PATIENT_TOPICS.map((t) => (
            <Disclosure key={t.id} id={`pt-${t.id}`} title={t.title} icon={t.icon} open={open.has(`pt-${t.id}`)} onToggle={(v) => toggle(`pt-${t.id}`, v)}>
              <Steps steps={t.steps} />
              <Button size="xs" variant="outline" asChild><Link to={t.to}>{t.label}<ArrowRight /></Link></Button>
            </Disclosure>
          ))}
        </div>
      </section>

      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Sparkles className="size-4 text-primary" />About AI in your care</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-body leading-relaxed text-muted-foreground">
          <p>Some tools help your care team work faster, for example by drafting visit notes (only with your permission) or reading documents you upload. A member of your care team always reviews this work. AI does not make decisions about your care.</p>
        </CardContent>
      </Card>

      <section className="space-y-2">
        <h2 className="text-section font-semibold">Frequently asked questions</h2>
        {faqs.map((f) => (
          <Disclosure key={f.id} id={`pfaq-${f.id}`} title={f.q} icon={CircleHelp} open={open.has(`pfaq-${f.id}`)} onToggle={(v) => toggle(`pfaq-${f.id}`, v)}>
            <p className="text-body leading-relaxed">{f.a}</p>
            {f.link && <Button size="xs" variant="outline" asChild><Link to={f.link.to}>{f.link.label}<ArrowRight /></Link></Button>}
          </Disclosure>
        ))}
      </section>

      <section className={cn("space-y-3")}>
        <h2 className="text-section font-semibold">About</h2>
        <AboutCard patient />
      </section>
    </div>
  );
}
