import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BadgeCheck, CalendarClock, FileImage, RefreshCw, Search, ShieldCheck, ShieldQuestion, UserX } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { EmptyState, ErrorState, LoadingRows, PageHeader, SimulatedBadge, Stat, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, fromNow } from "@/lib/format";
import { cn, titleCase } from "@/lib/utils";
import { CaseDrawer, CaseRow, type CaseT } from "../ops/ops";
import { AskAI } from "@/features/ai/AskAI";

type Summary = {
  window_days: number; visits: number; ready: number; ready_pct: number | null; states: Record<string, number>;
  open_cases: { kind: string; severity: string; count: number }[]; escalated_open: number; resolved_30d: { code: string; count: number; avg_hours: number }[];
  reminders_7d: Record<string, number>; eligibility_checks_7d: Record<string, number>; requests: { awaiting_patient: number; awaiting_staff_review: number };
  simulated_eligibility: boolean;
};
export type CheckT = { id: string; insurance_id: string; date_of_service: string; result: string; coverage_start: string | null; coverage_end: string | null; plan_description: string | null; source: string; trigger: string; payer_trace: string | null; message: string | null; checked_at: string };
export type RequestT = { id: string; patient_id: string; patient_name: string | null; mrn: string | null; case_id: string | null; reason: string; status: string; document_id: string | null; document_status: string | null; submitted: Record<string, string>; extracted: Record<string, string>; discrepancies: string[]; submitted_at: string | null; review_note: string | null; created_at: string };
type Coverage = { date_of_service: string; next_visit: { id: string; start_at: string; coverage_override: string | null } | null; state: string; reason: string; insurance_id: string | null; simulated: boolean; checks: CheckT[]; open_cases: { id: string; number: number; title: string; severity: string; status: string }[]; requests: RequestT[] };

export const STATE_META: Record<string, { label: string; variant: React.ComponentProps<typeof Badge>["variant"]; icon: React.ElementType }> = {
  verified_active: { label: "Verified active", variant: "success", icon: BadgeCheck },
  cleared_override: { label: "Cleared by staff", variant: "success", icon: ShieldCheck },
  verified_inactive: { label: "Payer: inactive", variant: "danger", icon: AlertTriangle },
  no_coverage: { label: "No insurance on file", variant: "danger", icon: UserX },
  error: { label: "Payer unreachable", variant: "warning", icon: AlertTriangle },
  stale: { label: "Needs re-verification", variant: "warning", icon: RefreshCw },
  unverified: { label: "Not verified", variant: "warning", icon: ShieldQuestion },
};

export function CoverageStateBadge({ state }: { state: string }) {
  const m = STATE_META[state] ?? { label: titleCase(state), variant: "neutral" as const, icon: ShieldQuestion };
  return <Badge variant={m.variant}><m.icon />{m.label}</Badge>;
}

export function InsuranceGuardianPage() {
  const [params, setParams] = useSearchParams();
  const [openCase, setOpenCase] = React.useState<string | null>(null);
  const s = useQuery({ queryKey: ["insurance", "summary"], queryFn: () => get<Summary>("/insurance/guardian/summary", { days: 7 }), refetchInterval: 60_000 });
  const cases = useQuery({ queryKey: ["cases", "insurance"], queryFn: () => get<CaseT[]>("/cases", { category: "insurance" }) });
  const reqs = useQuery({ queryKey: ["insurance", "requests"], queryFn: () => get<RequestT[]>("/insurance/requests", { status: "submitted" }) });
  const patient = params.get("patient");
  const requestId = params.get("request");
  const tab = requestId ? "review" : patient ? "patient" : params.get("tab") ?? "cases";
  const d = s.data;
  return (
    <>
      <PageHeader title="Insurance Guardian" description="Every upcoming visit verified with the payer before the patient arrives. Stored plan dates are reminders to confirm — never proof of coverage."
        actions={<div className="flex flex-wrap items-center gap-2">
          <AskAI agent="insurance_guardian" label="Summarize coverage issues" variant="outline" question="Summarize open insurance coverage issues for upcoming visits, most urgent first, and the next step for each." />
          {d?.simulated_eligibility && <SimulatedBadge label="Simulated payer (270/271)" />}
        </div>} />
      {s.isError ? <ErrorState error={s.error} retry={s.refetch} /> : (
        <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="Visits ready (next 7 days)" icon={BadgeCheck} tone="success" value={d ? (d.ready_pct == null ? "—" : `${d.ready_pct}%`) : "…"} sub={d ? `${d.ready} of ${d.visits} visits verified or cleared` : undefined} />
          <Stat label="Open insurance cases" icon={ShieldQuestion} tone="warning" value={d ? d.open_cases.reduce((a, c) => a + c.count, 0) : "…"} sub={d ? `${d.escalated_open} escalated` : undefined} />
          <Stat label="Waiting on patients" icon={CalendarClock} tone="primary" value={d?.requests.awaiting_patient ?? "…"} sub={d ? `${d.requests.awaiting_staff_review} card(s) awaiting staff review` : undefined} />
          <Stat label="Payer checks (7 days)" icon={RefreshCw} tone="ai" value={d ? Object.values(d.eligibility_checks_7d).reduce((a, b) => a + b, 0) : "…"} sub={d ? Object.entries(d.eligibility_checks_7d).map(([k, v]) => `${v} ${k}`).join(" · ") : undefined} />
        </div>
      )}
      {d && d.visits > 0 && <ReadinessBar states={d.states} total={d.visits} />}
      <Tabs value={tab} onValueChange={(v) => { const n = new URLSearchParams(); if (v !== "cases") n.set("tab", v); setParams(n); }}>
        <TabsList>
          <TabsTrigger value="cases">Cases</TabsTrigger>
          <TabsTrigger value="review">Card review {reqs.data?.length ? <span className="ml-1.5 rounded-full bg-destructive px-1.5 text-[11px] text-white">{reqs.data.length}</span> : null}</TabsTrigger>
          <TabsTrigger value="patient">Patient lookup</TabsTrigger>
          <TabsTrigger value="outcomes">Outcomes</TabsTrigger>
        </TabsList>
        <TabsContent value="cases">
          <Card className="overflow-hidden">
            {cases.isLoading ? <LoadingRows /> : !cases.data?.length ? <EmptyState icon={BadgeCheck} title="All upcoming visits are verified" /> : <ul className="divide-y">{cases.data.map((c) => <CaseRow key={c.id} c={c} onOpen={setOpenCase} />)}</ul>}
          </Card>
        </TabsContent>
        <TabsContent value="review"><CardReview selected={requestId} requests={reqs.data} loading={reqs.isLoading} /></TabsContent>
        <TabsContent value="patient"><PatientLookup patientId={patient} onPick={(id) => setParams({ patient: id })} /></TabsContent>
        <TabsContent value="outcomes">
          <Card><CardHeader><CardTitle>Resolved in the last 30 days</CardTitle></CardHeader>
            <CardContent>{!d?.resolved_30d.length ? <EmptyState title="No resolved cases yet" /> : (
              <ul className="divide-y text-[13.5px]">{d.resolved_30d.map((r) => <li key={r.code} className="flex justify-between py-2"><span>{titleCase(r.code.replace(/_/g, " "))}</span><span className="tabular text-muted-foreground">{r.count} · avg {r.avg_hours} h</span></li>)}</ul>
            )}
              {d && <p className="mt-3 text-xs text-muted-foreground">Patient reminders (7 days): {Object.entries(d.reminders_7d).map(([k, v]) => `${v} ${k}`).join(" · ") || "none"}. Email/SMS are delivered to the development outbox only.</p>}
            </CardContent></Card>
        </TabsContent>
      </Tabs>
      <CaseDrawer caseId={openCase} onClose={() => setOpenCase(null)} />
    </>
  );
}

function ReadinessBar({ states, total }: { states: Record<string, number>; total: number }) {
  const order = ["verified_active", "cleared_override", "stale", "unverified", "error", "verified_inactive", "no_coverage"];
  const color: Record<string, string> = { verified_active: "bg-success", cleared_override: "bg-success/60", stale: "bg-warning/70", unverified: "bg-warning", error: "bg-warning/50", verified_inactive: "bg-destructive", no_coverage: "bg-destructive/70" };
  return (
    <Card className="mb-5 p-4">
      <p className="mb-2 text-[13px] font-medium">Coverage status of the next {total} visits</p>
      <div className="flex h-3 overflow-hidden rounded-full bg-muted" role="img" aria-label="Coverage status distribution">
        {order.filter((k) => states[k]).map((k) => <div key={k} className={color[k]} style={{ width: `${(100 * states[k]) / total}%` }} title={`${STATE_META[k]?.label}: ${states[k]}`} />)}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {order.filter((k) => states[k]).map((k) => <span key={k} className="inline-flex items-center gap-1.5"><span className={cn("size-2 rounded-full", color[k])} />{STATE_META[k]?.label} · {states[k]}</span>)}
      </div>
    </Card>
  );
}

const FIELDS: [string, string][] = [["payer_name", "Payer"], ["plan_name", "Plan"], ["member_id", "Member ID"], ["group_number", "Group"], ["subscriber_name", "Subscriber"], ["effective_date", "Effective"]];

function CardReview({ selected, requests, loading }: { selected: string | null; requests?: RequestT[]; loading: boolean }) {
  const [current, setCurrent] = React.useState<RequestT | null>(null);
  React.useEffect(() => { if (selected && requests) setCurrent(requests.find((r) => r.id === selected) ?? null); }, [selected, requests]);
  if (loading) return <LoadingRows />;
  if (!requests?.length) return <EmptyState icon={FileImage} title="No cards waiting for review" description="When a patient uploads a new insurance card in the portal it appears here." />;
  return (
    <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
      <Card className="overflow-hidden"><ul className="divide-y">{requests.map((r) => (
        <li key={r.id}><button onClick={() => setCurrent(r)} className={cn("w-full px-4 py-3 text-left hover:bg-muted/40", current?.id === r.id && "bg-accent")}>
          <p className="text-[13.5px] font-medium">{r.patient_name} <span className="text-xs text-muted-foreground">{r.mrn}</span></p>
          <p className="text-xs text-muted-foreground">Submitted {fromNow(r.submitted_at)}{r.discrepancies.length ? ` · ${r.discrepancies.length} mismatch` : ""}</p>
        </button></li>))}</ul></Card>
      {current ? <ReviewForm key={current.id} r={current} onDone={() => setCurrent(null)} /> : <Card className="grid place-items-center p-10 text-[13px] text-muted-foreground">Select a submission to review</Card>}
    </div>
  );
}

function ReviewForm({ r, onDone }: { r: RequestT; onDone: () => void }) {
  const qc = useQueryClient();
  const initial = Object.fromEntries(FIELDS.map(([k]) => [k, r.extracted[k] ?? r.submitted[k] ?? ""]));
  const [f, setF] = React.useState<Record<string, string>>(initial);
  const [attest, setAttest] = React.useState(false);
  const [rejecting, setRejecting] = React.useState(false);
  const [note, setNote] = React.useState("");
  const done = () => { qc.invalidateQueries({ queryKey: ["insurance"] }); qc.invalidateQueries({ queryKey: ["cases"] }); qc.invalidateQueries({ queryKey: ["worklist"] }); onDone(); };
  const confirm = async () => {
    try {
      await post(`/insurance/requests/${r.id}/confirm`, { ...Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v || null])), attest_reviewed_card: attest });
      toast.success("Coverage confirmed — re-verified with the payer"); done();
    } catch (e) { toastError(e); }
  };
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between">
        <div><CardTitle>{r.patient_name}</CardTitle><p className="text-[13px] text-muted-foreground">{r.reason}</p></div>
        {r.document_id && <Button variant="outline" size="sm" asChild><a href={`/api/v1/documents/${r.document_id}/file`} target="_blank" rel="noreferrer" onClick={(e) => { e.preventDefault(); openDoc(r.document_id!); }}><FileImage />View card</a></Button>}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-[13px]"><thead className="bg-muted/50 text-xs text-muted-foreground"><tr><th className="px-3 py-2 text-left">Field</th><th className="px-3 py-2 text-left">Patient typed</th><th className="px-3 py-2 text-left">Read from card <Badge variant="ai" className="ml-1">AI draft</Badge></th></tr></thead>
            <tbody>{FIELDS.map(([k, label]) => (
              <tr key={k} className={cn("border-t", r.discrepancies.includes(k) && "bg-warning-soft/60")}>
                <td className="px-3 py-1.5 font-medium">{label}</td><td className="px-3 py-1.5">{r.submitted[k] || "—"}</td>
                <td className="px-3 py-1.5">{r.extracted[k] || <span className="text-muted-foreground">{r.document_status === "processing" ? "Reading…" : "—"}</span>}{r.discrepancies.includes(k) && <AlertTriangle className="ml-1 inline size-3.5 text-warning" aria-label="Mismatch" />}</td>
              </tr>))}</tbody></table>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">{FIELDS.map(([k, label]) => (
          <Field key={k} label={label} required={k === "payer_name" || k === "member_id"}><Input type={k === "effective_date" ? "date" : "text"} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>))}</div>
        <label className="flex items-start gap-2 text-[13px]"><Checkbox checked={attest} onCheckedChange={(v) => setAttest(!!v)} className="mt-0.5" />I compared these fields with the card image/details. AI extraction is a draft and may be wrong.</label>
        <div className="flex flex-wrap gap-2">
          <Button disabled={!attest || !f.payer_name || !f.member_id} onClick={confirm}><BadgeCheck />Confirm & re-verify</Button>
          <Button variant="outline" onClick={() => setRejecting(true)}>Send back to patient</Button>
        </div>
      </CardContent>
      <Dialog open={rejecting} onOpenChange={setRejecting}>
        <DialogContent size="sm"><DialogHeader><DialogTitle>Send back to patient</DialogTitle><DialogDescription>The patient gets a portal notification with your note.</DialogDescription></DialogHeader>
          <Field label="What's wrong?" required><Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. The back of the card is missing" /></Field>
          <DialogFooter><Button variant="outline" onClick={() => setRejecting(false)}>Cancel</Button>
            <Button disabled={note.trim().length < 5} onClick={async () => { try { await post(`/insurance/requests/${r.id}/reject`, { note }); toast.success("Sent back to the patient"); setRejecting(false); done(); } catch (e) { toastError(e); } }}>Send</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

async function openDoc(id: string) {
  const { api } = await import("@/lib/api");
  try {
    const res = await api<Response>(`/documents/${id}/file`, { raw: true });
    const url = URL.createObjectURL(await res.blob());
    window.open(url, "_blank", "noopener");
  } catch (e) { toastError(e); }
}

function PatientLookup({ patientId, onPick }: { patientId: string | null; onPick: (id: string) => void }) {
  const [q, setQ] = React.useState("");
  const res = useQuery({ queryKey: ["patients", "search", q], queryFn: () => get<{ items: { id: string; first_name: string; last_name: string; mrn: string; date_of_birth: string }[] }>("/patients", { q, page_size: 8 }), enabled: q.length >= 2 });
  return (
    <div className="space-y-4">
      <Card className="p-3"><div className="relative"><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" /><Input className="pl-9" placeholder="Find a patient by name or MRN…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search patients" /></div>
        {res.data?.items?.length ? <ul className="mt-2 divide-y">{res.data.items.map((p) => <li key={p.id}><button className="w-full px-2 py-2 text-left text-[13.5px] hover:bg-muted/40" onClick={() => { onPick(p.id); setQ(""); }}>{p.first_name} {p.last_name} <span className="text-xs text-muted-foreground">{p.mrn} · DOB {fmtDate(p.date_of_birth)}</span></button></li>)}</ul> : null}
      </Card>
      {patientId && <CoveragePanel patientId={patientId} />}
    </div>
  );
}

/** Coverage for a patient's next visit + payer check history + actions. Used in the Guardian and the patient chart. */
export function CoveragePanel({ patientId }: { patientId: string }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["insurance", "coverage", patientId], queryFn: () => get<Coverage>(`/patients/${patientId}/coverage`) });
  const [override, setOverride] = React.useState(false);
  const [ov, setOv] = React.useState({ kind: "self_pay", reason: "" });
  if (q.isLoading) return <LoadingRows />;
  if (q.isError || !q.data) return <ErrorState error={q.error} retry={q.refetch} />;
  const c = q.data;
  const refresh = () => { qc.invalidateQueries({ queryKey: ["insurance"] }); qc.invalidateQueries({ queryKey: ["cases"] }); };
  const check = async () => {
    if (!c.insurance_id) return;
    try { const r = await post<CheckT>(`/patients/${patientId}/insurances/${c.insurance_id}/eligibility-checks`, { date_of_service: c.date_of_service }); toast.info(`Payer response: ${r.result}${r.source === "simulated" ? " (simulated)" : ""}`); refresh(); } catch (e) { toastError(e); }
  };
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="flex flex-wrap items-center gap-2">Coverage for {c.next_visit ? `visit ${fmtDateTime(c.next_visit.start_at)}` : `today (${fmtDate(c.date_of_service)})`} <CoverageStateBadge state={c.next_visit?.coverage_override ? "cleared_override" : c.state} /></CardTitle>
          <p className="mt-1 text-[13px] text-muted-foreground">{c.reason}</p>
        </div>
        <div className="flex shrink-0 gap-2">
          {can("insurance:write") && c.insurance_id && <Button size="sm" variant="outline" onClick={check}><RefreshCw />Check with payer</Button>}
          {can("insurance:write") && c.next_visit && !c.next_visit.coverage_override && c.state !== "verified_active" && <Button size="sm" variant="outline" onClick={() => setOverride(true)}>Clear visit…</Button>}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {c.open_cases.length > 0 && <div className="flex flex-wrap gap-2">{c.open_cases.map((k) => <Badge key={k.id} variant="warning">Case #{k.number}: {k.status}</Badge>)}</div>}
        {c.requests.length > 0 && <p className="text-[13px]">Patient update request: <Badge variant="outline">{c.requests[0].status}</Badge>{c.requests[0].status === "submitted" && <Link className="ml-2 text-primary hover:underline" to={`/insurance?request=${c.requests[0].id}`}>Review card</Link>}</p>}
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Payer responses {c.simulated && <SimulatedBadge className="ml-1" />}</h4>
          {!c.checks.length ? <p className="text-[13px] text-muted-foreground">No eligibility checks yet.</p> : (
            <div className="overflow-x-auto"><table className="w-full text-[13px]"><thead className="text-xs text-muted-foreground"><tr><th className="py-1 text-left">Checked</th><th className="text-left">For date</th><th className="text-left">Result</th><th className="text-left">Payer-reported period</th><th className="text-left">How</th></tr></thead>
              <tbody>{c.checks.map((k) => (
                <tr key={k.id} className="border-t"><td className="py-1.5">{fmtDateTime(k.checked_at)}</td><td>{fmtDate(k.date_of_service)}</td>
                  <td><Badge variant={k.result === "active" ? "success" : k.result === "inactive" ? "danger" : "warning"}>{k.result}</Badge></td>
                  <td className="text-muted-foreground">{k.coverage_start ? fmtDate(k.coverage_start) : "—"} → {k.coverage_end ? fmtDate(k.coverage_end) : "open"}</td>
                  <td className="text-muted-foreground">{titleCase(k.trigger.replace("_", " "))} · {k.payer_trace}</td></tr>))}</tbody></table></div>
          )}
        </div>
      </CardContent>
      <Dialog open={override} onOpenChange={setOverride}>
        <DialogContent size="sm"><DialogHeader><DialogTitle>Clear visit without verified coverage</DialogTitle><DialogDescription>Recorded on the visit, the case and the audit log.</DialogDescription></DialogHeader>
          <Field label="Decision"><NativeSelect value={ov.kind} onChange={(e) => setOv({ ...ov, kind: e.target.value })}>{[["self_pay", "Self-pay"], ["financial_counseling", "Financial counseling"], ["charity", "Charity care"], ["other", "Other"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect></Field>
          <Field label="Reason" required><Textarea rows={3} value={ov.reason} onChange={(e) => setOv({ ...ov, reason: e.target.value })} /></Field>
          <DialogFooter><Button variant="outline" onClick={() => setOverride(false)}>Cancel</Button>
            <Button disabled={ov.reason.trim().length < 5} onClick={async () => { try { await post(`/appointments/${c.next_visit!.id}/coverage-override`, ov); toast.success("Visit cleared"); setOverride(false); refresh(); } catch (e) { toastError(e); } }}>Clear visit</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
