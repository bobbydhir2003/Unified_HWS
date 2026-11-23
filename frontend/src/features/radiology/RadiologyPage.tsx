import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, CheckCircle2, FilePen, Play, ScanLine, Signature, SquareCheckBig } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState, LoadingRows, PageHeader, SimulatedBadge, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fromNow } from "@/lib/format";
import { titleCase } from "@/lib/utils";

type Study = { id: string; accession_number: number; modality: string; status: string; priority: string; order: { id: string; title: string; clinical_question: string | null; contrast: boolean | null };
  patient: { id: string; name: string; mrn: string }; scheduled_at: string | null; completed_at: string | null; technologist: string | null; findings: string | null; impression: string | null;
  critical_finding: boolean; drafted_by: string | null; signed_by: string | null; viewer_url: string | null; pacs: string };
type WL = { to_schedule: { order_id: string; title: string; priority: string; modality: string; clinical_question: string | null; signed_at: string; patient: { name: string; mrn: string } }[]; studies: Study[] };

const STATUS_V: Record<string, React.ComponentProps<typeof Badge>["variant"]> = { scheduled: "neutral", arrived: "info", in_progress: "primary", completed: "warning", preliminary: "ai", final: "success" };

export function RadiologyPage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["radiology", "worklist"], queryFn: () => get<WL>("/radiology/worklist"), refetchInterval: 30_000 });
  const [rep, setRep] = React.useState<Study | null>(null);
  const [f, setF] = React.useState({ findings: "", impression: "", critical_finding: false });
  const act = async (path: string, body: unknown, ok: string, method: "post" | "put" = "post") => {
    try { await (method === "put" ? put(path, body) : post(path, body)); toast.success(ok); qc.invalidateQueries({ queryKey: ["radiology"] }); qc.invalidateQueries({ queryKey: ["cases"] }); return true; } catch (e) { toastError(e); return false; }
  };
  const d = q.data;
  return (
    <>
      <PageHeader title="Radiology" description="Imaging worklist from order to signed report. Images stay in the PACS; reports become part of the chart once a radiologist signs."
        actions={<SimulatedBadge label="PACS not connected — no image viewer" />} />
      {q.isError ? <ErrorState error={q.error} retry={q.refetch} /> : !d ? <LoadingRows rows={6} /> : (
        <div className="space-y-4">
          <Card className="overflow-hidden">
            <CardHeader><CardTitle>Orders to schedule</CardTitle></CardHeader>
            {!d.to_schedule.length ? <EmptyState icon={CalendarPlus} title="No imaging orders waiting" /> : (
              <Table><THead><TR><TH>Priority</TH><TH>Exam</TH><TH>Patient</TH><TH>Clinical question</TH><TH>Ordered</TH><TH /></TR></THead>
                <TBody>{d.to_schedule.map((o) => (
                  <TR key={o.order_id}><TD><Badge variant={o.priority === "stat" ? "danger" : o.priority === "urgent" ? "warning" : "outline"}>{titleCase(o.priority)}</Badge></TD>
                    <TD className="font-medium">{o.modality} · {o.title}</TD><TD>{o.patient.name} <span className="text-xs text-muted-foreground">{o.patient.mrn}</span></TD>
                    <TD className="max-w-72 truncate text-table">{o.clinical_question}</TD><TD>{fromNow(o.signed_at)}</TD>
                    <TD className="text-right"><Button size="xs" variant="outline" onClick={() => act("/radiology/studies", { order_id: o.order_id }, "Study scheduled")}><CalendarPlus />Schedule</Button></TD></TR>))}</TBody></Table>
            )}
          </Card>
          <Card className="overflow-hidden">
            <CardHeader><CardTitle>Studies</CardTitle></CardHeader>
            {!d.studies.length ? <EmptyState icon={ScanLine} title="No active studies" /> : (
              <Table><THead><TR><TH>Accession</TH><TH>Exam</TH><TH>Patient</TH><TH>Status</TH><TH /></TR></THead>
                <TBody>{d.studies.map((s) => (
                  <TR key={s.id}><TD className="tabular">#{s.accession_number}</TD>
                    <TD><p className="font-medium">{s.modality} · {s.order.title} {s.priority === "stat" && <Badge variant="danger" className="ml-1">STAT</Badge>}</p><p className="text-xs text-muted-foreground">{s.order.clinical_question}</p></TD>
                    <TD>{s.patient.name} <span className="text-xs text-muted-foreground">{s.patient.mrn}</span></TD>
                    <TD><Badge variant={STATUS_V[s.status] ?? "neutral"}>{titleCase(s.status.replace("_", " "))}</Badge>{s.critical_finding && <Badge variant="danger" className="ml-1">Critical</Badge>}</TD>
                    <TD><div className="flex justify-end gap-1">
                      {s.status === "scheduled" && <Button size="xs" variant="outline" onClick={() => act(`/radiology/studies/${s.id}/status`, { to: "arrived" }, "Patient arrived")}>Arrived</Button>}
                      {s.status === "arrived" && <Button size="xs" variant="outline" onClick={() => act(`/radiology/studies/${s.id}/status`, { to: "in_progress" }, "Exam started")}><Play />Start exam</Button>}
                      {s.status === "in_progress" && <Button size="xs" variant="outline" onClick={() => act(`/radiology/studies/${s.id}/status`, { to: "completed" }, "Exam completed — ready to read")}><SquareCheckBig />Complete</Button>}
                      {["completed", "preliminary"].includes(s.status) && can("radiology:sign") && <Button size="xs" variant="outline" onClick={() => { setRep(s); setF({ findings: s.findings ?? "", impression: s.impression ?? "", critical_finding: s.critical_finding }); }}><FilePen />{s.status === "preliminary" ? "Edit report" : "Report"}</Button>}
                      {s.status === "preliminary" && can("radiology:sign") && <Button size="xs" variant="outline" onClick={() => act(`/radiology/studies/${s.id}/sign`, {}, "Report signed and sent")}><Signature />Sign</Button>}
                    </div></TD></TR>))}</TBody></Table>
            )}
          </Card>
        </div>
      )}
      <Dialog open={!!rep} onOpenChange={(o) => !o && setRep(null)}>
        <DialogContent size="lg"><DialogHeader><DialogTitle>Report — {rep?.modality} {rep?.order.title}</DialogTitle><DialogDescription>{rep?.patient.name} · Clinical question: {rep?.order.clinical_question}</DialogDescription></DialogHeader>
          <Field label="Findings" required><Textarea rows={7} value={f.findings} onChange={(e) => setF({ ...f, findings: e.target.value })} /></Field>
          <Field label="Impression" required><Textarea rows={3} value={f.impression} onChange={(e) => setF({ ...f, impression: e.target.value })} /></Field>
          <label className="flex items-center gap-2 text-body"><Checkbox checked={f.critical_finding} onCheckedChange={(v) => setF({ ...f, critical_finding: !!v })} />Critical finding — requires ordering clinician acknowledgment</label>
          <DialogFooter><Button variant="outline" onClick={() => setRep(null)}>Cancel</Button>
            <Button disabled={f.findings.trim().length < 3 || f.impression.trim().length < 3} onClick={async () => { if (await act(`/radiology/studies/${rep!.id}/report`, f, "Draft saved", "put")) setRep(null); }}><CheckCircle2 />Save draft</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
