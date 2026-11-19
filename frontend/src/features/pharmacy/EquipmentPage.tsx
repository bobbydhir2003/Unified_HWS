import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Wrench } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, LoadingRows, PageHeader, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { NativeSelect, Textarea } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import { titleCase } from "@/lib/utils";

type Eq = { id: string; name: string; asset_tag: string; category: string; manufacturer: string | null; status: string; location: string | null; maintenance_interval_days: number;
  last_maintenance_on: string | null; next_maintenance_due: string | null; overdue: boolean; due_soon: boolean };

const STATUS_V: Record<string, React.ComponentProps<typeof Badge>["variant"]> = { in_service: "success", maintenance: "warning", out_of_service: "danger", retired: "neutral" };

export function EquipmentPage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["equipment"], queryFn: () => get<Eq[]>("/equipment") });
  const [log, setLog] = React.useState<Eq | null>(null);
  const [f, setF] = React.useState({ kind: "preventive", result: "passed", notes: "" });
  return (
    <>
      <PageHeader title="Equipment" description="Medical equipment registry with preventive-maintenance schedule. Overdue and upcoming maintenance open cases automatically." />
      <Card className="overflow-hidden">
        {q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState icon={Wrench} title="No equipment registered" /> : (
          <Table><THead><TR><TH>Equipment</TH><TH>Location</TH><TH>Status</TH><TH>Last service</TH><TH>Next due</TH><TH /></TR></THead>
            <TBody>{q.data.map((e) => (
              <TR key={e.id}><TD><p className="font-medium">{e.name}</p><p className="text-xs text-muted-foreground">{e.asset_tag}{e.manufacturer ? ` · ${e.manufacturer}` : ""}</p></TD>
                <TD>{e.location ?? "—"}</TD><TD><Badge variant={STATUS_V[e.status]}>{titleCase(e.status.replace(/_/g, " "))}</Badge></TD>
                <TD>{e.last_maintenance_on ? fmtDate(e.last_maintenance_on) : "—"}</TD>
                <TD>{e.next_maintenance_due ? fmtDate(e.next_maintenance_due) : "—"} {e.overdue ? <Badge variant="danger" className="ml-1">Overdue</Badge> : e.due_soon ? <Badge variant="warning" className="ml-1">Due soon</Badge> : null}</TD>
                <TD className="text-right">{can("inventory:write") && e.status !== "retired" && <Button size="xs" variant="outline" onClick={() => { setLog(e); setF({ kind: "preventive", result: "passed", notes: "" }); }}><Wrench />Log service</Button>}</TD></TR>))}</TBody></Table>
        )}
      </Card>
      <Dialog open={!!log} onOpenChange={(o) => !o && setLog(null)}>
        <DialogContent size="sm"><DialogHeader><DialogTitle>Log service — {log?.name}</DialogTitle><DialogDescription>{log?.asset_tag} · every {log?.maintenance_interval_days} days</DialogDescription></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Type"><NativeSelect value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>{["preventive", "repair", "inspection", "calibration"].map((k) => <option key={k} value={k}>{titleCase(k)}</option>)}</NativeSelect></Field>
            <Field label="Result"><NativeSelect value={f.result} onChange={(e) => setF({ ...f, result: e.target.value })}><option value="passed">Passed</option><option value="repaired">Repaired</option><option value="failed">Failed (take out of service)</option></NativeSelect></Field>
          </div>
          <Field label="Notes"><Textarea rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
          <DialogFooter><Button variant="outline" onClick={() => setLog(null)}>Cancel</Button>
            <Button onClick={async () => { try { await post(`/equipment/${log!.id}/maintenance`, { ...f, notes: f.notes || null }); toast.success("Service logged"); setLog(null); qc.invalidateQueries({ queryKey: ["equipment"] }); qc.invalidateQueries({ queryKey: ["cases"] }); } catch (e) { toastError(e); } }}>Save</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
