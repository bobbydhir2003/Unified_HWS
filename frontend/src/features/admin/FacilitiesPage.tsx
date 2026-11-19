import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BedDouble, Building2, ChevronRight, DoorOpen, Hospital, LayoutGrid, Plus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, LoadingRows, PageHeader, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect } from "@/components/ui/input";
import { get, patch, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, titleCase } from "@/lib/utils";

export type Facility = { id: string; name: string; code: string; facility_type: string; timezone: string; department_count: number; bed_count: number; settings: Record<string, unknown> };
export type Department = { id: string; facility_id: string; name: string; code: string; kind: string; is_active: boolean };
export type Loc = { id: string; facility_id: string; department_id: string | null; parent_id: string | null; kind: string; name: string; code: string; sort_order: number; is_active: boolean; bed_status: string | null };

const DEPT_KINDS = ["outpatient", "emergency", "inpatient", "icu", "surgery", "pharmacy", "laboratory", "radiology", "billing", "administration", "support"];
const FAC_TYPES = ["clinic", "hospital", "urgent_care", "surgery_center", "lab", "pharmacy"];

export function useFacilities() {
  return useQuery({ queryKey: ["facilities"], queryFn: () => get<Facility[]>("/facilities"), staleTime: 300_000 });
}

export function FacilitiesPage() {
  const fac = useFacilities();
  const [sel, setSel] = React.useState<string | null>(null);
  const current = fac.data?.find((f) => f.id === (sel ?? fac.data?.find((x) => x.facility_type === "hospital")?.id ?? fac.data?.[0]?.id));
  return (
    <>
      <PageHeader title="Facilities & locations" description="Hospital structure: facility → department → unit → room → bed. Staff access can be limited to facilities and departments." />
      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <Card className="h-fit overflow-hidden">
          {fac.isLoading ? <LoadingRows /> : <ul className="divide-y">{fac.data?.map((f) => (
            <li key={f.id}><button onClick={() => setSel(f.id)} className={cn("flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/40", current?.id === f.id && "bg-accent")}>
              {f.facility_type === "hospital" ? <Hospital className="size-4 text-primary" /> : <Building2 className="size-4 text-muted-foreground" />}
              <div className="min-w-0 flex-1"><p className="truncate text-[13.5px] font-medium">{f.name}</p><p className="text-xs text-muted-foreground">{titleCase(f.facility_type.replace("_", " "))} · {f.department_count} depts · {f.bed_count} beds</p></div>
            </button></li>))}</ul>}
        </Card>
        {current ? <FacilityDetail f={current} /> : <EmptyState title="Select a facility" />}
      </div>
    </>
  );
}

function FacilityDetail({ f }: { f: Facility }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const manage = can("clinic:manage");
  const depts = useQuery({ queryKey: ["departments", f.id], queryFn: () => get<Department[]>("/departments", { facility_id: f.id }) });
  const locs = useQuery({ queryKey: ["locations", f.id], queryFn: () => get<Loc[]>("/locations", { facility_id: f.id }) });
  const [newDept, setNewDept] = React.useState<null | { name: string; code: string; kind: string }>(null);
  const [newUnit, setNewUnit] = React.useState<null | { name: string; code: string; department_id: string }>(null);
  const [gen, setGen] = React.useState<null | { unit: Loc; rooms: string; beds: string; start: string }>(null);
  const units = (locs.data ?? []).filter((l) => !l.parent_id);
  const children = (id: string) => (locs.data ?? []).filter((l) => l.parent_id === id);
  const deptName = (id: string | null) => depts.data?.find((d) => d.id === id)?.name;
  const refresh = () => { qc.invalidateQueries({ queryKey: ["locations", f.id] }); qc.invalidateQueries({ queryKey: ["departments", f.id] }); qc.invalidateQueries({ queryKey: ["facilities"] }); };
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex-row items-center justify-between"><CardTitle>{f.name}</CardTitle>
          {manage && <NativeSelect className="w-44" value={f.facility_type} aria-label="Facility type" onChange={async (e) => { try { await patch(`/facilities/${f.id}`, { facility_type: e.target.value }); refresh(); toast.success("Facility type updated"); } catch (err) { toastError(err); } }}>{FAC_TYPES.map((t) => <option key={t} value={t}>{titleCase(t.replace("_", " "))}</option>)}</NativeSelect>}
        </CardHeader>
        <CardContent>
          <div className="mb-2 flex items-center justify-between"><h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Departments</h4>{manage && <Button size="sm" variant="outline" onClick={() => setNewDept({ name: "", code: "", kind: "inpatient" })}><Plus />Department</Button>}</div>
          {depts.isLoading ? <LoadingRows rows={2} /> : <div className="flex flex-wrap gap-2">{depts.data?.map((d) => <Badge key={d.id} variant={d.is_active ? "outline" : "neutral"} className="py-1">{d.name} <span className="text-muted-foreground">· {d.code} · {d.kind}</span></Badge>)}</div>}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex-row items-center justify-between"><CardTitle className="flex items-center gap-2"><LayoutGrid className="size-4" />Units, rooms & beds</CardTitle>{manage && <Button size="sm" variant="outline" onClick={() => setNewUnit({ name: "", code: "", department_id: depts.data?.[0]?.id ?? "" })}><Plus />Unit</Button>}</CardHeader>
        <CardContent>
          {locs.isLoading ? <LoadingRows /> : !units.length ? <EmptyState icon={LayoutGrid} title="No units yet" /> : (
            <ul className="space-y-3">{units.map((u) => {
              const rooms = children(u.id);
              const beds = rooms.flatMap((r) => (r.kind === "bed" ? [r] : children(r.id).filter((b) => b.kind === "bed")));
              return (
                <li key={u.id} className="rounded-lg border">
                  <details>
                    <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-[13.5px]">
                      <ChevronRight className="size-4 text-muted-foreground transition-transform [details[open]_&]:rotate-90" />
                      <span className="font-medium">{u.name}</span><span className="text-xs text-muted-foreground">{u.code} · {titleCase(u.kind.replace("_", " "))}{deptName(u.department_id) ? ` · ${deptName(u.department_id)}` : ""}</span>
                      <span className="ml-auto flex items-center gap-2 text-xs text-muted-foreground"><DoorOpen className="size-3.5" />{rooms.filter((r) => r.kind === "room").length}<BedDouble className="ml-1 size-3.5" />{beds.length}</span>
                      {manage && u.kind === "unit" && <Button size="sm" variant="ghost" onClick={(e) => { e.preventDefault(); setGen({ unit: u, rooms: "4", beds: "2", start: String(100 + rooms.length + 1) }); }}>Add rooms</Button>}
                    </summary>
                    <div className="flex flex-wrap gap-1.5 border-t p-3">{rooms.map((r) => r.kind === "room" ? (
                      <div key={r.id} className="rounded-md border px-2 py-1 text-xs"><span className="font-medium">{r.name}</span>{children(r.id).map((b) => <span key={b.id} className="ml-1.5 rounded bg-muted px-1.5 py-0.5">{b.name}</span>)}</div>
                    ) : <div key={r.id} className="rounded-md border px-2 py-1 text-xs">{r.name}<span className="ml-1 text-muted-foreground">{r.kind === "bed" ? "bed" : r.kind.replace("_", " ")}</span></div>)}</div>
                  </details>
                </li>);
            })}</ul>
          )}
        </CardContent>
      </Card>
      <Dialog open={!!newDept} onOpenChange={(o) => !o && setNewDept(null)}>
        <DialogContent size="sm"><DialogHeader><DialogTitle>New department</DialogTitle></DialogHeader>
          {newDept && <>
            <Field label="Name" required><Input value={newDept.name} onChange={(e) => setNewDept({ ...newDept, name: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-3"><Field label="Code" required><Input value={newDept.code} onChange={(e) => setNewDept({ ...newDept, code: e.target.value.toUpperCase() })} /></Field>
              <Field label="Type"><NativeSelect value={newDept.kind} onChange={(e) => setNewDept({ ...newDept, kind: e.target.value })}>{DEPT_KINDS.map((k) => <option key={k} value={k}>{titleCase(k)}</option>)}</NativeSelect></Field></div>
          </>}
          <DialogFooter><Button variant="outline" onClick={() => setNewDept(null)}>Cancel</Button>
            <Button disabled={!newDept?.name || !newDept?.code} onClick={async () => { try { await post("/departments", { ...newDept, facility_id: f.id }); setNewDept(null); refresh(); toast.success("Department created"); } catch (e) { toastError(e); } }}>Create</Button></DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={!!newUnit} onOpenChange={(o) => !o && setNewUnit(null)}>
        <DialogContent size="sm"><DialogHeader><DialogTitle>New unit</DialogTitle></DialogHeader>
          {newUnit && <>
            <Field label="Name" required><Input value={newUnit.name} onChange={(e) => setNewUnit({ ...newUnit, name: e.target.value })} placeholder="e.g. Med-Surg 5A" /></Field>
            <div className="grid grid-cols-2 gap-3"><Field label="Code" required><Input value={newUnit.code} onChange={(e) => setNewUnit({ ...newUnit, code: e.target.value.toUpperCase() })} /></Field>
              <Field label="Department"><NativeSelect value={newUnit.department_id} onChange={(e) => setNewUnit({ ...newUnit, department_id: e.target.value })}>{depts.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</NativeSelect></Field></div>
          </>}
          <DialogFooter><Button variant="outline" onClick={() => setNewUnit(null)}>Cancel</Button>
            <Button disabled={!newUnit?.name || !newUnit?.code} onClick={async () => { try { await post("/locations", { ...newUnit, department_id: newUnit!.department_id || null, kind: "unit", facility_id: f.id }); setNewUnit(null); refresh(); toast.success("Unit created"); } catch (e) { toastError(e); } }}>Create</Button></DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={!!gen} onOpenChange={(o) => !o && setGen(null)}>
        <DialogContent size="sm"><DialogHeader><DialogTitle>Add rooms to {gen?.unit.name}</DialogTitle></DialogHeader>
          {gen && <div className="grid grid-cols-3 gap-3">
            <Field label="Rooms"><Input type="number" min={1} max={60} value={gen.rooms} onChange={(e) => setGen({ ...gen, rooms: e.target.value })} /></Field>
            <Field label="Beds / room"><Input type="number" min={1} max={6} value={gen.beds} onChange={(e) => setGen({ ...gen, beds: e.target.value })} /></Field>
            <Field label="First room #"><Input type="number" min={0} value={gen.start} onChange={(e) => setGen({ ...gen, start: e.target.value })} /></Field>
          </div>}
          <DialogFooter><Button variant="outline" onClick={() => setGen(null)}>Cancel</Button>
            <Button onClick={async () => { try { const r = await post<Loc[]>(`/locations/${gen!.unit.id}/generate`, { rooms: Number(gen!.rooms), beds_per_room: Number(gen!.beds), start_number: Number(gen!.start) }); toast.success(`Created ${r.filter((x) => x.kind === "bed").length} beds`); setGen(null); refresh(); } catch (e) { toastError(e); } }}>Generate</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
