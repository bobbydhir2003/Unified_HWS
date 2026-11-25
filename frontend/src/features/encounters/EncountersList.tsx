import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Info, Stethoscope } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get } from "@/lib/api";
import { cn } from "@/lib/utils";

type View = "today" | "upcoming" | "in_progress" | "completed" | "documentation";
type Visit = { kind: "appointment" | "encounter"; id: string; at: string; patient: { id: string; name: string; mrn: string }; reason: string | null;
  status: string; note_status?: string; clinician: string | null; encounter_id: string | null; link: string };
type Resp = { view: View; timezone: string; scope: "mine" | "clinics"; scope_note: string | null; counts: Record<View, number>; items: Visit[] };

const VIEWS: { key: View; label: string }[] = [
  { key: "today", label: "Today" }, { key: "upcoming", label: "Upcoming" }, { key: "in_progress", label: "In progress" },
  { key: "completed", label: "Completed" }, { key: "documentation", label: "Needs documentation" },
];
const TONE: Record<string, "neutral" | "primary" | "success" | "warning" | "danger" | "info"> = {
  scheduled: "neutral", confirmed: "neutral", checked_in: "info", roomed: "info", in_progress: "primary", completed: "success", checked_out: "success", no_show: "danger",
};

/** My Visits: the clinician's appointments and encounters from the existing scheduling and encounter records. */
export function EncountersList() {
  const [params, setParams] = useSearchParams();
  const view = (VIEWS.some((v) => v.key === params.get("view")) ? params.get("view") : "today") as View;
  const q = useQuery({ queryKey: ["my-visits", view], queryFn: () => get<Resp>("/my-visits", { view }), refetchInterval: 60_000 });
  const tz = q.data?.timezone;
  const when = (at: string) => new Date(at).toLocaleString([], view === "today" ? { hour: "numeric", minute: "2-digit", timeZone: tz }
    : { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: tz });
  return (
    <>
      <PageHeader title="My Visits" description={q.data?.scope === "clinics" ? "Visits in your clinics." : "Your appointments and visits — open one to document it."} />
      {q.data?.scope_note && <p className="mb-3 flex items-start gap-2 rounded-lg border bg-subtle px-3 py-2 text-table text-muted-foreground" data-testid="visits-scope-note"><Info className="mt-0.5 size-4 shrink-0" />{q.data.scope_note}</p>}
      <nav aria-label="Visit views" className="mb-3 flex flex-wrap gap-1 rounded-lg bg-muted p-0.5 sm:inline-flex" data-testid="visit-views">
        {VIEWS.map((v) => (
          <button key={v.key} type="button" aria-pressed={view === v.key} onClick={() => setParams(v.key === "today" ? {} : { view: v.key })}
            className={cn("rounded-md px-3 py-1 text-table font-medium text-muted-foreground", view === v.key && "bg-card text-foreground shadow-sm")}>
            {v.label}{q.data ? <span className="ml-1.5 tabular text-muted-foreground">{q.data.counts[v.key]}</span> : null}
          </button>
        ))}
      </nav>
      <Card className="overflow-hidden" data-testid="visits-table">
        {q.error ? <ErrorState error={q.error} retry={q.refetch} /> : q.isLoading ? <LoadingRows /> : !q.data?.items.length ? (
          <EmptyState icon={Stethoscope} title={{ today: "No visits today", upcoming: "No upcoming visits in the next 14 days", in_progress: "No visits in progress",
            completed: "No completed visits in the last 30 days", documentation: "Nothing waiting for documentation" }[view]}
            description="Visits appear here from the schedule, the front desk and patients' charts." />
        ) : (
          <Table>
            <THead><TR><TH>{view === "today" ? "Time" : "When"}</TH><TH>Patient</TH><TH className="hidden md:table-cell">Reason</TH><TH className="hidden lg:table-cell">Clinician</TH><TH>Status</TH><TH><span className="sr-only">Action</span></TH></TR></THead>
            <TBody>
              {q.data.items.map((v) => (
                <TR key={`${v.kind}-${v.id}`} data-visit={v.kind}>
                  <TD className="whitespace-nowrap font-medium tabular">{when(v.at)}</TD>
                  <TD><Link to={`/patients/${v.patient.id}`} className="font-medium text-heading hover:underline">{v.patient.name}</Link><span className="block text-xs text-muted-foreground tabular">{v.patient.mrn}</span></TD>
                  <TD className="hidden md:table-cell">{v.reason ?? "—"}</TD>
                  <TD className="hidden lg:table-cell text-muted-foreground">{v.clinician ?? "—"}</TD>
                  <TD><div className="flex flex-wrap gap-1"><Badge variant={TONE[v.status] ?? "neutral"} className="capitalize">{v.status.replace(/_/g, " ")}</Badge>
                    {v.note_status && v.note_status !== "signed" && <Badge variant="warning">{v.note_status === "draft" ? "Note draft" : "No note"}</Badge>}
                    {v.note_status === "signed" && <Badge variant="success">Signed</Badge>}</div></TD>
                  <TD className="text-right">
                    <Button asChild size="xs" variant="outline"><Link to={v.link} data-testid="open-visit">{v.encounter_id ? "Open visit" : "Open chart"}<ArrowRight /></Link></Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
    </>
  );
}
