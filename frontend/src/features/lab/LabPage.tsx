import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertOctagon, Beaker, CheckCircle2, ClipboardList, PackageCheck, Pencil, TestTube, XCircle } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { EmptyState, ErrorState, LoadingRows, PageHeader, SimulatedBadge, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, fromNow } from "@/lib/format";
import { cn, titleCase } from "@/lib/utils";

type Result = { id: string; name: string; value: string; unit: string | null; reference_range: string | null; flag: string; status: string; entered_by_id: string | null; entered_by: string | null; verified_by: string | null; supersedes_id: string | null; correction_reason: string | null };
type Spec = { id: string; accession_number: number; status: string; specimen_type: string; container: string | null; order: { id: string; title: string; priority: string }; patient: { id: string; name: string; mrn: string }; collected_at: string; received_at: string | null; template: { name: string; unit: string | null; reference_range: string | null }[]; results: Result[] };
type WL = { to_collect: { order_id: string; title: string; priority: string; signed_at: string; patient: { id: string; name: string; mrn: string }; location: string }[]; specimens: Spec[]; critical_unacknowledged: { id: string; summary: string; minutes: number }[] };
type Crit = { id: string; summary: string; order_id: string; patient: { id: string; name: string; mrn: string }; created_at: string; mine: boolean };

const FLAG: Record<string, React.ComponentProps<typeof Badge>["variant"]> = { normal: "neutral", high: "warning", low: "warning", abnormal: "warning", critical_high: "danger", critical_low: "danger" };

export function LabPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const labUser = can("lab:work") || can("lab:verify");
  const tab = params.get("tab") ?? (labUser ? "collect" : "critical");
  const wl = useQuery({ queryKey: ["lab", "worklist"], queryFn: () => get<WL>("/lab/worklist"), enabled: labUser, refetchInterval: 30_000 });
  const crit = useQuery({ queryKey: ["lab", "critical"], queryFn: () => get<Crit[]>("/lab/critical") });
  return (
    <>
      <PageHeader title="Laboratory" description="Collection → accession → results → independent verification. Critical values need clinician read-back acknowledgment. Unverified results never reach patients."
        actions={<SimulatedBadge label="No analyzer interface — manual entry" />} />
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v })}>
        <TabsList>
          {labUser && <TabsTrigger value="collect">To collect {wl.data ? <Count n={wl.data.to_collect.length} /> : null}</TabsTrigger>}
          {labUser && <TabsTrigger value="bench">Bench & verification {wl.data ? <Count n={wl.data.specimens.length} /> : null}</TabsTrigger>}
          <TabsTrigger value="critical">Critical results {crit.data?.length ? <Count n={crit.data.length} alert /> : null}</TabsTrigger>
        </TabsList>
        <TabsContent value="collect">{wl.isError ? <ErrorState error={wl.error} /> : <Collect data={wl.data} />}</TabsContent>
        <TabsContent value="bench"><Bench data={wl.data} /></TabsContent>
        <TabsContent value="critical"><Critical data={crit.data} loading={crit.isLoading} /></TabsContent>
      </Tabs>
    </>
  );
}

function Count({ n, alert }: { n: number; alert?: boolean }) {
  return <span className={cn("ml-1.5 rounded-full px-1.5 text-[11px] tabular", alert ? "bg-destructive text-white" : "bg-muted text-muted-foreground")}>{n}</span>;
}

function useRefresh() {
  const qc = useQueryClient();
  return () => { qc.invalidateQueries({ queryKey: ["lab"] }); qc.invalidateQueries({ queryKey: ["cases"] }); qc.invalidateQueries({ queryKey: ["orders"] }); };
}

function Collect({ data }: { data?: WL }) {
  const refresh = useRefresh();
  const [o, setO] = React.useState<WL["to_collect"][number] | null>(null);
  const [f, setF] = React.useState({ specimen_type: "blood", container: "" });
  if (!data) return <LoadingRows />;
  return (
    <Card className="overflow-hidden">
      {!data.to_collect.length ? <EmptyState icon={TestTube} title="Nothing to collect" /> : (
        <Table><THead><TR><TH>Priority</TH><TH>Test</TH><TH>Patient</TH><TH>Location</TH><TH>Ordered</TH><TH /></TR></THead>
          <TBody>{data.to_collect.map((x) => (
            <TR key={x.order_id}><TD>{x.priority === "stat" ? <Badge variant="danger">STAT</Badge> : <Badge variant="outline">Routine</Badge>}</TD><TD className="font-medium">{x.title}</TD>
              <TD>{x.patient.name} <span className="text-xs text-muted-foreground">{x.patient.mrn}</span></TD><TD>{x.location}</TD><TD>{fromNow(x.signed_at)}</TD>
              <TD className="text-right"><Button size="xs" onClick={() => { setO(x); setF({ specimen_type: "blood", container: "" }); }}><TestTube />Collect</Button></TD></TR>))}</TBody></Table>
      )}
      <Dialog open={!!o} onOpenChange={(v) => !v && setO(null)}>
        <DialogContent size="sm"><DialogHeader><DialogTitle>Collect — {o?.title}</DialogTitle><DialogDescription>{o?.patient.name} · confirm two identifiers before collecting.</DialogDescription></DialogHeader>
          <Field label="Specimen"><NativeSelect value={f.specimen_type} onChange={(e) => setF({ ...f, specimen_type: e.target.value })}>{["blood", "urine", "swab", "csf", "stool", "sputum", "other"].map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}</NativeSelect></Field>
          <Field label="Container / tube"><Input value={f.container} onChange={(e) => setF({ ...f, container: e.target.value })} placeholder="e.g. Green top (lithium heparin)" /></Field>
          <DialogFooter><Button variant="outline" onClick={() => setO(null)}>Cancel</Button><Button onClick={async () => {
            try { const s = await post<Spec>("/lab/collect", { order_id: o!.order_id, specimen_type: f.specimen_type, container: f.container || null }); toast.success(`Collected — accession ${s.accession_number}`); setO(null); refresh(); } catch (e) { toastError(e); }
          }}>Collect & label</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function Bench({ data }: { data?: WL }) {
  const { me, can } = useAuth();
  const refresh = useRefresh();
  const [entry, setEntry] = React.useState<Spec | null>(null);
  const [rows, setRows] = React.useState<Record<string, string>[]>([]);
  const [fix, setFix] = React.useState<Result | null>(null);
  const [fx, setFx] = React.useState({ value: "", flag: "normal", reason: "" });
  if (!data) return <LoadingRows />;
  const act = async (path: string, body: unknown, ok: string) => { try { await post(path, body); toast.success(ok); refresh(); return true; } catch (e) { toastError(e); return false; } };
  const openEntry = (s: Spec) => {
    const existing = s.results.filter((r) => r.status === "preliminary");
    setRows(existing.length ? existing.map((r) => ({ name: r.name, value: r.value, unit: r.unit ?? "", reference_range: r.reference_range ?? "", flag: r.flag }))
      : (s.template.length ? s.template : [{ name: "", unit: "", reference_range: "" }]).map((t) => ({ name: t.name ?? "", value: "", unit: t.unit ?? "", reference_range: t.reference_range ?? "", flag: "normal" })));
    setEntry(s);
  };
  return (
    <div className="space-y-3">
      {!data.specimens.length ? <Card><EmptyState icon={Beaker} title="No specimens in progress" /></Card> : data.specimens.map((s) => {
        const prelim = s.results.filter((r) => r.status === "preliminary");
        const mineEntered = prelim.some((r) => r.entered_by_id === me?.user.id);
        return (
          <Card key={s.id}>
            <CardHeader className="flex-row flex-wrap items-center justify-between gap-2 py-3">
              <div><CardTitle className="text-[15px]">#{s.accession_number} · {s.order.title} {s.order.priority === "stat" && <Badge variant="danger" className="ml-1">STAT</Badge>}</CardTitle>
                <p className="text-xs text-muted-foreground">{s.patient.name} ({s.patient.mrn}) · {s.specimen_type}{s.container ? ` · ${s.container}` : ""} · collected {fromNow(s.collected_at)}{s.received_at ? ` · received ${fromNow(s.received_at)}` : ""}</p></div>
              <div className="flex flex-wrap items-center gap-2"><Badge variant={s.status === "collected" ? "warning" : "info"}>{titleCase(s.status.replace("_", " "))}</Badge>
                {s.status === "collected" && can("lab:work") && <><Button size="xs" onClick={() => act(`/lab/specimens/${s.id}/receive`, {}, "Accessioned")}><PackageCheck />Receive</Button>
                  <Button size="xs" variant="ghost" onClick={() => { const reason = window.prompt("Rejection reason (e.g. hemolyzed, clotted, mislabeled)?"); if (reason) act(`/lab/specimens/${s.id}/reject`, { reason }, "Specimen rejected — recollection requested"); }}><XCircle />Reject</Button></>}
                {s.status !== "collected" && can("lab:work") && <Button size="xs" variant="outline" onClick={() => openEntry(s)}><Pencil />{prelim.length ? "Edit results" : "Enter results"}</Button>}
                {prelim.length > 0 && can("lab:verify") && <Button size="xs" disabled={mineEntered} title={mineEntered ? "Results must be verified by a different person" : undefined} onClick={() => act(`/lab/specimens/${s.id}/verify`, {}, "Verified and sent to the clinician")}><CheckCircle2 />Verify</Button>}
              </div>
            </CardHeader>
            {s.results.length > 0 && (
              <Table><THead><TR><TH>Test</TH><TH>Value</TH><TH>Reference</TH><TH>Flag</TH><TH>Status</TH><TH>By</TH><TH /></TR></THead>
                <TBody>{s.results.map((r) => (
                  <TR key={r.id} className={cn(r.status === "superseded" && "opacity-50")}><TD className="font-medium">{r.name}</TD><TD className="tabular">{r.value} {r.unit}</TD><TD className="text-muted-foreground">{r.reference_range ?? "—"}</TD>
                    <TD><Badge variant={FLAG[r.flag] ?? "neutral"}>{titleCase(r.flag.replace("_", " "))}</Badge></TD><TD>{titleCase(r.status)}{r.correction_reason && <p className="text-xs text-muted-foreground">Correction: {r.correction_reason}</p>}</TD>
                    <TD className="text-xs text-muted-foreground">{r.entered_by ?? "—"}{r.verified_by ? ` · verified ${r.verified_by}` : ""}</TD>
                    <TD>{r.status === "final" && can("lab:work") && <Button size="xs" variant="ghost" onClick={() => { setFix(r); setFx({ value: r.value, flag: r.flag, reason: "" }); }}>Correct</Button>}</TD></TR>))}</TBody></Table>
            )}
          </Card>);
      })}
      <Dialog open={!!entry} onOpenChange={(v) => !v && setEntry(null)}>
        <DialogContent size="lg"><DialogHeader><DialogTitle>Results — #{entry?.accession_number} {entry?.order.title}</DialogTitle><DialogDescription>Saved as preliminary. A different technologist verifies before the clinician sees them.</DialogDescription></DialogHeader>
          <div className="space-y-2">{rows.map((r, i) => (
            <div key={i} className="grid grid-cols-12 gap-2">
              <Input className="col-span-3" aria-label="Test" value={r.name} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} placeholder="Test" />
              <Input className="col-span-2" aria-label={`${r.name} value`} value={r.value} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} placeholder="Value" />
              <Input className="col-span-2" aria-label="Unit" value={r.unit} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, unit: e.target.value } : x)))} placeholder="Unit" />
              <Input className="col-span-2" aria-label="Reference" value={r.reference_range} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, reference_range: e.target.value } : x)))} placeholder="Ref" />
              <NativeSelect className="col-span-3" aria-label={`${r.name} flag`} value={r.flag} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, flag: e.target.value } : x)))}>{Object.keys(FLAG).map((k) => <option key={k} value={k}>{titleCase(k.replace("_", " "))}</option>)}</NativeSelect>
            </div>))}
            <Button size="xs" variant="ghost" onClick={() => setRows([...rows, { name: "", value: "", unit: "", reference_range: "", flag: "normal" }])}>Add row</Button>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setEntry(null)}>Cancel</Button>
            <Button disabled={!rows.some((r) => r.name && r.value)} onClick={async () => { if (await act(`/lab/specimens/${entry!.id}/results`, rows.filter((r) => r.name && r.value).map((r) => ({ ...r, unit: r.unit || null, reference_range: r.reference_range || null })), "Results saved (preliminary)")) setEntry(null); }}>Save preliminary</Button></DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={!!fix} onOpenChange={(v) => !v && setFix(null)}>
        <DialogContent size="sm"><DialogHeader><DialogTitle>Correct {fix?.name}</DialogTitle><DialogDescription>The original value is kept as history. The correction needs independent verification and the clinician re-reviews it.</DialogDescription></DialogHeader>
          <div className="grid grid-cols-2 gap-3"><Field label="Corrected value"><Input value={fx.value} onChange={(e) => setFx({ ...fx, value: e.target.value })} /></Field>
            <Field label="Flag"><NativeSelect value={fx.flag} onChange={(e) => setFx({ ...fx, flag: e.target.value })}>{Object.keys(FLAG).map((k) => <option key={k} value={k}>{titleCase(k.replace("_", " "))}</option>)}</NativeSelect></Field></div>
          <Field label="Reason" required><Textarea rows={2} value={fx.reason} onChange={(e) => setFx({ ...fx, reason: e.target.value })} /></Field>
          <DialogFooter><Button variant="outline" onClick={() => setFix(null)}>Cancel</Button><Button disabled={fx.reason.trim().length < 5} onClick={async () => { if (await act(`/lab/results/${fix!.id}/correct`, fx, "Correction entered — awaiting verification")) setFix(null); }}>Submit correction</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Critical({ data, loading }: { data?: Crit[]; loading: boolean }) {
  const { can } = useAuth();
  const refresh = useRefresh();
  const [ack, setAck] = React.useState<Crit | null>(null);
  const [rb, setRb] = React.useState("");
  if (loading) return <LoadingRows />;
  return (
    <Card className="overflow-hidden">
      <CardHeader><CardTitle className="flex items-center gap-2"><AlertOctagon className="size-4 text-destructive" />Critical results awaiting acknowledgment</CardTitle></CardHeader>
      {!data?.length ? <EmptyState icon={CheckCircle2} title="All critical results acknowledged" /> : (
        <ul className="divide-y">{data.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <div className="min-w-0 flex-1"><p className="text-[13.5px] font-semibold text-destructive">{a.summary}</p><p className="text-xs text-muted-foreground">{a.patient.name} ({a.patient.mrn}) · verified {fmtDateTime(a.created_at)} ({fromNow(a.created_at)}){a.mine ? " · your patient" : ""}</p></div>
            {can("clinical:write") && (a.mine || can("orders:sign")) && <Button size="sm" onClick={() => { setAck(a); setRb(""); }}><ClipboardList />Acknowledge</Button>}
          </li>))}</ul>
      )}
      <Dialog open={!!ack} onOpenChange={(v) => !v && setAck(null)}>
        <DialogContent size="sm"><DialogHeader><DialogTitle>Acknowledge critical result</DialogTitle><DialogDescription>{ack?.summary} — {ack?.patient.name}. Record the read-back and your action.</DialogDescription></DialogHeader>
          <Field label="Read-back / action" required><Textarea rows={3} value={rb} onChange={(e) => setRb(e.target.value)} placeholder="e.g. Potassium 6.9 read back; ordering repeat BMP and ECG" /></Field>
          <DialogFooter><Button variant="outline" onClick={() => setAck(null)}>Cancel</Button><Button disabled={rb.trim().length < 3} onClick={async () => { try { await post(`/lab/critical/${ack!.id}/acknowledge`, { read_back: rb }); toast.success("Acknowledged"); setAck(null); refresh(); } catch (e) { toastError(e); } }}>Acknowledge</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

