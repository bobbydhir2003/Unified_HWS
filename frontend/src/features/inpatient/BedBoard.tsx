import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BedDouble, Clock, LogOut, Plus, Radio, ShieldAlert, Sparkles, UserPlus } from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { EmptyState, ErrorState, LoadingRows, PageHeader, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect } from "@/components/ui/input";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fromNow } from "@/lib/format";
import { useLiveStatus } from "@/lib/live";
import { cn } from "@/lib/utils";
import { useFacilities } from "../admin/FacilitiesPage";
import { AdmitDialog, BED_STYLE, BedStatusChip, losLabel, type StayT } from "./shared";

type BedT = { id: string; code: string; name: string; room: string | null; status: string; status_reason: string | null; since: string | null;
  stay: null | { id: string; status: string; patient_name: string; patient_id: string | null; mrn: string | null; los_hours: number | null; isolation: string | null; discharge_ordered: boolean; attending: string | null; expected_discharge_date: string | null } };
type Board = { facility: { id: string; name: string }; units: { id: string; code: string; name: string; beds: BedT[]; counts: Record<string, number> }[]; totals: Record<string, number>; occupancy_pct: number | null; pending_admissions: StayT[]; discharges_ordered: number };

export function BedBoard() {
  const facs = useFacilities();
  const hospitals = (facs.data ?? []).filter((f) => f.facility_type === "hospital");
  const [facility, setFacility] = React.useState("");
  const fid = facility || hospitals[0]?.id;
  const live = useLiveStatus();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["beds", fid], queryFn: () => get<Board>("/adt/board", { facility_id: fid }), enabled: !!fid, refetchInterval: 60_000 });
  const [bed, setBed] = React.useState<BedT | null>(null);
  const [admit, setAdmit] = React.useState(false);
  const [placing, setPlacing] = React.useState<StayT | null>(null);
  const [unitFilter, setUnitFilter] = React.useState("");
  const d = q.data;
  return (
    <>
      <PageHeader title="Bed board" description="Live bed status and placement. Occupancy is enforced by the database — a bed can never hold two patients."
        actions={<div className="flex items-center gap-2">
          <Badge variant={live ? "success" : "neutral"}><Radio className={cn(live && "animate-pulse")} />{live ? "Live" : "Polling"}</Badge>
          {hospitals.length > 1 && <NativeSelect className="w-56" aria-label="Facility" value={fid ?? ""} onChange={(e) => setFacility(e.target.value)}>{hospitals.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}</NativeSelect>}
          {can("adt:write") && <Button onClick={() => setAdmit(true)}><UserPlus />Request admission</Button>}
        </div>} />
      {facs.isSuccess && !hospitals.length ? <EmptyState icon={BedDouble} title="No hospital facility in your scope" /> : q.isError ? <ErrorState error={q.error} retry={q.refetch} /> : !d ? <LoadingRows rows={8} /> : (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Mini label="Occupancy" value={d.occupancy_pct == null ? "—" : `${d.occupancy_pct}%`} />
            {(["available", "occupied", "cleaning", "blocked"] as const).map((k) => <Mini key={k} label={BED_STYLE[k].label} value={d.totals[k]} dot={BED_STYLE[k].dot} />)}
            <Mini label="Discharges ordered" value={d.discharges_ordered} />
          </div>
          <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
            <div className="space-y-4">
              <div className="flex flex-wrap gap-1.5">{[{ id: "", name: "All units" }, ...d.units].map((u) => <button key={u.id} onClick={() => setUnitFilter(u.id)} className={cn("rounded-md px-2.5 py-1 text-[13px] font-medium text-muted-foreground hover:bg-muted", unitFilter === u.id && "bg-accent text-accent-foreground")}>{u.name}</button>)}</div>
              {d.units.filter((u) => !unitFilter || u.id === unitFilter).map((u) => (
                <Card key={u.id}>
                  <CardHeader className="flex-row items-center justify-between py-3"><CardTitle className="text-[15px]">{u.name}</CardTitle>
                    <span className="text-xs text-muted-foreground tabular">{u.counts.occupied}/{u.beds.length - u.counts.blocked} occupied · {u.counts.available} open · {u.counts.cleaning} cleaning</span></CardHeader>
                  <CardContent className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 2xl:grid-cols-6">
                    {u.beds.map((b) => (
                      <button key={b.id} onClick={() => setBed(b)} className={cn("min-h-[84px] rounded-lg border p-2.5 text-left text-xs transition focus-visible:outline-2 focus-visible:outline-primary", BED_STYLE[b.status]?.tile)}
                        aria-label={`Bed ${b.code}, ${BED_STYLE[b.status]?.label}${b.stay ? `, ${b.stay.patient_name}` : ""}`}>
                        <div className="flex items-center justify-between"><span className="font-semibold">{b.name}</span><BedStatusChip status={b.status} /></div>
                        {b.stay ? (
                          <div className="mt-1.5 space-y-0.5">
                            <p className="truncate text-[13px] font-medium">{b.stay.patient_name}</p>
                            <p className="text-muted-foreground">LOS {losLabel(b.stay.los_hours)}</p>
                            <div className="flex flex-wrap gap-1">{b.stay.discharge_ordered && <Badge variant="info" className="px-1 py-0 text-[10px]"><LogOut className="size-3" />Discharge</Badge>}{b.stay.isolation && <Badge variant="warning" className="px-1 py-0 text-[10px]"><ShieldAlert className="size-3" />{b.stay.isolation}</Badge>}</div>
                          </div>
                        ) : b.status === "cleaning" ? <p className="mt-1.5 flex items-center gap-1 text-muted-foreground"><Clock className="size-3" />{fromNow(b.since)}</p>
                          : b.status === "blocked" ? <p className="mt-1.5 line-clamp-2 text-muted-foreground">{b.status_reason}</p> : <p className="mt-1.5 text-muted-foreground">Ready</p>}
                      </button>))}
                  </CardContent>
                </Card>))}
            </div>
            <Card className="h-fit">
              <CardHeader><CardTitle className="flex items-center gap-2"><Clock className="size-4" />Waiting for a bed</CardTitle></CardHeader>
              <CardContent>{!d.pending_admissions.length ? <p className="text-[13px] text-muted-foreground">No pending admissions.</p> : (
                <ul className="space-y-2">{d.pending_admissions.map((s) => (
                  <li key={s.id} className={cn("rounded-lg border p-3 text-[13px]", (s.waiting_hours ?? 0) >= 1 && "border-warning/50 bg-warning-soft/30")}>
                    <p className="font-medium">{s.patient.name}</p><p className="text-xs text-muted-foreground">{s.reason}</p>
                    <p className="mt-1 text-xs">{s.level_of_care.replace("_", "-")} · {s.admit_source.toUpperCase()} · waiting <span className="font-medium tabular">{losLabel(s.waiting_hours)}</span></p>
                    {can("adt:write") && <Button size="sm" className="mt-2" onClick={() => setPlacing(s)}><BedDouble />Assign bed</Button>}
                  </li>))}</ul>
              )}</CardContent>
            </Card>
          </div>
        </>
      )}
      <BedDialog bed={bed} board={d} onClose={() => setBed(null)} />
      {placing && d && <PlaceDialog stay={placing} board={d} onClose={() => setPlacing(null)} />}
      <AdmitDialog open={admit} onOpenChange={setAdmit} facilityId={fid} />
    </>
  );
}

function Mini({ label, value, dot }: { label: string; value: React.ReactNode; dot?: string }) {
  return <div className="rounded-xl border bg-card px-3 py-2.5"><p className="flex items-center gap-1.5 text-xs text-muted-foreground">{dot && <span className={cn("size-2 rounded-full", dot)} />}{label}</p><p className="text-xl font-semibold tabular">{value}</p></div>;
}

function useAct() {
  const qc = useQueryClient();
  return async (path: string, body: unknown, ok: string) => {
    try { await post(path, body); toast.success(ok); qc.invalidateQueries({ queryKey: ["beds"] }); qc.invalidateQueries({ queryKey: ["adt"] }); return true; } catch (e) { toastError(e); return false; }
  };
}

function BedDialog({ bed, board, onClose }: { bed: BedT | null; board?: Board; onClose: () => void }) {
  const { can } = useAuth();
  const act = useAct();
  const nav = useNavigate();
  const [reason, setReason] = React.useState("");
  const [admit, setAdmit] = React.useState(false);
  const [target, setTarget] = React.useState("");
  if (!bed) return null;
  const free = (board?.units ?? []).flatMap((u) => u.beds.filter((b) => b.status === "available" && b.id !== bed.id).map((b) => ({ ...b, unit: u.name })));
  const manage = can("beds:manage");
  return (
    <>
      <Dialog open={!!bed && !admit} onOpenChange={(o) => !o && onClose()}>
        <DialogContent size="sm">
          <DialogHeader><DialogTitle>Bed {bed.code}</DialogTitle><DialogDescription><BedStatusChip status={bed.status} />{bed.status_reason ? ` · ${bed.status_reason}` : ""}</DialogDescription></DialogHeader>
          {bed.stay ? (
            <div className="space-y-3 text-[13.5px]">
              <p><span className="font-medium">{bed.stay.patient_name}</span> {bed.stay.mrn && <span className="text-xs text-muted-foreground">{bed.stay.mrn}</span>}</p>
              <p className="text-muted-foreground">Attending {bed.stay.attending ?? "—"} · LOS {losLabel(bed.stay.los_hours)}</p>
              {can("adt:write") && (
                <Field label="Transfer to"><div className="flex gap-2"><NativeSelect value={target} onChange={(e) => setTarget(e.target.value)}><option value="">Choose a bed…</option>{free.map((b) => <option key={b.id} value={b.id}>{b.unit} · {b.name}</option>)}</NativeSelect>
                  <Button disabled={!target} onClick={async () => { if (await act(`/adt/stays/${bed.stay!.id}/transfer`, { bed_id: target }, "Patient transferred")) onClose(); }}>Transfer</Button></div></Field>
              )}
              <Button variant="outline" onClick={() => { onClose(); nav(`/inpatients/${bed.stay!.id}`); }}>Open patient stay</Button>
            </div>
          ) : (
            <div className="space-y-3">
              {bed.status === "available" && can("adt:write") && <Button className="w-full" onClick={() => setAdmit(true)}><Plus />Admit a patient here</Button>}
              {manage && bed.status === "cleaning" && <Button className="w-full" onClick={async () => { if (await act(`/beds/${bed.id}/status`, { to: "available" }, "Bed is clean and available")) onClose(); }}><Sparkles />Mark clean</Button>}
              {manage && bed.status === "blocked" && <Button className="w-full" onClick={async () => { if (await act(`/beds/${bed.id}/status`, { to: "available" }, "Bed back in service")) onClose(); }}>Return to service</Button>}
              {manage && bed.status === "available" && (
                <Field label="Block this bed" hint="e.g. equipment broken, isolation"><div className="flex gap-2"><Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason" />
                  <Button variant="outline" disabled={reason.trim().length < 3} onClick={async () => { if (await act(`/beds/${bed.id}/status`, { to: "blocked", reason }, "Bed blocked")) { setReason(""); onClose(); } }}>Block</Button></div></Field>
              )}
            </div>
          )}
          <DialogFooter><Button variant="ghost" onClick={onClose}>Close</Button></DialogFooter>
        </DialogContent>
      </Dialog>
      {admit && <AdmitDialog open={admit} onOpenChange={(o) => { setAdmit(o); if (!o) onClose(); }} facilityId={board?.facility.id} bedId={bed.id} />}
    </>
  );
}

function PlaceDialog({ stay, board, onClose }: { stay: StayT; board: Board; onClose: () => void }) {
  const act = useAct();
  const [bedId, setBedId] = React.useState("");
  const free = board.units.flatMap((u) => u.beds.filter((b) => b.status === "available").map((b) => ({ ...b, unit: u })));
  const preferred = free.filter((b) => stay.level_of_care === "icu" ? b.unit.code === "ICU" : b.unit.code !== "ICU" && b.unit.code !== "ED");
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="sm">
        <DialogHeader><DialogTitle>Assign a bed — {stay.patient.name}</DialogTitle><DialogDescription>{stay.reason} · {stay.level_of_care.replace("_", "-")}{stay.isolation ? ` · ${stay.isolation} isolation` : ""}</DialogDescription></DialogHeader>
        <Field label="Bed" hint={`${preferred.length} matching open bed(s) shown first`}>
          <NativeSelect value={bedId} onChange={(e) => setBedId(e.target.value)}><option value="">Choose…</option>
            {[...preferred, ...free.filter((b) => !preferred.includes(b))].map((b) => <option key={b.id} value={b.id}>{b.unit.name} · {b.name}</option>)}</NativeSelect>
        </Field>
        <p className="text-xs text-muted-foreground">Placing the patient admits them, starts the inpatient record, and updates every bed board live. <Link className="text-primary hover:underline" to={`/inpatients/${stay.id}`}>Open request</Link></p>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button disabled={!bedId} onClick={async () => { if (await act(`/adt/stays/${stay.id}/assign-bed`, { bed_id: bedId }, "Patient placed")) onClose(); }}>Assign & admit</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
