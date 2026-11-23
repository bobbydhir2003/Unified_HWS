import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Ban, CheckCircle2, CircleDollarSign, FileText, FlaskConical, Gavel, Plus, RefreshCw, Send, Trash2, Wallet } from "lucide-react";
import { Dialog as D } from "radix-ui";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { EmptyState, ErrorState, LoadingRows, PageHeader, SimulatedBadge, Stat, toastError, useConfirm } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, fmtMoney, newIdempotencyKey } from "@/lib/format";
import type { Page } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";

type ChargeT = { id?: string; code: string; description: string; units: number; unit_price_cents: number; amount_cents: number; diagnosis_codes: string[]; modifiers?: string[]; status?: string };
export type ClaimT = {
  id: string; claim_number: string; patient_id: string; patient: { name: string; mrn: string; date_of_birth: string } | null; encounter_id: string;
  payer_name: string; member_id: string; service_date: string; status: string; total_charge_cents: number; allowed_cents: number | null;
  paid_cents: number; patient_responsibility_cents: number; adjustment_cents: number; scrub_errors: string[]; clearinghouse_ref: string | null;
  submitted_at: string | null; adjudicated_at: string | null; denial_code: string | null; denial_reason: string | null; appeal_text: string | null;
  submission_count: number; created_at: string; charges: ChargeT[]; events: { event: string; details: Record<string, unknown>; created_at: string }[];
};
export type InvoiceT = { id: string; number: string; patient_id: string; patient: { name: string; mrn: string } | null; description: string; status: string; total_cents: number; balance_cents: number; issued_at: string; due_date: string; claim_id: string | null };
type Summary = {
  charges_mtd_cents: number; payments_mtd: Record<string, number>; ar_insurance_cents: number; ar_patient_cents: number;
  aging: Record<string, { insurance_cents: number; patient_cents: number }>; denial_rate: number | null;
  top_denials: { code: string; reason: string; count: number }[]; claims_by_status: Record<string, number>;
  collections_by_month: { month: string; source: string; cents: number }[];
};

const CLAIM_VARIANT: Record<string, React.ComponentProps<typeof Badge>["variant"]> = {
  draft: "warning", ready: "info", submitted: "primary", accepted: "primary", paid: "success", partially_paid: "success",
  denied: "danger", appealed: "ai", rejected: "danger", closed: "neutral", void: "neutral",
};
export const ClaimBadge = ({ s }: { s: string }) => <Badge variant={CLAIM_VARIANT[s] ?? "neutral"}>{titleCase(s)}</Badge>;
const TABS: [string, string][] = [["overview", "Overview"], ["capture", "Charge capture"], ["claims", "Claims"], ["denials", "Denials"], ["balances", "Patient balances"], ["fees", "Fee schedule"]];

export function BillingPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "overview";
  return (
    <>
      <PageHeader title="Billing" description="Charges, claims, denials and patient balances." actions={<SimulatedBadge label="Clearinghouse, payer & card processor simulated" />} />
      <nav className="-mx-1 mb-5 flex gap-1 overflow-x-auto border-b px-1" aria-label="Billing sections">
        {TABS.map(([k, l]) => (
          <button key={k} onClick={() => setParams({ tab: k })} className={cn("-mb-px shrink-0 border-b-2 border-transparent px-3 py-2 text-table font-medium text-muted-foreground hover:text-foreground", tab === k && "border-primary text-foreground")}>{l}</button>
        ))}
      </nav>
      {tab === "overview" && <Overview />}
      {tab === "capture" && <ChargeCapture />}
      {tab === "claims" && <ClaimsList statuses="" />}
      {tab === "denials" && <ClaimsList statuses="denied,appealed" />}
      {tab === "balances" && <Balances />}
      {tab === "fees" && <FeeSchedule />}
    </>
  );
}

function Overview() {
  const q = useQuery({ queryKey: ["billing-summary"], queryFn: () => get<Summary>("/billing/summary") });
  if (q.error) return <ErrorState error={q.error} />;
  if (!q.data) return <LoadingRows />;
  const s = q.data;
  const aging = Object.entries(s.aging).map(([bucket, v]) => ({ bucket, Insurance: v.insurance_cents / 100, Patient: v.patient_cents / 100 }));
  const months = [...new Set(s.collections_by_month.map((x) => x.month))].map((m) => ({
    month: new Date(m).toLocaleDateString("en-US", { month: "short", timeZone: "UTC" }),
    Insurance: (s.collections_by_month.find((x) => x.month === m && x.source === "insurance")?.cents ?? 0) / 100,
    Patient: (s.collections_by_month.find((x) => x.month === m && x.source === "patient")?.cents ?? 0) / 100,
  }));
  const tip = { contentStyle: { background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }, formatter: (v: unknown) => fmtMoney(Math.round(Number(v ?? 0) * 100)) };
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Charges this month" value={fmtMoney(s.charges_mtd_cents)} icon={FileText} />
        <Stat label="Collected this month" value={fmtMoney((s.payments_mtd.insurance ?? 0) + (s.payments_mtd.patient ?? 0))} sub={`Insurance ${fmtMoney(s.payments_mtd.insurance ?? 0)} · Patient ${fmtMoney(s.payments_mtd.patient ?? 0)}`} icon={CircleDollarSign} tone="success" />
        <Stat label="A/R outstanding" value={fmtMoney(s.ar_insurance_cents + s.ar_patient_cents)} sub={`Insurance ${fmtMoney(s.ar_insurance_cents)} · Patient ${fmtMoney(s.ar_patient_cents)}`} icon={Wallet} tone="warning" />
        <Stat label="Denial rate" value={s.denial_rate == null ? "—" : `${Math.round(s.denial_rate * 100)}%`} sub="of adjudicated claims" icon={Gavel} tone="danger" />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card><CardHeader><CardTitle>A/R aging</CardTitle></CardHeader><CardContent className="h-60">
          <ResponsiveContainer><BarChart data={aging} margin={{ left: -8 }}><CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="bucket" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} />
            <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} />
            <RTooltip {...tip} /><Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="Insurance" stackId="a" fill="var(--primary)" /><Bar dataKey="Patient" stackId="a" fill="var(--ai)" radius={[4, 4, 0, 0]} />
          </BarChart></ResponsiveContainer>
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Collections (6 months)</CardTitle></CardHeader><CardContent className="h-60">
          {!months.length ? <p className="text-table text-muted-foreground">No payments yet.</p> : (
            <ResponsiveContainer><BarChart data={months} margin={{ left: -8 }}><CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis dataKey="month" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} />
              <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} />
              <RTooltip {...tip} /><Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Insurance" fill="var(--success)" radius={[4, 4, 0, 0]} /><Bar dataKey="Patient" fill="var(--warning)" radius={[4, 4, 0, 0]} />
            </BarChart></ResponsiveContainer>
          )}
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Claims by status</CardTitle></CardHeader><CardContent className="flex flex-wrap gap-2">
          {Object.entries(s.claims_by_status).map(([k, v]) => <span key={k} className="flex items-center gap-1.5"><ClaimBadge s={k} /><span className="text-table font-semibold tabular">{v}</span></span>)}
          {!Object.keys(s.claims_by_status).length && <p className="text-table text-muted-foreground">No claims yet.</p>}
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Top denial reasons</CardTitle></CardHeader><CardContent>
          {!s.top_denials.length ? <p className="text-table text-muted-foreground">No denials.</p> : <ul className="space-y-1.5 text-table">{s.top_denials.map((d) => <li key={d.code} className="flex justify-between gap-2"><span><span className="font-mono text-xs font-semibold">{d.code}</span> {d.reason}</span><span className="tabular">{d.count}</span></li>)}</ul>}
        </CardContent></Card>
      </div>
    </div>
  );
}

type QueueItem = { encounter_id: string; patient: { id: string; name: string; mrn: string }; provider: string; service_date: string; chief_complaint: string | null; diagnoses: { code: string; description: string }[]; payer: string | null; charges_cents: number | null };
type CaptureData = { encounter: { id: string; service_date: string; provider: string; patient: { id: string; name: string; mrn: string }; diagnoses: { code: string; description: string }[] }; insurance: { payer_name: string; member_id: string; eligibility_status: string } | null; charges: ChargeT[]; suggestions: (ChargeT & { reason: string })[] };
type Fee = { code: string; description: string; price_cents: number; is_active: boolean };

function ChargeCapture() {
  const q = useQuery({ queryKey: ["charge-queue"], queryFn: () => get<QueueItem[]>("/billing/charge-queue") });
  const [open, setOpen] = React.useState<string | null>(null);
  return (
    <Card className="overflow-hidden">
      {q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState icon={CheckCircle2} title="All completed visits are billed" /> : (
        <Table>
          <THead><TR><TH>Date of service</TH><TH>Patient</TH><TH>Provider</TH><TH className="hidden md:table-cell">Diagnoses</TH><TH>Payer</TH><TH>Charges</TH></TR></THead>
          <TBody>{q.data.map((x) => (
            <TR key={x.encounter_id} data-clickable tabIndex={0} onClick={() => setOpen(x.encounter_id)} onKeyDown={(e) => e.key === "Enter" && setOpen(x.encounter_id)}>
              <TD className="whitespace-nowrap">{fmtDate(x.service_date)}</TD>
              <TD><span className="font-medium">{x.patient.name}</span><span className="block text-xs text-muted-foreground">{x.patient.mrn}</span></TD>
              <TD>{x.provider}</TD>
              <TD className="hidden md:table-cell"><div className="flex flex-wrap gap-1">{x.diagnoses.map((d) => <Badge key={d.code} variant="outline">{d.code}</Badge>)}</div></TD>
              <TD>{x.payer ?? <Badge variant="warning">Self-pay</Badge>}</TD>
              <TD>{x.charges_cents ? fmtMoney(x.charges_cents) : <Badge variant="warning">Not captured</Badge>}</TD>
            </TR>
          ))}</TBody>
        </Table>
      )}
      <ChargeDrawer encounterId={open} onOpenChange={(v) => !v && setOpen(null)} />
    </Card>
  );
}

function ChargeDrawer({ encounterId, onOpenChange }: { encounterId: string | null; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["capture", encounterId], queryFn: () => get<CaptureData>(`/encounters/${encounterId}/charges`), enabled: !!encounterId });
  const fees = useQuery({ queryKey: ["fees"], queryFn: () => get<Fee[]>("/fee-schedule"), enabled: !!encounterId });
  const [lines, setLines] = React.useState<{ code: string; units: number; diagnosis_codes: string[] }[]>([]);
  const [busy, setBusy] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!q.data) return;
    setLines(q.data.charges.length ? q.data.charges.map((c) => ({ code: c.code, units: c.units, diagnosis_codes: c.diagnosis_codes }))
      : q.data.suggestions.map((s) => ({ code: s.code, units: 1, diagnosis_codes: s.diagnosis_codes })));
  }, [q.data]);
  const feeMap = new Map((fees.data ?? []).map((f) => [f.code, f]));
  const total = lines.reduce((n, l) => n + (feeMap.get(l.code)?.price_cents ?? 0) * l.units, 0);
  const refresh = () => ["charge-queue", "capture", "claims", "billing-summary", "invoices"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const save = async () => { await put(`/encounters/${encounterId}/charges`, lines); refresh(); };
  const d = q.data;
  return (
    <Dialog open={!!encounterId} onOpenChange={onOpenChange}>
      <SheetContent className="max-w-2xl" aria-describedby={undefined}>
        <div className="border-b px-6 py-5">
          <D.Title className="text-base font-semibold">Charge capture</D.Title>
          {d && <p className="text-table text-muted-foreground">{d.encounter.patient.name} · {fmtDate(d.encounter.service_date)} · {d.encounter.provider}</p>}
        </div>
        {!d ? <LoadingRows /> : (
          <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
            <div className="flex flex-wrap gap-2 text-table">
              {d.insurance ? <Badge variant="info">{d.insurance.payer_name} · {d.insurance.member_id}</Badge> : <Badge variant="warning">No active insurance (self-pay)</Badge>}
              {d.encounter.diagnoses.map((x) => <Badge key={x.code} variant="outline">{x.code} {x.description}</Badge>)}
            </div>
            {d.suggestions.length > 0 && (
              <div className="rounded-lg border border-ai/25 bg-ai-soft/50 p-3 text-table">
                <p className="mb-1 font-medium text-ai">Suggested codes (rule-based)</p>
                {d.suggestions.map((s) => <p key={s.code}><span className="font-mono font-semibold">{s.code}</span> — {s.reason}</p>)}
              </div>
            )}
            <table className="w-full text-table">
              <thead><tr className="text-left text-label uppercase tracking-wide text-muted-foreground"><th className="pb-1">Code</th><th>Units</th><th>Dx pointers</th><th className="text-right">Amount</th><th /></tr></thead>
              <tbody>{lines.map((l, i) => (
                <tr key={i} className="border-t">
                  <td className="py-1.5 pr-2"><NativeSelect value={l.code} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, code: e.target.value } : x))} aria-label="Code">
                    {fees.data?.filter((f) => f.is_active).map((f) => <option key={f.code} value={f.code}>{f.code} — {f.description}</option>)}
                  </NativeSelect></td>
                  <td className="pr-2"><Input className="w-16" inputMode="numeric" value={l.units} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, units: Math.max(1, Number(e.target.value.replace(/\D/g, "")) || 1) } : x))} aria-label="Units" /></td>
                  <td className="pr-2"><div className="flex flex-wrap gap-1">{d.encounter.diagnoses.map((dx) => {
                    const on = l.diagnosis_codes.includes(dx.code);
                    return <button key={dx.code} type="button" onClick={() => setLines(lines.map((x, j) => j === i ? { ...x, diagnosis_codes: on ? x.diagnosis_codes.filter((c) => c !== dx.code) : [...x.diagnosis_codes, dx.code].slice(0, 4) } : x))}
                      className={cn("rounded border px-1.5 py-0.5 font-mono text-label", on && "border-primary bg-primary text-primary-foreground")}>{dx.code}</button>;
                  })}</div></td>
                  <td className="text-right tabular">{fmtMoney((feeMap.get(l.code)?.price_cents ?? 0) * l.units)}</td>
                  <td><Button variant="ghost" size="icon-sm" onClick={() => setLines(lines.filter((_, j) => j !== i))} aria-label="Remove line"><Trash2 /></Button></td>
                </tr>
              ))}</tbody>
              <tfoot><tr className="border-t font-semibold"><td colSpan={3} className="py-2">Total</td><td className="text-right tabular">{fmtMoney(total)}</td><td /></tr></tfoot>
            </table>
            <Button variant="outline" size="sm" onClick={() => setLines([...lines, { code: fees.data?.[0]?.code ?? "99213", units: 1, diagnosis_codes: d.encounter.diagnoses.slice(0, 1).map((x) => x.code) }])}><Plus />Add line</Button>
          </div>
        )}
        <div className="flex flex-wrap gap-2 border-t px-6 py-4">
          <Button variant="outline" loading={busy === "save"} disabled={!lines.length} onClick={async () => { setBusy("save"); try { await save(); toast.success("Charges saved"); } catch (e) { toastError(e); } finally { setBusy(null); } }}>Save charges</Button>
          {d?.insurance ? (
            <Button loading={busy === "claim"} disabled={!lines.length || lines.some((l) => !l.diagnosis_codes.length)} onClick={async () => {
              setBusy("claim");
              try { await save(); const c = await post<ClaimT>("/claims", { encounter_id: encounterId }); toast.success(`Claim ${c.claim_number} created (${c.status})`); refresh(); onOpenChange(false); }
              catch (e) { toastError(e); } finally { setBusy(null); }
            }}><FileText />Save & create claim</Button>
          ) : d && (
            <Button loading={busy === "inv"} disabled={!lines.length} onClick={async () => {
              setBusy("inv");
              try { await save(); await post(`/encounters/${encounterId}/self-pay-invoice`); toast.success("Self-pay statement created"); refresh(); onOpenChange(false); }
              catch (e) { toastError(e); } finally { setBusy(null); }
            }}><Wallet />Save & bill patient</Button>
          )}
        </div>
      </SheetContent>
    </Dialog>
  );
}

export function ClaimsList({ statuses }: { statuses: string }) {
  const [status, setStatus] = React.useState(statuses);
  const q = useQuery({ queryKey: ["claims", status], queryFn: () => get<Page<ClaimT>>("/claims", { status }), placeholderData: keepPreviousData });
  const [openId, setOpenId] = React.useState<string | null>(null);
  const items = q.data?.items ?? [];
  const open = items.find((c) => c.id === openId) ?? null;
  return (
    <Card className="overflow-hidden">
      {!statuses && (
        <div className="border-b p-3"><NativeSelect value={status} onChange={(e) => setStatus(e.target.value)} className="w-52" aria-label="Status">
          <option value="">All statuses</option>{["draft", "ready", "accepted", "paid", "denied", "appealed", "closed", "void"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
        </NativeSelect></div>
      )}
      {q.isLoading ? <LoadingRows /> : !items.length ? <EmptyState icon={FileText} title="No claims" /> : (
        <Table>
          <THead><TR><TH>Claim</TH><TH>Patient</TH><TH className="hidden md:table-cell">Payer</TH><TH className="text-right">Billed</TH><TH className="hidden text-right lg:table-cell">Paid</TH><TH>Status</TH></TR></THead>
          <TBody>{items.map((c) => (
            <TR key={c.id} data-clickable tabIndex={0} onClick={() => setOpenId(c.id)} onKeyDown={(e) => e.key === "Enter" && setOpenId(c.id)}>
              <TD><span className="font-mono text-table font-medium">{c.claim_number}</span><span className="block text-xs text-muted-foreground">DOS {fmtDate(c.service_date)}</span></TD>
              <TD>{c.patient?.name}<span className="block text-xs text-muted-foreground">{c.patient?.mrn}</span></TD>
              <TD className="hidden md:table-cell">{c.payer_name}</TD>
              <TD className="text-right tabular">{fmtMoney(c.total_charge_cents)}</TD>
              <TD className="hidden text-right tabular lg:table-cell">{c.paid_cents ? fmtMoney(c.paid_cents) : "—"}</TD>
              <TD><ClaimBadge s={c.status} />{c.denial_code && <span className="block text-xs text-destructive">{c.denial_code}</span>}{!!c.scrub_errors.length && c.status === "draft" && <span className="block text-xs text-warning">{c.scrub_errors.length} error(s)</span>}</TD>
            </TR>
          ))}</TBody>
        </Table>
      )}
      <ClaimDrawer claim={open} onOpenChange={(v) => !v && setOpenId(null)} />
    </Card>
  );
}

export function ClaimDrawer({ claim: c, onOpenChange }: { claim: ClaimT | null; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const { confirm, dialog } = useConfirm();
  const [busy, setBusy] = React.useState<string | null>(null);
  const [appealOpen, setAppealOpen] = React.useState(false);
  const [appealText, setAppealText] = React.useState("");
  const submitKey = React.useRef<Record<string, string>>({});
  const refresh = () => ["claims", "billing-summary", "invoices", "patient-billing"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const act = async (k: string, fn: () => Promise<unknown>, ok?: string) => {
    setBusy(k);
    try { await fn(); if (ok) toast.success(ok); refresh(); } catch (e) { toastError(e); } finally { setBusy(null); }
  };
  const w = can("billing:write");
  return (
    <>
      {dialog}
      <Dialog open={!!c} onOpenChange={onOpenChange}>
        <SheetContent className="max-w-xl" aria-describedby={undefined}>
          {c && (
            <div className="flex h-full flex-col">
              <div className="border-b px-6 py-5">
                <D.Title className="flex items-center gap-2 text-base font-semibold"><span className="font-mono">{c.claim_number}</span><ClaimBadge s={c.status} /></D.Title>
                <p className="mt-1 text-table text-muted-foreground"><Link to={`/patients/${c.patient_id}`} className="text-primary hover:underline">{c.patient?.name}</Link> · {c.payer_name} · member {c.member_id} · DOS {fmtDate(c.service_date)}</p>
              </div>
              <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5 text-table">
                {c.scrub_errors.length > 0 && ["draft", "ready"].includes(c.status) && (
                  <div className="rounded-lg border border-warning/40 bg-warning-soft p-3">{c.scrub_errors.map((e) => <p key={e} className="flex gap-1.5"><AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" />{e}</p>)}</div>
                )}
                {c.denial_code && <div className="rounded-lg border border-destructive/30 bg-destructive-soft p-3 text-destructive"><strong>{c.denial_code}</strong> — {c.denial_reason}</div>}
                <table className="w-full">
                  <thead><tr className="text-left text-label uppercase tracking-wide text-muted-foreground"><th className="pb-1">Line</th><th>Dx</th><th className="text-right">Amount</th></tr></thead>
                  <tbody>{c.charges.map((ch) => <tr key={ch.id} className="border-t"><td className="py-1.5"><span className="font-mono font-medium">{ch.code}</span> {ch.description}{ch.units > 1 ? ` × ${ch.units}` : ""}</td><td className="font-mono text-xs">{ch.diagnosis_codes.join(", ")}</td><td className="text-right tabular">{fmtMoney(ch.amount_cents)}</td></tr>)}</tbody>
                </table>
                <dl className="grid grid-cols-2 gap-2 rounded-lg border p-3 tabular">
                  <dt className="text-muted-foreground">Billed</dt><dd className="text-right">{fmtMoney(c.total_charge_cents)}</dd>
                  <dt className="text-muted-foreground">Allowed</dt><dd className="text-right">{fmtMoney(c.allowed_cents)}</dd>
                  <dt className="text-muted-foreground">Insurance paid</dt><dd className="text-right">{fmtMoney(c.paid_cents)}</dd>
                  <dt className="text-muted-foreground">Contractual adjustment</dt><dd className="text-right">{fmtMoney(c.adjustment_cents)}</dd>
                  <dt className="font-medium">Patient responsibility</dt><dd className="text-right font-medium">{fmtMoney(c.patient_responsibility_cents)}</dd>
                </dl>
                <div>
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">History</p>
                  <ol className="space-y-1.5">{c.events.map((e, i) => <li key={i} className="flex gap-2"><span className="w-32 shrink-0 text-xs text-muted-foreground">{fmtDateTime(e.created_at)}</span><span>{titleCase(e.event)}{e.details?.simulated ? <span className="ml-1 text-xs text-warning">(simulated)</span> : null}</span></li>)}</ol>
                </div>
                {c.appeal_text && <div><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Appeal</p><p className="whitespace-pre-wrap">{c.appeal_text}</p></div>}
              </div>
              {w && (
                <div className="flex flex-wrap gap-2 border-t px-6 py-4">
                  {["draft", "ready", "rejected", "denied"].includes(c.status) && <Button size="sm" variant="outline" loading={busy === "scrub"} onClick={() => act("scrub", () => post(`/claims/${c.id}/rescrub`), "Claim re-checked")}><RefreshCw />Re-check</Button>}
                  {["ready", "denied"].includes(c.status) && (
                    <Button size="sm" loading={busy === "submit"} onClick={() => {
                      submitKey.current[c.id] ??= newIdempotencyKey("claim-submit");
                      act("submit", async () => { await post(`/claims/${c.id}/submit`, {}, { "Idempotency-Key": submitKey.current[c.id] }); delete submitKey.current[c.id]; }, c.status === "denied" ? "Corrected claim resubmitted" : "Claim submitted");
                    }}><Send />{c.status === "denied" ? "Resubmit" : "Submit"}</Button>
                  )}
                  {c.status === "accepted" && <Button size="sm" variant="outline" loading={busy === "adj"} onClick={() => act("adj", () => post(`/claims/${c.id}/simulate-adjudication`))}><FlaskConical />Simulate payer response</Button>}
                  {c.status === "denied" && <Button size="sm" variant="outline" onClick={() => { setAppealText(""); setAppealOpen(true); }}><Gavel />Appeal</Button>}
                  {c.status === "appealed" && <Button size="sm" variant="outline" loading={busy === "apd"} onClick={() => act("apd", () => post(`/claims/${c.id}/simulate-appeal-decision`))}><FlaskConical />Simulate appeal decision</Button>}
                  {["draft", "ready", "rejected", "denied"].includes(c.status) && (
                    <Button size="sm" variant="ghost" className="ml-auto text-destructive" onClick={async () => {
                      const r = await confirm({ title: `Void ${c.claim_number}?`, description: "Charges return to the capture queue.", requireReason: true, destructive: true, confirmLabel: "Void claim" });
                      if (r) act("void", () => post(`/claims/${c.id}/void`, { reason: r }), "Claim voided");
                    }}><Ban />Void</Button>
                  )}
                </div>
              )}
            </div>
          )}
        </SheetContent>
      </Dialog>
      <Dialog open={appealOpen} onOpenChange={setAppealOpen}>
        <DialogContent size="md">
          <DialogHeader><DialogTitle>Appeal {c?.claim_number}</DialogTitle><DialogDescription>{c?.denial_code} — {c?.denial_reason}</DialogDescription></DialogHeader>
          <Field label="Appeal letter" hint="At least 20 characters. Cite documentation supporting the claim."><Textarea rows={6} value={appealText} onChange={(e) => setAppealText(e.target.value)} /></Field>
          <DialogFooter><Button variant="outline" onClick={() => setAppealOpen(false)}>Cancel</Button>
            <Button disabled={appealText.trim().length < 20} loading={busy === "appeal"} onClick={() => act("appeal", async () => { await post(`/claims/${c!.id}/appeal`, { text: appealText }); setAppealOpen(false); }, "Appeal submitted (simulated)")}><Gavel />Submit appeal</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function PaymentDialog({ invoice, onOpenChange }: { invoice: InvoiceT | null; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const [amount, setAmount] = React.useState("");
  const [method, setMethod] = React.useState<"cash" | "check" | "card_simulated">("cash");
  const [reference, setReference] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const key = React.useRef<string | null>(null);
  React.useEffect(() => { if (invoice) { setAmount((invoice.balance_cents / 100).toFixed(2)); key.current = null; } }, [invoice]);
  const cents = Math.round(Number(amount) * 100);
  return (
    <Dialog open={!!invoice} onOpenChange={onOpenChange}>
      <DialogContent size="sm">
        <DialogHeader><DialogTitle>Record payment</DialogTitle><DialogDescription>{invoice?.number} · balance {fmtMoney(invoice?.balance_cents)}</DialogDescription></DialogHeader>
        <div className="grid gap-3">
          <Field label="Amount (USD)"><Input inputMode="decimal" value={amount} onChange={(e) => { setAmount(e.target.value.replace(/[^\d.]/g, "")); key.current = null; }} /></Field>
          <Field label="Method"><NativeSelect value={method} onChange={(e) => { setMethod(e.target.value as typeof method); key.current = null; }}><option value="cash">Cash</option><option value="check">Check</option><option value="card_simulated">Card (simulated processor)</option></NativeSelect></Field>
          {method === "check" && <Field label="Check number"><Input value={reference} onChange={(e) => setReference(e.target.value)} /></Field>}
          {method === "card_simulated" && <p className="text-xs text-muted-foreground">No card data is entered or stored; the processor is simulated.</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button loading={busy} disabled={!(cents > 0) || (invoice ? cents > invoice.balance_cents : true)} onClick={async () => {
            key.current ??= newIdempotencyKey("pay");
            setBusy(true);
            try {
              await post(`/invoices/${invoice!.id}/payments`, { amount_cents: cents, method, reference: reference || null }, { "Idempotency-Key": key.current });
              toast.success(`Payment of ${fmtMoney(cents)} recorded`);
              ["invoices", "billing-summary", "patient-billing"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
              onOpenChange(false);
            } catch (e) { toastError(e); } finally { setBusy(false); }
          }}><CircleDollarSign />Record {cents > 0 ? fmtMoney(cents) : ""}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Balances() {
  const [status, setStatus] = React.useState("open");
  const q = useQuery({ queryKey: ["invoices", status], queryFn: () => get<InvoiceT[]>("/invoices", { status }) });
  const { can } = useAuth();
  const [paying, setPaying] = React.useState<InvoiceT | null>(null);
  return (
    <Card className="overflow-hidden">
      <div className="border-b p-3"><NativeSelect value={status} onChange={(e) => setStatus(e.target.value)} className="w-40" aria-label="Status"><option value="open">Open</option><option value="paid">Paid</option></NativeSelect></div>
      {q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState icon={Wallet} title="No statements" /> : (
        <Table>
          <THead><TR><TH>Statement</TH><TH>Patient</TH><TH className="hidden md:table-cell">For</TH><TH className="text-right">Total</TH><TH className="text-right">Balance</TH><TH className="hidden lg:table-cell">Due</TH><TH /></TR></THead>
          <TBody>{q.data.map((i) => (
            <TR key={i.id}>
              <TD className="font-mono text-table">{i.number}</TD>
              <TD><Link to={`/patients/${i.patient_id}/billing`} className="font-medium hover:underline">{i.patient?.name}</Link></TD>
              <TD className="hidden max-w-72 truncate md:table-cell">{i.description}</TD>
              <TD className="text-right tabular">{fmtMoney(i.total_cents)}</TD>
              <TD className="text-right font-medium tabular">{fmtMoney(i.balance_cents)}</TD>
              <TD className={cn("hidden lg:table-cell", i.status === "open" && new Date(i.due_date) < new Date() && "text-destructive")}>{fmtDate(i.due_date)}</TD>
              <TD>{i.status === "open" && can("billing:write") && <Button size="xs" variant="outline" onClick={() => setPaying(i)}><CircleDollarSign />Payment</Button>}</TD>
            </TR>
          ))}</TBody>
        </Table>
      )}
      <PaymentDialog invoice={paying} onOpenChange={(v) => !v && setPaying(null)} />
    </Card>
  );
}

function FeeSchedule() {
  const qc = useQueryClient();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["fees"], queryFn: () => get<Fee[]>("/fee-schedule") });
  const [edit, setEdit] = React.useState<Record<string, string>>({});
  return (
    <Card className="overflow-hidden">
      <p className="border-b px-4 py-2.5 text-xs text-muted-foreground">CPT® codes and descriptions are AMA-licensed; this development list is abbreviated. Prices apply to new charges only.</p>
      {q.isLoading ? <LoadingRows /> : (
        <Table>
          <THead><TR><TH>Code</TH><TH>Description</TH><TH className="text-right">Price</TH><TH /></TR></THead>
          <TBody>{q.data?.map((f) => (
            <TR key={f.code}>
              <TD className="font-mono font-medium">{f.code}</TD><TD>{f.description}</TD>
              <TD className="text-right">{edit[f.code] !== undefined ? <Input className="ml-auto w-28 text-right" value={edit[f.code]} onChange={(e) => setEdit({ ...edit, [f.code]: e.target.value.replace(/[^\d.]/g, "") })} aria-label={`Price for ${f.code}`} /> : <span className="tabular">{fmtMoney(f.price_cents)}</span>}</TD>
              <TD className="w-28">{can("billing:write") && (edit[f.code] !== undefined
                ? <Button size="xs" variant="outline" onClick={async () => { try { await put(`/fee-schedule/${f.code}`, { description: f.description, price_cents: Math.round(Number(edit[f.code]) * 100), is_active: f.is_active }); const n = { ...edit }; delete n[f.code]; setEdit(n); qc.invalidateQueries({ queryKey: ["fees"] }); } catch (e) { toastError(e); } }}>Save</Button>
                : <Button size="xs" variant="ghost" onClick={() => setEdit({ ...edit, [f.code]: (f.price_cents / 100).toFixed(2) })}>Edit</Button>)}</TD>
            </TR>
          ))}</TBody>
        </Table>
      )}
    </Card>
  );
}

export function PatientBillingTab({ patientId }: { patientId: string }) {
  const q = useQuery({ queryKey: ["patient-billing", patientId], queryFn: () => get<{ balance_cents: number; claims: ClaimT[]; invoices: InvoiceT[]; payments: { id: string; source: string; method: string; amount_cents: number; created_at: string; reference: string | null }[] }>(`/patients/${patientId}/billing`) });
  const { can } = useAuth();
  const [paying, setPaying] = React.useState<InvoiceT | null>(null);
  const [openClaim, setOpenClaim] = React.useState<string | null>(null);
  if (!q.data) return <LoadingRows />;
  const d = q.data;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="lg:col-span-2"><CardContent className="flex items-center gap-4 pt-5"><Wallet className="size-5 text-primary" /><div><p className="text-xs text-muted-foreground">Patient balance</p><p className="text-xl font-semibold tabular">{fmtMoney(d.balance_cents)}</p></div></CardContent></Card>
      <Card><CardHeader className="pb-2"><CardTitle>Claims</CardTitle></CardHeader><CardContent>
        {!d.claims.length ? <p className="text-table text-muted-foreground">None.</p> : <ul className="divide-y text-table">{d.claims.map((c) => (
          <li key={c.id}><button onClick={() => setOpenClaim(c.id)} className="flex w-full items-center justify-between gap-2 py-2 text-left hover:underline"><span><span className="font-mono">{c.claim_number}</span> · DOS {fmtDate(c.service_date)}</span><span className="flex items-center gap-2 tabular">{fmtMoney(c.total_charge_cents)}<ClaimBadge s={c.status} /></span></button></li>
        ))}</ul>}
      </CardContent></Card>
      <Card><CardHeader className="pb-2"><CardTitle>Statements</CardTitle></CardHeader><CardContent>
        {!d.invoices.length ? <p className="text-table text-muted-foreground">None.</p> : <ul className="divide-y text-table">{d.invoices.map((i) => (
          <li key={i.id} className="flex items-center justify-between gap-2 py-2"><span className="min-w-0"><span className="font-mono">{i.number}</span><span className="block truncate text-xs text-muted-foreground">{i.description}</span></span>
            <span className="flex shrink-0 items-center gap-2 tabular">{fmtMoney(i.balance_cents)}{i.status === "open" ? (can("billing:write") && <Button size="xs" variant="outline" onClick={() => setPaying(i)}>Pay</Button>) : <Badge variant="success">Paid</Badge>}</span></li>
        ))}</ul>}
      </CardContent></Card>
      <Card className="lg:col-span-2"><CardHeader className="pb-2"><CardTitle>Payments</CardTitle></CardHeader><CardContent>
        {!d.payments.length ? <p className="text-table text-muted-foreground">None.</p> : <ul className="divide-y text-table">{d.payments.map((p) => (
          <li key={p.id} className="flex justify-between gap-2 py-2"><span>{fmtDateTime(p.created_at)} · {titleCase(p.source)} · {titleCase(p.method)}{p.reference ? ` · ${p.reference}` : ""}</span><span className="tabular">{fmtMoney(p.amount_cents)}</span></li>
        ))}</ul>}
      </CardContent></Card>
      <PaymentDialog invoice={paying} onOpenChange={(v) => !v && setPaying(null)} />
      <ClaimDrawer claim={d.claims.find((c) => c.id === openClaim) ?? null} onOpenChange={(v) => !v && setOpenClaim(null)} />
    </div>
  );
}
