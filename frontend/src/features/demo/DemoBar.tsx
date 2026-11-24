import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck, FlaskConical, RotateCcw, UserRoundCog } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toastError } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/input";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

/** The visitor's private demo hospital (GET /auth/demo/session). */
type DemoInfo = {
  hospital: string; tag: string; expires_at: string; idle_hours: number; role_key: string | null; role_label: string | null;
  roles: { key: string; role: string; label: string }[];
  people: { user_id: string; name: string; title: string | null; roles: string[]; role_key: string | null }[];
};
type Tokens = Parameters<ReturnType<typeof useAuth>["acceptTokens"]>[0];

export function useDemoHospital() {
  const { me } = useAuth();
  return useQuery({
    queryKey: ["demo", "session", me?.user.id], queryFn: () => get<DemoInfo>("/auth/demo/session"),
    enabled: !!me?.demo_hospital, staleTime: 60_000, refetchInterval: 5 * 60_000,
  });
}

function endsIn(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "ending now";
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  return h ? `${h} h ${m} min` : `${m} min`;
}

/** Switching identity replaces the session: clear every cached query so nothing from the previous role is shown. */
function useEnter() {
  const { acceptTokens } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  return React.useCallback((data: Tokens, to = "/") => {
    qc.clear();
    acceptTokens(data);
    navigate(data.me.memberships[0]?.roles.includes("patient") ? "/portal" : to, { replace: true });
  }, [acceptTokens, navigate, qc]);
}

/** Slim bar shown only to identities of a private demo hospital: who you are, switch role, guide, reset, expiry. */
export function DemoBar({ className }: { className?: string }) {
  const { me } = useAuth();
  const q = useDemoHospital();
  const enter = useEnter();
  const [busy, setBusy] = React.useState(false);
  const [resetOpen, setResetOpen] = React.useState(false);
  const [guideOpen, setGuideOpen] = React.useState(false);
  const [, tick] = React.useState(0);
  React.useEffect(() => { const id = setInterval(() => tick((n) => n + 1), 60_000); return () => clearInterval(id); }, []);
  const d = q.data;
  if (!d) return null;

  const switchTo = async (value: string) => {
    if (!value) return;
    setBusy(true);
    try {
      const body = value.startsWith("user:") ? { user_id: value.slice(5) } : { key: value };
      enter(await post<Tokens>("/auth/demo/switch", body));
    } catch (e) {
      toastError(e, "Couldn't switch role");
    } finally {
      setBusy(false);
    }
  };
  const others = d.people.filter((p) => !p.role_key);

  return (
    <div role="region" aria-label="Demo hospital" data-testid="demo-bar"
      className={cn("flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-dashed border-warning/50 bg-warning-soft/60 px-4 py-2 text-table sm:px-6", className)}>
      <span className="flex items-center gap-1.5 font-medium text-warning-foreground"><FlaskConical className="size-4" />Your private demo hospital</span>
      <span className="hidden text-muted-foreground md:inline">Synthetic data · only you can see it</span>
      <label className="flex items-center gap-1.5">
        <UserRoundCog className="size-4 text-muted-foreground" aria-hidden />
        <span className="sr-only">Switch role</span>
        <NativeSelect aria-label="Switch role" data-testid="demo-role-switch" className="h-8 w-auto min-w-44 max-w-64 py-0 text-table" disabled={busy}
          value={d.role_key ?? `user:${me?.user.id}`} onChange={(e) => switchTo(e.target.value)}>
          <optgroup label="Roles">
            {d.roles.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          </optgroup>
          {others.length > 0 && (
            <optgroup label="Other staff in this hospital">
              {others.map((p) => <option key={p.user_id} value={`user:${p.user_id}`}>{p.name}{p.roles.length ? ` · ${p.roles.join(", ")}` : ""}</option>)}
            </optgroup>
          )}
        </NativeSelect>
      </label>
      <span className="text-muted-foreground" data-testid="demo-expiry" title={`Ends after ${d.idle_hours} hours without activity, or 24 hours after it started.`}>
        Ends in {endsIn(d.expires_at)}
      </span>
      <span className="ml-auto flex items-center gap-1.5">
        <Button size="sm" variant="ghost" onClick={() => setGuideOpen(true)}><ClipboardCheck />Guided demo</Button>
        <Button size="sm" variant="outline" onClick={() => setResetOpen(true)} data-testid="demo-reset"><RotateCcw />Reset my hospital</Button>
      </span>
      <ResetDialog open={resetOpen} onOpenChange={setResetOpen} onDone={enter} />
      <GuideDialog open={guideOpen} onOpenChange={setGuideOpen} tag={d.tag} onSwitch={(k) => { setGuideOpen(false); switchTo(k); }} />
    </div>
  );
}

function ResetDialog({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: (d: Tokens) => void }) {
  const [busy, setBusy] = React.useState(false);
  const go = async () => {
    setBusy(true);
    try {
      onDone(await post<Tokens>("/auth/demo/reset", { confirm: "RESET" }));
      onOpenChange(false);
    } catch (e) {
      toastError(e, "Couldn't reset your demo hospital");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Reset your demo hospital?</DialogTitle>
          <DialogDescription>
            Everything you created or changed in this demo hospital is deleted and you get a fresh one with the original synthetic
            data. Only your hospital is affected. This can't be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button variant="destructive" onClick={go} loading={busy} data-testid="demo-reset-confirm">Reset my hospital</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** A short checklist of end-to-end workflows; each step names the role to switch to. Progress is kept in this browser. */
const GUIDE: { title: string; steps: [string, string][] }[] = [
  { title: "A · Patient visit, lab and claim", steps: [
    ["front_desk", "Register a patient, book a visit for today, check in and room them (Front desk)"],
    ["nurse", "Record vitals on the patient's chart"],
    ["doctor", "Open the chart, start the visit, write the note and order a lipid panel"],
    ["lab_tech", "Collect, receive and enter the results (Laboratory)"],
    ["super_admin", "Verify the results as a second person (or switch to Marcus Bell)"],
    ["doctor", "Review the results, sign the note, add a diagnosis and complete the visit"],
    ["billing", "Capture charges, create the claim and submit it (simulated clearinghouse)"],
  ] },
  { title: "B · Pharmacy shortage", steps: [
    ["pharmacist", "Open My work: the low-stock case and its purchase request"],
    ["hospital_admin", "Approve the purchase request in My work"],
    ["pharmacist", "Place the (simulated) order and receive the stock"],
    ["super_admin", "Run the low-stock monitor in Monitors & rules — the case verifies and closes"],
  ] },
  { title: "C · Insurance follow-up", steps: [
    ["insurance_specialist", "Open Elena Moreau's coverage case; ask Insurance Guardian for help"],
    ["insurance_specialist", "Approve or reject any AI proposal in My work"],
    ["patient", "Upload an insurance card in the portal"],
    ["insurance_specialist", "Confirm the card — the payer re-check closes the case"],
  ] },
  { title: "D · Emergency to discharge", steps: [
    ["nurse", "Register an arrival on the Emergency board, triage and room them"],
    ["doctor", "Assign yourself and decide to admit"],
    ["bed_manager", "Assign an inpatient bed on the Bed board"],
    ["nurse", "Write a handoff; then complete discharge tasks"],
    ["doctor", "Order discharge, sign the discharge summary and approve instructions"],
  ] },
  { title: "E · Hospital administration", steps: [
    ["super_admin", "Edit a facility, add a staff member, change a monitor's settings"],
    ["super_admin", "Review the Command Center and assign a case"],
    ["hospital_admin", "Complete the task in My work"],
  ] },
];

function GuideDialog({ open, onOpenChange, tag, onSwitch }: { open: boolean; onOpenChange: (o: boolean) => void; tag: string; onSwitch: (k: string) => void }) {
  const key = `ud-demo-guide-${tag}`;
  const [done, setDone] = React.useState<Record<string, boolean>>(() => {
    try { return JSON.parse(localStorage.getItem(key) || "{}"); } catch { return {}; }
  });
  const toggle = (id: string) => setDone((d) => {
    const n = { ...d, [id]: !d[id] };
    try { localStorage.setItem(key, JSON.stringify(n)); } catch { /* ignore */ }
    return n;
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>Guided demo</DialogTitle>
          <DialogDescription>Each workflow runs on your hospital's real records. Use "Switch" to become the role a step needs.</DialogDescription>
        </DialogHeader>
        <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
          {GUIDE.map((g) => (
            <section key={g.title}>
              <h3 className="mb-1.5 text-body font-semibold">{g.title}</h3>
              <ol className="space-y-1">
                {g.steps.map(([role, text], i) => {
                  const id = `${g.title}:${i}`;
                  return (
                    <li key={id} className="flex items-start gap-2 text-table">
                      <input type="checkbox" className="mt-0.5" checked={!!done[id]} onChange={() => toggle(id)} aria-label={`Done: ${text}`} />
                      <span className={cn("flex-1", done[id] && "text-muted-foreground line-through")}>{text}</span>
                      <Button size="sm" variant="ghost" className="h-6 px-2" onClick={() => onSwitch(role)}>Switch</Button>
                    </li>
                  );
                })}
              </ol>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
