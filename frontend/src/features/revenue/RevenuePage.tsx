import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Bot, ClipboardCheck, FileSearch, ListChecks, ShieldAlert, TrendingDown } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { EmptyState, LoadingRows, PageHeader, SimulatedBadge, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { NativeSelect, Textarea } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtMoney, fromNow } from "@/lib/format";
import { titleCase } from "@/lib/utils";
import { AskAI } from "@/features/ai/AskAI";

type PA = { id: string; number: number; status: string; patient: { id: string; name: string; mrn: string }; service_code: string; service_description: string; payer_name: string | null;
  checklist: { key: string; label: string; done: boolean; note: string | null }[]; clinical_summary: string | null; auth_number: string | null; valid_from: string | null; valid_to: string | null;
  denial_reason: string | null; source: string; created_at: string };
type Finding = { id: string; source: string; code: string; severity: string; message: string; status: string; resolution_note: string | null; model: string | null };
type Claim = { id: string; claim_number: string; status: string; payer_name: string; service_date: string; total_charge_cents: number; scrub_errors: string[]; patient: { name: string } };
type Coding = { encounter_id: string; type: string; patient: { id: string; name: string; mrn: string }; service_date: string; charges_cents: number; charge_codes: string[]; missing: string[] };
type Denials = { submitted: number; denied: number; denial_rate_pct: number | null; by_reason: { code: string; reason: string; payer: string; count: number; charges_cents: number; prevention: string | null }[] };

const PA_V: Record<string, React.ComponentProps<typeof Badge>["variant"]> = { draft: "neutral", submitted: "info", pended: "warning", approved: "success", denied: "danger", cancelled: "neutral", expired: "neutral" };
const SEV_V: Record<string, React.ComponentProps<typeof Badge>["variant"]> = { blocker: "danger", warning: "warning", info: "info" };

export function RevenuePage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? (can("insurance:write") ? "prior-auth" : "review");
  return (
    <>
      <PageHeader title="Claims & authorizations" description="Prior authorizations, claim review and coding — catching problems before claims go out. Reviews only flag issues; people decide."
        actions={<AskAI agent="claims_review" label="Explain claim problems" question="Explain which claims need attention and why, citing case references, most urgent first." />} />
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v })}>
        <TabsList>
          {can("insurance:write") && <TabsTrigger value="prior-auth">Prior authorizations</TabsTrigger>}
          {can("billing:read") && <TabsTrigger value="review">Claim review</TabsTrigger>}
          {can("billing:read") && <TabsTrigger value="coding">Coding queue</TabsTrigger>}
          {can("billing:read") && <TabsTrigger value="denials">Denials</TabsTrigger>}
        </TabsList>
        <TabsContent value="prior-auth"><PriorAuths /></TabsContent>
        <TabsContent value="review"><ClaimReview /></TabsContent>
        <TabsContent value="coding"><CodingQueue /></TabsContent>
        <TabsContent value="denials"><DenialsPanel /></TabsContent>
      </Tabs>
    </>
  );
}

function PriorAuths() {
  const qc = useQueryClient();
  const [status, setStatus] = React.useState("open");
  const q = useQuery({ queryKey: ["revenue", "pa", status], queryFn: () => get<PA[]>("/prior-auths", { status: status === "all" ? undefined : status }) });
  const [open, setOpen] = React.useState<PA | null>(null);
  const act = async (path: string, body: unknown, ok?: string) => {
    try { const r = await post<PA>(path, body); if (ok) toast.success(ok); qc.invalidateQueries({ queryKey: ["revenue"] }); qc.invalidateQueries({ queryKey: ["cases"] }); return r; } catch (e) { toastError(e); return null; }
  };
  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row items-center justify-between"><CardTitle>Prior authorizations</CardTitle>
        <div className="flex items-center gap-2"><SimulatedBadge label="Payer decisions simulated (no X12 278)" /><NativeSelect className="h-9 w-36" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="open">Open</option><option value="approved">Approved</option><option value="denied">Denied</option><option value="all">All</option></NativeSelect></div></CardHeader>
      {q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState icon={ClipboardCheck} title="No authorizations" description="The prior-auth monitor drafts requests automatically when a signed order needs one." /> : (
        <Table><THead><TR><TH>#</TH><TH>Service</TH><TH>Patient</TH><TH>Payer</TH><TH>Status</TH><TH>Valid</TH><TH /></TR></THead>
          <TBody>{q.data.map((p) => (
            <TR key={p.id}><TD className="tabular">{p.number}</TD><TD><p className="font-medium">{p.service_description}</p><p className="text-xs text-muted-foreground">{p.service_code}{p.source === "monitor" && " · drafted automatically"}</p></TD>
              <TD>{p.patient.name}</TD><TD>{p.payer_name ?? "—"}</TD><TD><Badge variant={PA_V[p.status] ?? "neutral"}>{titleCase(p.status)}</Badge>{p.denial_reason && <p className="text-xs text-destructive">{p.denial_reason}</p>}</TD>
              <TD className="text-table">{p.valid_to ? `${fmtDate(p.valid_from)} → ${fmtDate(p.valid_to)}` : "—"}{p.auth_number && <p className="text-xs text-muted-foreground">{p.auth_number}</p>}</TD>
              <TD className="text-right">{["draft", "pended"].includes(p.status) && <Button size="xs" variant="outline" onClick={() => setOpen(p)}>Work</Button>}</TD></TR>))}</TBody></Table>
      )}
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent size="md"><DialogHeader><DialogTitle>Authorization #{open?.number} — {open?.service_description}</DialogTitle><DialogDescription>{open?.patient.name} · {open?.payer_name} · {open?.clinical_summary}</DialogDescription></DialogHeader>
          <ul className="space-y-2">{open?.checklist.map((c) => (
            <li key={c.key}><label className="flex items-center gap-2 text-body"><Checkbox checked={c.done} onCheckedChange={async (v) => { const r = await act(`/prior-auths/${open.id}/checklist`, { key: c.key, done: !!v }); if (r) setOpen(r); }} />{c.label}{c.key === "prior_treatment" && <span className="text-xs text-muted-foreground">(if required)</span>}</label></li>))}</ul>
          <DialogFooter><Button variant="ghost" onClick={async () => { if (await act(`/prior-auths/${open!.id}/cancel`, {}, "Cancelled")) setOpen(null); }}>Cancel request</Button>
            <Button onClick={async () => { const r = await act(`/prior-auths/${open!.id}/submit`, {}); if (r) { toast[r.status === "approved" ? "success" : "warning"](`Payer response: ${r.status}${r.denial_reason ? ` — ${r.denial_reason}` : ""}`); setOpen(null); } }}><BadgeCheck />Submit to payer</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function ClaimReview() {
  const qc = useQueryClient();
  const { can } = useAuth();
  const claims = useQuery({ queryKey: ["revenue", "claims"], queryFn: () => get<{ items: Claim[] } | Claim[]>("/claims", { status: "draft" }) });
  const list = Array.isArray(claims.data) ? claims.data : claims.data?.items ?? [];
  const [sel, setSel] = React.useState<Claim | null>(null);
  const f = useQuery({ queryKey: ["revenue", "findings", sel?.id], queryFn: () => get<Finding[]>(`/claims/${sel!.id}/findings`), enabled: !!sel });
  const [busy, setBusy] = React.useState(false);
  const [closing, setClosing] = React.useState<Finding | null>(null);
  const [note, setNote] = React.useState("");
  const [how, setHow] = React.useState("resolved");
  return (
    <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
      <Card className="h-fit overflow-hidden"><CardHeader><CardTitle>Claims on hold</CardTitle></CardHeader>
        {claims.isLoading ? <LoadingRows /> : !list.length ? <EmptyState icon={BadgeCheck} title="No held claims" /> : (
          <ul className="divide-y">{list.map((c) => (
            <li key={c.id}><button className={`w-full px-4 py-2.5 text-left hover:bg-muted/40 ${sel?.id === c.id ? "bg-accent" : ""}`} onClick={() => setSel(c)}>
              <p className="text-body font-medium">{c.claim_number} · {c.patient?.name}</p><p className="text-xs text-muted-foreground">{c.payer_name} · {fmtMoney(c.total_charge_cents)} · {c.scrub_errors.length} scrub issue(s)</p></button></li>))}</ul>
        )}
      </Card>
      {!sel ? <Card className="grid place-items-center p-10 text-table text-muted-foreground">Select a claim to review</Card> : (
        <Card>
          <CardHeader className="flex-row items-center justify-between"><CardTitle>{sel.claim_number} — findings</CardTitle>
            {can("billing:write") && <Button size="sm" loading={busy} onClick={async () => { setBusy(true); try { await post(`/claims/${sel.id}/review`); toast.success("Review complete"); qc.invalidateQueries({ queryKey: ["revenue", "findings", sel.id] }); } catch (e) { toastError(e); } finally { setBusy(false); } }}><FileSearch />Run review</Button>}</CardHeader>
          <CardContent className="space-y-3">
            {sel.scrub_errors.length > 0 && <div className="rounded-lg border border-warning/40 bg-warning-soft/40 p-3 text-table"><p className="mb-1 font-medium">Scrubber</p><ul className="list-disc pl-5">{sel.scrub_errors.map((e) => <li key={e}>{e}</li>)}</ul></div>}
            {!f.data?.length ? <p className="text-table text-muted-foreground">No findings yet — run a review.</p> : (
              <ul className="divide-y">{f.data.map((x) => (
                <li key={x.id} className="flex flex-wrap items-start gap-3 py-2.5">
                  <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><Badge variant={SEV_V[x.severity]}>{titleCase(x.severity)}</Badge>{x.source === "ai" && <Badge variant="ai"><Bot />AI{x.model ? ` · ${x.model}` : ""}</Badge>}<span className="text-body font-medium">{titleCase(x.code.replace(/_/g, " "))}</span>{x.status !== "open" && <Badge variant="outline">{x.status}</Badge>}</div>
                    <p className="text-table text-muted-foreground">{x.message}{x.resolution_note ? ` · ${x.resolution_note}` : ""}</p></div>
                  {x.status === "open" && can("billing:write") && <Button size="xs" variant="outline" onClick={() => { setClosing(x); setNote(""); setHow("resolved"); }}>Close</Button>}
                </li>))}</ul>
            )}
            <p className="text-xs text-muted-foreground">Findings never change codes or submit claims. Blockers must be resolved by a person before submission. <Link className="text-primary hover:underline" to="/billing">Open billing</Link></p>
          </CardContent>
        </Card>
      )}
      <Dialog open={!!closing} onOpenChange={(o) => !o && setClosing(null)}>
        <DialogContent size="sm"><DialogHeader><DialogTitle>Close finding</DialogTitle><DialogDescription>{closing?.message}</DialogDescription></DialogHeader>
          <Field label="Outcome"><NativeSelect value={how} onChange={(e) => setHow(e.target.value)}><option value="resolved">Resolved (issue fixed)</option><option value="dismissed">Dismissed (not an issue)</option></NativeSelect></Field>
          <Field label="Note" required><Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <DialogFooter><Button variant="outline" onClick={() => setClosing(null)}>Cancel</Button><Button disabled={note.trim().length < 3} onClick={async () => { try { await post(`/claim-findings/${closing!.id}`, { status: how, note }); setClosing(null); qc.invalidateQueries({ queryKey: ["revenue"] }); } catch (e) { toastError(e); } }}>Save</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CodingQueue() {
  const q = useQuery({ queryKey: ["revenue", "coding"], queryFn: () => get<Coding[]>("/coding/queue") });
  return (
    <Card className="overflow-hidden"><CardHeader><CardTitle>Completed encounters not yet billed</CardTitle></CardHeader>
      {q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState icon={ListChecks} title="Nothing waiting for coding" /> : (
        <Table><THead><TR><TH>Patient</TH><TH>Type</TH><TH>Service date</TH><TH>Charges</TH><TH>Missing</TH></TR></THead>
          <TBody>{q.data.map((r) => (
            <TR key={r.encounter_id}><TD><p className="font-medium">{r.patient.name}</p><p className="text-xs text-muted-foreground">{r.patient.mrn}</p></TD><TD>{titleCase(r.type.replace("_", " "))}</TD>
              <TD>{fmtDate(r.service_date)} <span className="text-xs text-muted-foreground">({fromNow(r.service_date)})</span></TD><TD className="tabular">{r.charge_codes.join(", ") || "—"} {r.charges_cents ? `· ${fmtMoney(r.charges_cents)}` : ""}</TD>
              <TD>{r.missing.length ? r.missing.map((m) => <Badge key={m} variant="warning" className="mr-1">{m}</Badge>) : <Badge variant="success">Ready to bill</Badge>}</TD></TR>))}</TBody></Table>
      )}
    </Card>
  );
}

function DenialsPanel() {
  const q = useQuery({ queryKey: ["revenue", "denials"], queryFn: () => get<Denials>("/revenue/denials") });
  const d = q.data;
  return (
    <Card><CardHeader className="flex-row items-center justify-between"><CardTitle className="flex items-center gap-2"><TrendingDown className="size-4" />Denials (180 days)</CardTitle>
      {d && <span className="text-table text-muted-foreground">{d.denied} of {d.submitted} submitted · {d.denial_rate_pct ?? "—"}%</span>}</CardHeader>
      <CardContent>{!d ? <LoadingRows /> : !d.by_reason.length ? <EmptyState icon={ShieldAlert} title="No denials" /> : (
        <Table><THead><TR><TH>Reason</TH><TH>Payer</TH><TH className="text-right">Claims</TH><TH className="text-right">Charges</TH><TH>Prevented by</TH></TR></THead>
          <TBody>{d.by_reason.map((r, i) => <TR key={i}><TD><span className="font-medium">{r.code}</span> {r.reason}</TD><TD>{r.payer}</TD><TD className="text-right tabular">{r.count}</TD><TD className="text-right tabular">{fmtMoney(r.charges_cents)}</TD><TD className="text-table text-muted-foreground">{r.prevention ?? "—"}</TD></TR>)}</TBody></Table>
      )}</CardContent></Card>
  );
}
