import { useQuery } from "@tanstack/react-query";
import { Stethoscope } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get } from "@/lib/api";
import { fmtDateTime, fmtDob } from "@/lib/format";
import type { Encounter } from "@/lib/types";
import { cn } from "@/lib/utils";

export function EncountersList() {
  const [status, setStatus] = React.useState<"in_progress" | "completed">("in_progress");
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["my-encounters", status], queryFn: () => get<Encounter[]>("/encounters", { status, mine: true }) });
  return (
    <>
      <PageHeader title="My visits" description="Encounters where you are the rendering provider." />
      <div className="mb-3 inline-flex rounded-lg bg-muted p-0.5">
        {(["in_progress", "completed"] as const).map((s) => (
          <button key={s} onClick={() => setStatus(s)} className={cn("rounded-md px-3 py-1 text-table font-medium text-muted-foreground", status === s && "bg-card text-foreground shadow-sm")}>
            {s === "in_progress" ? "Open" : "Completed"}
          </button>
        ))}
      </div>
      <Card className="overflow-hidden">
        {q.error ? <ErrorState error={q.error} retry={q.refetch} /> : q.isLoading ? <LoadingRows /> : !q.data?.length ? (
          <EmptyState icon={Stethoscope} title={status === "in_progress" ? "No open visits" : "No completed visits"} description="Start a visit from the schedule, front desk or a patient's chart." />
        ) : (
          <Table>
            <THead><TR><TH>Patient</TH><TH>Started</TH><TH>Chief complaint</TH><TH>Diagnoses</TH><TH>Note</TH></TR></THead>
            <TBody>
              {q.data.map((e) => (
                <TR key={e.id} data-clickable tabIndex={0} onClick={() => navigate(`/encounters/${e.id}`)} onKeyDown={(ev) => ev.key === "Enter" && navigate(`/encounters/${e.id}`)}>
                  <TD><span className="font-medium">{e.patient.name}</span><span className="block text-xs text-muted-foreground tabular">{fmtDob(e.patient.date_of_birth)} · {e.patient.mrn}</span></TD>
                  <TD className="whitespace-nowrap">{fmtDateTime(e.started_at)}</TD>
                  <TD>{e.chief_complaint ?? "—"}</TD>
                  <TD><div className="flex flex-wrap gap-1">{e.diagnoses.map((d) => <Badge key={d.id} variant="outline">{d.code}</Badge>)}</div></TD>
                  <TD>{e.note_status === "signed" ? <Badge variant="success">Signed</Badge> : e.note_status === "draft" ? <Badge variant="warning">Draft</Badge> : <Badge>None</Badge>}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
    </>
  );
}
