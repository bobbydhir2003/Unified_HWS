import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { ClipboardList, FileSignature, Plus } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { EmptyState, ErrorState, LoadingRows, PageHeader, SimulatedBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import type { Page } from "@/lib/types";
import { cn } from "@/lib/utils";
import { flagClass, flagLabel, NewOrderDialog, type Order, OrderDrawer, OrderStatusBadge, SignOrderDialog, TYPE_ICON } from "./shared";

const QUEUES: [string, string][] = [["to_sign", "To sign"], ["results", "Results to review"], ["pending", "Awaiting results"], ["referrals", "Referrals"], ["all", "All orders"]];

function OrdersTable({ orders, onOpen, showPatient = true }: { orders: Order[]; onOpen: (o: Order) => void; showPatient?: boolean }) {
  return (
    <Table>
      <THead><TR><TH>Order</TH>{showPatient && <TH>Patient</TH>}<TH className="hidden md:table-cell">Ordered</TH><TH className="hidden lg:table-cell">By</TH><TH>Status</TH></TR></THead>
      <TBody>
        {orders.map((o) => {
          const Icon = TYPE_ICON[o.order_type];
          const abnormal = o.results.filter((r) => r.flag !== "normal").length;
          return (
            <TR key={o.id} data-clickable tabIndex={0} onClick={() => onOpen(o)} onKeyDown={(e) => e.key === "Enter" && onOpen(o)}>
              <TD>
                <span className="flex items-center gap-2 font-medium"><Icon className="size-4 shrink-0 text-muted-foreground" />{o.title}</span>
                {abnormal > 0 && <span className="ml-6 text-xs text-destructive">{abnormal} abnormal</span>}
              </TD>
              {showPatient && <TD><span className="font-medium">{o.patient.name}</span><span className="block text-xs text-muted-foreground tabular">MRN {o.patient.mrn}</span></TD>}
              <TD className="hidden whitespace-nowrap text-muted-foreground md:table-cell">{fmtDateTime(o.created_at)}</TD>
              <TD className="hidden lg:table-cell">{o.signed_by ?? o.ordered_by}</TD>
              <TD><OrderStatusBadge o={o} /></TD>
            </TR>
          );
        })}
      </TBody>
    </Table>
  );
}

export function OrdersPage() {
  const [params, setParams] = useSearchParams();
  const { can } = useAuth();
  const queue = params.get("queue") ?? (can("orders:sign") ? "to_sign" : "pending");
  const [mine, setMine] = React.useState(false);
  const [openId, setOpenId] = React.useState<string | null>(null);
  const counts = useQuery({ queryKey: ["orders-counts"], queryFn: () => get<Record<string, number>>("/orders-counts"), refetchInterval: 20_000 });
  const q = useQuery({ queryKey: ["orders", "worklist", queue, mine], queryFn: () => get<Page<Order>>("/orders", { queue, mine }), placeholderData: keepPreviousData });
  const open = q.data?.items.find((o) => o.id === openId) ?? null;
  return (
    <>
      <PageHeader title="Orders" description="Prescriptions, labs, imaging and referrals across your patients." actions={<SimulatedBadge label="External transmission simulated" />} />
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-1 border-b p-3">
          {QUEUES.map(([k, l]) => (
            <button key={k} onClick={() => setParams({ queue: k })} className={cn("flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-table font-medium text-muted-foreground hover:bg-muted", queue === k && "bg-accent text-accent-foreground")}>
              {l}{!!counts.data?.[k] && <span className={cn("rounded-full px-1.5 text-label tabular", k === "results" || k === "to_sign" ? "bg-warning text-white" : "bg-muted")}>{counts.data[k]}</span>}
            </button>
          ))}
          <label className="ml-auto flex items-center gap-2 text-table text-muted-foreground"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} className="accent-[var(--primary)]" />Only mine</label>
        </div>
        {q.error ? <ErrorState error={q.error} /> : q.isLoading ? <LoadingRows /> : !q.data?.items.length ? <EmptyState icon={ClipboardList} title="Nothing here" description="Orders appear here as they're drafted, sent and resulted." /> : (
          <OrdersTable orders={q.data.items} onOpen={(o) => setOpenId(o.id)} />
        )}
      </Card>
      <OrderDrawer order={open} onOpenChange={(v) => !v && setOpenId(null)} />
    </>
  );
}

export function EncounterOrdersCard({ patientId, encounterId, diagnosisCodes, editable }: { patientId: string; encounterId: string; diagnosisCodes: string[]; editable: boolean }) {
  const { can } = useAuth();
  const [newOpen, setNewOpen] = React.useState(false);
  const [openId, setOpenId] = React.useState<string | null>(null);
  const [signing, setSigning] = React.useState<Order | null>(null);
  const q = useQuery({ queryKey: ["orders", "encounter", encounterId], queryFn: () => get<Order[]>(`/patients/${patientId}/orders`, { encounter_id: encounterId }) });
  const open = q.data?.find((o) => o.id === openId) ?? null;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle>Orders</CardTitle>
        {editable && can("orders:write") && <Button size="xs" variant="outline" onClick={() => setNewOpen(true)}><Plus />New</Button>}
      </CardHeader>
      <CardContent>
        {!q.data?.length ? <p className="text-table text-muted-foreground">No orders for this visit.</p> : (
          <ul className="space-y-1.5">
            {q.data.map((o) => {
              const Icon = TYPE_ICON[o.order_type];
              return (
                <li key={o.id} className="flex items-center gap-2 rounded-lg border px-2.5 py-2 text-table">
                  <Icon className="size-4 shrink-0 text-muted-foreground" />
                  <button className="min-w-0 flex-1 truncate text-left font-medium hover:underline" onClick={() => setOpenId(o.id)}>{o.title}</button>
                  {o.status === "draft" && can("orders:sign") ? <Button size="xs" variant="outline" onClick={() => setSigning(o)}><FileSignature />Sign</Button> : <OrderStatusBadge o={o} />}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
      <NewOrderDialog open={newOpen} onOpenChange={setNewOpen} patientId={patientId} encounterId={encounterId} initialIndications={diagnosisCodes} />
      <OrderDrawer order={open} onOpenChange={(v) => !v && setOpenId(null)} showPatient={false} />
      <SignOrderDialog order={signing} onOpenChange={(v) => !v && setSigning(null)} />
    </Card>
  );
}

export function PatientOrdersTab({ patientId }: { patientId: string }) {
  const { can } = useAuth();
  const [type, setType] = React.useState("");
  const [newOpen, setNewOpen] = React.useState(false);
  const [openId, setOpenId] = React.useState<string | null>(null);
  const q = useQuery({ queryKey: ["orders", "patient", patientId, type], queryFn: () => get<Order[]>(`/patients/${patientId}/orders`, { order_type: type }) });
  const open = q.data?.find((o) => o.id === openId) ?? null;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <NativeSelect value={type} onChange={(e) => setType(e.target.value)} className="w-44" aria-label="Order type"><option value="">All types</option><option value="medication">Medications</option><option value="lab">Labs</option><option value="imaging">Imaging</option><option value="referral">Referrals</option></NativeSelect>
        {can("orders:write") && <Button size="sm" className="ml-auto" onClick={() => setNewOpen(true)}><Plus />New order</Button>}
      </div>
      <Card className="overflow-hidden">
        {q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState icon={ClipboardList} title="No orders" /> : <OrdersTable orders={q.data} onOpen={(o) => setOpenId(o.id)} showPatient={false} />}
      </Card>
      <NewOrderDialog open={newOpen} onOpenChange={setNewOpen} patientId={patientId} />
      <OrderDrawer order={open} onOpenChange={(v) => !v && setOpenId(null)} showPatient={false} />
    </div>
  );
}

type FlatResult = { id: string; order_id: string; panel: string; name: string; value: string; unit: string | null; reference_range: string | null; flag: string; resulted_at: string; reviewed: boolean; released: boolean; source: string };

export function PatientResultsTab({ patientId }: { patientId: string }) {
  const q = useQuery({ queryKey: ["results", patientId], queryFn: () => get<FlatResult[]>(`/patients/${patientId}/results`) });
  const [trend, setTrend] = React.useState<string | null>(null);
  const names = [...new Set((q.data ?? []).filter((r) => !Number.isNaN(Number(r.value))).map((r) => r.name))];
  const series = (q.data ?? []).filter((r) => r.name === trend).slice().reverse().map((r) => ({ label: format(parseISO(r.resulted_at), "MMM d"), value: Number(r.value) }));
  if (q.error) return <ErrorState error={q.error} />;
  if (q.isLoading) return <LoadingRows />;
  if (!q.data?.length) return <Card><EmptyState title="No lab results" description="Results appear here when ordered labs come back." /></Card>;
  return (
    <div className="space-y-4">
      {names.length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle>Trend</CardTitle>
            <NativeSelect value={trend ?? ""} onChange={(e) => setTrend(e.target.value || null)} className="w-56" aria-label="Test"><option value="">Choose a test…</option>{names.map((n) => <option key={n}>{n}</option>)}</NativeSelect>
          </CardHeader>
          {trend && (
            <CardContent className="h-52">
              {series.length < 2 ? <p className="text-table text-muted-foreground">Only one result so far.</p> : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={series} margin={{ left: -16, right: 8 }}>
                    <CartesianGrid vertical={false} stroke="var(--border)" />
                    <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} />
                    <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} domain={["auto", "auto"]} />
                    <RTooltip contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} />
                    <Line dataKey="value" name={trend} stroke="var(--primary)" strokeWidth={2} dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          )}
        </Card>
      )}
      <Card className="overflow-hidden">
        <Table>
          <THead><TR><TH>Resulted</TH><TH>Test</TH><TH>Result</TH><TH className="hidden sm:table-cell">Reference</TH><TH>Status</TH></TR></THead>
          <TBody>
            {q.data.map((r) => (
              <TR key={r.id}>
                <TD className="whitespace-nowrap text-muted-foreground">{fmtDateTime(r.resulted_at)}</TD>
                <TD><span className="font-medium">{r.name}</span><span className="block text-xs text-muted-foreground">{r.panel}</span></TD>
                <TD className={cn("tabular", flagClass(r.flag))}>{r.value} {r.unit} <span className="text-xs">{flagLabel(r.flag)}</span></TD>
                <TD className="hidden text-muted-foreground tabular sm:table-cell">{r.reference_range}</TD>
                <TD>
                  <div className="flex flex-wrap gap-1">
                    {r.reviewed ? <Badge variant="success">Reviewed</Badge> : <Badge variant="warning">Needs review</Badge>}
                    {r.released && <Badge variant="info">Released</Badge>}
                    {r.source === "simulated" && <SimulatedBadge />}
                  </div>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </Card>
    </div>
  );
}
