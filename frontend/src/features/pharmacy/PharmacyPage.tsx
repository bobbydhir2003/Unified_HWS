import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRightLeft, Boxes, ClipboardCheck, PackagePlus, Pill, Search, ShieldCheck, ShoppingCart, Trash2 } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { EmptyState, ErrorState, LoadingRows, PageHeader, SimulatedBadge, Stat, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, fmtMoney, fromNow } from "@/lib/format";
import { cn, titleCase } from "@/lib/utils";
import { CaseDrawer, CaseRow, type CaseT } from "../ops/ops";
import { AskAI } from "@/features/ai/AskAI";

type Item = { id: string; name: string; sku: string; ndc: string | null; kind: string; unit: string; strength: string | null; form: string | null; is_controlled: boolean; on_hand: number; reorder_point: number; avg_daily_use: number; days_of_supply: number | null; nearest_expiry: string | null; expiring_soon: boolean; stock_status: string };
type Lot = { lot_id: string; lot_number: string; expiry_date: string | null; expired: boolean; location_id: string; location: string; quantity: number };
type Detail = { item: Item & { supplier: string | null }; lots: Lot[]; movements: { id: string; kind: string; quantity: number; balance_after: number; lot: string; location: string; by: string | null; reason: string | null; at: string; approved: boolean }[];
  recommendation: { on_hand: number; avg_daily_use: number; days_of_supply: number | null; recommended_qty: number; method: string; lead_time_days: number }; purchase_requests: PR[] };
type PR = { id: string; number: number; item_id: string; item: string; unit: string; quantity: number; received_quantity: number; status: string; source: string; reason: string | null; supplier: string | null; estimated_cost_cents: number; created_at: string; po_reference: string | null; deliver_to_location_id: string | null; can_decide: boolean };
type Loc = { id: string; name: string; code: string };
type Ver = { order_id: string; title: string; details: Record<string, string>; patient: { id: string; name: string; mrn: string }; prescriber: string | null; signed_at: string; waiting_minutes: number | null; safety_warnings: unknown[] | null };
type Report = { valuation: { kind: string; value_cents: number; units: number }[]; expiring_30d_value_cents: number; waste_30d_value_cents: number; low_stock_items: number; pending_verifications: number | null };

const STATUS: Record<string, React.ComponentProps<typeof Badge>["variant"]> = { ok: "success", low: "warning", out: "danger" };

export function PharmacyPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "inventory";
  const itemId = params.get("item");
  const [openCase, setOpenCase] = React.useState<string | null>(null);
  const report = useQuery({ queryKey: ["inventory", "report"], queryFn: () => get<Report>("/inventory/report") });
  const cases = useQuery({ queryKey: ["cases", "pharmacy"], queryFn: async () => [...await get<CaseT[]>("/cases", { category: "pharmacy" }), ...await get<CaseT[]>("/cases", { category: "inventory" })] });
  const set = (k: string, v: string | null) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n, { replace: true }); };
  const r = report.data;
  return (
    <>
      <PageHeader title="Pharmacy & inventory" description="Verify medication orders, keep stock safe and reorder in time. The Pharmacy Watchdog flags expiring stock, low stock and unusual use, and drafts reorders for approval."
        actions={<AskAI agent="pharmacy_watchdog" label="Summarize inventory risks" variant="outline" question="Summarize medication stock and expiry risks that need pharmacy review today, most urgent first." />} />
      <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Watchdog cases" icon={AlertTriangle} tone="warning" value={cases.data?.length ?? "…"} sub="Expiry, low stock, unusual use" />
        <Stat label="Below reorder point" icon={Boxes} tone="danger" value={r?.low_stock_items ?? "…"} />
        <Stat label="Expiring ≤ 30 days" icon={Pill} tone="primary" value={r ? fmtMoney(r.expiring_30d_value_cents) : "…"} sub={r ? `Waste last 30 days ${fmtMoney(r.waste_30d_value_cents)}` : undefined} />
        <Stat label="Orders awaiting verification" icon={ClipboardCheck} tone="ai" value={r?.pending_verifications ?? "—"} />
      </div>
      <Tabs value={tab} onValueChange={(v) => set("tab", v === "inventory" ? null : v)}>
        <TabsList><TabsTrigger value="inventory">Inventory</TabsTrigger><TabsTrigger value="watchdog">Watchdog {cases.data?.length ? <span className="ml-1.5 rounded-full bg-warning px-1.5 text-[11px]">{cases.data.length}</span> : null}</TabsTrigger>
          <TabsTrigger value="purchasing">Purchasing</TabsTrigger>{can("pharmacy:read") && <TabsTrigger value="verify">Verification</TabsTrigger>}</TabsList>
        <TabsContent value="inventory"><InventoryTable onOpen={(id) => set("item", id)} /></TabsContent>
        <TabsContent value="watchdog"><Card className="overflow-hidden">{cases.isLoading ? <LoadingRows /> : !cases.data?.length ? <EmptyState icon={ShieldCheck} title="No Watchdog alerts" /> : <ul className="divide-y">{cases.data.map((c) => <CaseRow key={c.id} c={c} onOpen={setOpenCase} />)}</ul>}</Card></TabsContent>
        <TabsContent value="purchasing"><Purchasing /></TabsContent>
        <TabsContent value="verify"><Verification /></TabsContent>
      </Tabs>
      <ItemDrawer itemId={itemId} onClose={() => set("item", null)} />
      <CaseDrawer caseId={openCase} onClose={() => setOpenCase(null)} />
    </>
  );
}

function InventoryTable({ onOpen }: { onOpen: (id: string) => void }) {
  const [q, setQ] = React.useState("");
  const [kind, setKind] = React.useState("");
  const [status, setStatus] = React.useState("all");
  const items = useQuery({ queryKey: ["inventory", "items", q, kind, status], queryFn: () => get<Item[]>("/inventory/items", { q: q || undefined, kind: kind || undefined, status }) });
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap gap-2 border-b p-3">
        <div className="relative"><Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" /><Input className="h-9 w-64 pl-8" placeholder="Search name, SKU or NDC…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search inventory" /></div>
        <NativeSelect className="h-9 w-36" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Type"><option value="">All types</option><option value="medication">Medications</option><option value="supply">Supplies</option></NativeSelect>
        <NativeSelect className="h-9 w-40" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="all">All stock</option><option value="low">Low / out</option><option value="expiring">Expiring ≤ 30 d</option></NativeSelect>
      </div>
      {items.isLoading ? <LoadingRows /> : items.isError ? <ErrorState error={items.error} /> : !items.data?.length ? <EmptyState icon={Boxes} title="No items match" /> : (
        <Table><THead><TR><TH>Item</TH><TH className="text-right">On hand</TH><TH className="text-right">Reorder at</TH><TH className="text-right">Avg use/day</TH><TH className="text-right">Days of supply</TH><TH>Nearest expiry</TH><TH>Status</TH></TR></THead>
          <TBody>{items.data.map((i) => (
            <TR key={i.id} className="cursor-pointer hover:bg-muted/40" onClick={() => onOpen(i.id)}>
              <TD><p className="font-medium">{i.name} {i.strength && <span className="font-normal text-muted-foreground">{i.strength}</span>}</p><p className="text-xs text-muted-foreground">{i.sku}{i.is_controlled && <Badge variant="danger" className="ml-1.5 px-1 py-0 text-[10px]">Controlled</Badge>}</p></TD>
              <TD className="text-right tabular">{i.on_hand} <span className="text-xs text-muted-foreground">{i.unit}</span></TD><TD className="text-right tabular">{i.reorder_point}</TD>
              <TD className="text-right tabular">{i.avg_daily_use}</TD><TD className={cn("text-right tabular", i.days_of_supply != null && i.days_of_supply < 3 && "font-medium text-destructive")}>{i.days_of_supply ?? "—"}</TD>
              <TD className={cn(i.expiring_soon && "font-medium text-warning")}>{i.nearest_expiry ? fmtDate(i.nearest_expiry) : "—"}</TD>
              <TD><Badge variant={STATUS[i.stock_status]}>{titleCase(i.stock_status)}</Badge></TD>
            </TR>))}</TBody></Table>
      )}
    </Card>
  );
}

function ItemDrawer({ itemId, onClose }: { itemId: string | null; onClose: () => void }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const d = useQuery({ queryKey: ["inventory", "item", itemId], queryFn: () => get<Detail>(`/inventory/items/${itemId}`), enabled: !!itemId });
  const locs = useQuery({ queryKey: ["inventory", "locations"], queryFn: () => get<Loc[]>("/inventory/locations"), enabled: !!itemId });
  const [action, setAction] = React.useState<null | { kind: "transfer" | "dispense" | "waste" | "receive" | "request"; lot?: Lot }>(null);
  const [f, setF] = React.useState<Record<string, string>>({});
  const refresh = () => { qc.invalidateQueries({ queryKey: ["inventory"] }); qc.invalidateQueries({ queryKey: ["cases"] }); qc.invalidateQueries({ queryKey: ["purchase"] }); };
  const run = async (path: string, body: unknown, ok: string) => {
    try { const r = await post<{ status?: string; message?: string }>(path, body); toast.success(r?.status === "pending_approval" ? "Sent for a second person's approval" : ok); setAction(null); setF({}); refresh(); } catch (e) { toastError(e); }
  };
  const it = d.data?.item;
  return (
    <Dialog open={!!itemId} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="max-w-2xl overflow-y-auto" aria-describedby={undefined}>
        {!d.data || !it ? <div className="p-6"><LoadingRows /></div> : (
          <div className="space-y-5 p-5 pr-12">
            <div><DialogTitle className="text-[17px] font-semibold">{it.name} {it.strength}</DialogTitle><p className="text-xs text-muted-foreground">{it.sku}{it.ndc ? ` · NDC ${it.ndc}` : ""} · {it.supplier ?? "no supplier"}{it.is_controlled ? " · controlled substance" : ""}</p></div>
            <div className="rounded-lg border bg-muted/30 p-3 text-[13px]">
              <p><span className="font-medium">Reorder recommendation:</span> {d.data.recommendation.recommended_qty} {it.unit} · {d.data.recommendation.avg_daily_use}/day average · {d.data.recommendation.days_of_supply ?? "—"} days of supply · lead time {d.data.recommendation.lead_time_days} d</p>
              <p className="mt-0.5 text-xs text-muted-foreground">Method: {d.data.recommendation.method}. A simple statistical baseline — not a validated forecast.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {can("inventory:write") && <Button size="sm" variant="outline" onClick={() => setAction({ kind: "receive" })}><PackagePlus />Receive</Button>}
              {can("inventory:write") && <Button size="sm" variant="outline" onClick={() => { setF({ quantity: String(d.data!.recommendation.recommended_qty) }); setAction({ kind: "request" }); }}><ShoppingCart />Request purchase</Button>}
            </div>
            <section>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Lots on hand</h4>
              {!d.data.lots.length ? <p className="text-[13px] text-muted-foreground">No stock.</p> : (
                <Table><THead><TR><TH>Lot</TH><TH>Location</TH><TH>Expiry</TH><TH className="text-right">Qty</TH><TH /></TR></THead>
                  <TBody>{d.data.lots.map((l) => (
                    <TR key={l.lot_id + l.location_id}><TD className="font-medium">{l.lot_number}</TD><TD>{l.location}</TD>
                      <TD className={cn(l.expired && "font-medium text-destructive")}>{l.expiry_date ? fmtDate(l.expiry_date) : "—"}{l.expired && " (expired)"}</TD><TD className="text-right tabular">{l.quantity}</TD>
                      <TD><div className="flex justify-end gap-1">{can("inventory:write") && <>
                        <Button size="xs" variant="ghost" onClick={() => setAction({ kind: "transfer", lot: l })} aria-label="Transfer"><ArrowRightLeft /></Button>
                        {!l.expired && <Button size="xs" variant="ghost" onClick={() => setAction({ kind: "dispense", lot: l })}>Dispense</Button>}
                        <Button size="xs" variant="ghost" onClick={() => setAction({ kind: "waste", lot: l })} aria-label="Waste"><Trash2 /></Button></>}</div></TD></TR>))}</TBody></Table>
              )}
            </section>
            <section>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Ledger (most recent)</h4>
              <ul className="space-y-1 text-[13px]">{d.data.movements.slice(0, 15).map((m) => <li key={m.id} className="flex flex-wrap gap-x-2"><span className="w-28 text-muted-foreground">{fmtDateTime(m.at)}</span><span className="font-medium">{titleCase(m.kind.replace("_", " "))} {m.quantity}</span><span className="text-muted-foreground">lot {m.lot} · {m.location} · bal {m.balance_after}{m.by ? ` · ${m.by}` : ""}{m.approved ? " · approved" : ""}</span></li>)}</ul>
            </section>
          </div>
        )}
      </SheetContent>
      <Dialog open={!!action} onOpenChange={(o) => !o && setAction(null)}>
        <DialogContent size="sm">
          <DialogHeader><DialogTitle>{action && { transfer: "Transfer stock", dispense: "Dispense", waste: "Waste stock", receive: "Receive stock", request: "Request purchase" }[action.kind]}</DialogTitle>
            {action?.kind === "waste" && <DialogDescription>A second person with the right permission must approve before stock is removed.</DialogDescription>}
            {action?.lot && <DialogDescription>Lot {action.lot.lot_number} · {action.lot.location} · {action.lot.quantity} on hand</DialogDescription>}</DialogHeader>
          {(action?.kind === "transfer" || action?.kind === "receive") && <Field label={action.kind === "transfer" ? "To location" : "Into location"}><NativeSelect value={f.loc ?? ""} onChange={(e) => setF({ ...f, loc: e.target.value })}><option value="">Choose…</option>{locs.data?.filter((l) => l.id !== action.lot?.location_id).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</NativeSelect></Field>}
          {action?.kind === "receive" && <div className="grid grid-cols-2 gap-3"><Field label="Lot number" required><Input value={f.lot ?? ""} onChange={(e) => setF({ ...f, lot: e.target.value })} /></Field><Field label="Expiry"><Input type="date" value={f.exp ?? ""} onChange={(e) => setF({ ...f, exp: e.target.value })} /></Field></div>}
          <Field label="Quantity" required><Input inputMode="numeric" value={f.quantity ?? ""} onChange={(e) => setF({ ...f, quantity: e.target.value })} /></Field>
          {(action?.kind === "waste" || action?.kind === "transfer" || action?.kind === "request") && <Field label="Reason" required={action.kind === "waste"}><Textarea rows={2} value={f.reason ?? ""} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field>}
          <DialogFooter><Button variant="outline" onClick={() => setAction(null)}>Cancel</Button>
            <Button disabled={!Number(f.quantity) || (action?.kind === "waste" && (f.reason ?? "").trim().length < 5)} onClick={() => {
              const a = action!; const qty = Number(f.quantity);
              if (a.kind === "transfer") run("/inventory/transfer", { lot_id: a.lot!.lot_id, from_location_id: a.lot!.location_id, to_location_id: f.loc, quantity: qty, reason: f.reason || null }, "Transferred");
              if (a.kind === "dispense") run("/inventory/dispense", { lot_id: a.lot!.lot_id, location_id: a.lot!.location_id, quantity: qty }, "Dispensed");
              if (a.kind === "waste") run("/inventory/adjust", { lot_id: a.lot!.lot_id, location_id: a.lot!.location_id, quantity: qty, action: "waste", reason: f.reason }, "Wasted");
              if (a.kind === "receive") run("/inventory/receive", { item_id: it!.id, location_id: f.loc, lot_number: f.lot, expiry_date: f.exp || null, quantity: qty }, "Received");
              if (a.kind === "request") run("/purchase-requests", { item_id: it!.id, quantity: qty, reason: f.reason || null }, "Purchase request submitted");
            }}>Confirm</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Dialog>
  );
}

function Purchasing() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["purchase", "list"], queryFn: () => get<PR[]>("/purchase-requests") });
  const locs = useQuery({ queryKey: ["inventory", "locations"], queryFn: () => get<Loc[]>("/inventory/locations") });
  const { can } = useAuth();
  const [recv, setRecv] = React.useState<PR | null>(null);
  const [f, setF] = React.useState({ lot: "", exp: "", loc: "" });
  const act = async (path: string, body: unknown, ok: string) => { try { await post(path, body); toast.success(ok); qc.invalidateQueries({ queryKey: ["purchase"] }); qc.invalidateQueries({ queryKey: ["inventory"] }); qc.invalidateQueries({ queryKey: ["cases"] }); } catch (e) { toastError(e); } };
  const V: Record<string, React.ComponentProps<typeof Badge>["variant"]> = { submitted: "warning", approved: "info", ordered: "primary", received: "success", rejected: "neutral" };
  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row items-center justify-between"><CardTitle>Purchase requests</CardTitle><SimulatedBadge label="Supplier ordering simulated" /></CardHeader>
      {q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState icon={ShoppingCart} title="No purchase requests" /> : (
        <Table><THead><TR><TH>#</TH><TH>Item</TH><TH className="text-right">Qty</TH><TH>Source</TH><TH>Supplier</TH><TH className="text-right">Est. cost</TH><TH>Status</TH><TH /></TR></THead>
          <TBody>{q.data.map((p) => (
            <TR key={p.id}><TD className="tabular">{p.number}</TD><TD><p className="font-medium">{p.item}</p><p className="text-xs text-muted-foreground">{fromNow(p.created_at)}{p.reason ? ` · ${p.reason}` : ""}</p></TD>
              <TD className="text-right tabular">{p.quantity}{p.received_quantity ? ` (${p.received_quantity} rec.)` : ""}</TD><TD>{p.source === "watchdog" ? <Badge variant="ai">Watchdog</Badge> : "Manual"}</TD>
              <TD>{p.supplier ?? "—"}</TD><TD className="text-right tabular">{fmtMoney(p.estimated_cost_cents)}</TD><TD><Badge variant={V[p.status] ?? "neutral"}>{titleCase(p.status)}</Badge>{p.po_reference && <p className="text-xs text-muted-foreground">{p.po_reference}</p>}</TD>
              <TD><div className="flex justify-end gap-1">
                {p.can_decide && <><Button size="xs" onClick={() => act(`/purchase-requests/${p.id}/decide`, { approve: true }, "Approved")}>Approve</Button><Button size="xs" variant="ghost" onClick={() => { const note = window.prompt("Reason for rejecting?"); if (note) act(`/purchase-requests/${p.id}/decide`, { approve: false, note }, "Rejected"); }}>Reject</Button></>}
                {p.status === "approved" && can("inventory:write") && <Button size="xs" variant="outline" onClick={() => act(`/purchase-requests/${p.id}/order`, {}, "Order sent (simulated)")}>Send order</Button>}
                {["approved", "ordered"].includes(p.status) && can("inventory:write") && <Button size="xs" variant="outline" onClick={() => { setRecv(p); setF({ lot: "", exp: "", loc: p.deliver_to_location_id ?? "" }); }}>Receive</Button>}
              </div></TD></TR>))}</TBody></Table>
      )}
      <Dialog open={!!recv} onOpenChange={(o) => !o && setRecv(null)}>
        <DialogContent size="sm"><DialogHeader><DialogTitle>Receive #{recv?.number} — {recv?.item}</DialogTitle></DialogHeader>
          <Field label="Into location"><NativeSelect value={f.loc} onChange={(e) => setF({ ...f, loc: e.target.value })}><option value="">Choose…</option>{locs.data?.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</NativeSelect></Field>
          <div className="grid grid-cols-2 gap-3"><Field label="Lot number" required><Input value={f.lot} onChange={(e) => setF({ ...f, lot: e.target.value })} /></Field><Field label="Expiry"><Input type="date" value={f.exp} onChange={(e) => setF({ ...f, exp: e.target.value })} /></Field></div>
          <DialogFooter><Button variant="outline" onClick={() => setRecv(null)}>Cancel</Button><Button disabled={!f.lot || !f.loc} onClick={async () => { await act("/inventory/receive", { item_id: recv!.item_id, location_id: f.loc, lot_number: f.lot, expiry_date: f.exp || null, quantity: recv!.quantity - recv!.received_quantity, purchase_request_id: recv!.id }, "Received into stock"); setRecv(null); }}>Receive {recv ? recv.quantity - recv.received_quantity : ""}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function Verification() {
  const qc = useQueryClient();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["pharmacy", "verifications"], queryFn: () => get<Ver[]>("/pharmacy/verifications") });
  const decide = async (v: Ver, status: string) => {
    const note = status === "verified" ? null : window.prompt(status === "rejected" ? "Why is this order rejected?" : "What needs clarification?");
    if (status !== "verified" && !note) return;
    try { await post("/pharmacy/verifications", { order_id: v.order_id, status, note }); toast.success(`Order ${status}`); qc.invalidateQueries({ queryKey: ["pharmacy"] }); qc.invalidateQueries({ queryKey: ["inventory", "report"] }); } catch (e) { toastError(e); }
  };
  return (
    <Card className="overflow-hidden">
      <CardHeader><CardTitle>Inpatient medication orders awaiting verification</CardTitle></CardHeader>
      {q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState icon={ClipboardCheck} title="Queue is clear" /> : (
        <ul className="divide-y">{q.data.map((v) => (
          <li key={v.order_id} className="flex flex-wrap items-start gap-3 px-4 py-3">
            <div className="min-w-0 flex-1"><p className="text-[13.5px] font-medium">{v.title}</p>
              <p className="text-xs text-muted-foreground">{v.patient.name} ({v.patient.mrn}) · {v.prescriber ?? "—"} · signed {fromNow(v.signed_at)}</p>
              {v.safety_warnings?.length ? <Badge variant="warning" className="mt-1"><AlertTriangle />{v.safety_warnings.length} safety warning(s) overridden</Badge> : null}</div>
            {can("pharmacy:verify") && <div className="flex gap-1"><Button size="sm" onClick={() => decide(v, "verified")}><ShieldCheck />Verify</Button><Button size="sm" variant="outline" onClick={() => decide(v, "clarify")}>Clarify</Button><Button size="sm" variant="ghost" onClick={() => decide(v, "rejected")}>Reject</Button></div>}
          </li>))}</ul>
      )}
    </Card>
  );
}

