import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Clock, Pencil, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, LoadingRows, PageHeader, toastError } from "@/components/common";
import { FormDialog } from "@/components/common/FormDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get, patch, post, put } from "@/lib/api";
import { type ClinicFull, useClinics } from "@/lib/hooks";
import type { AppointmentType, Provider } from "@/lib/types";

const TIMEZONES = ["America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles", "America/Anchorage", "Pacific/Honolulu"];

export function ClinicsPage() {
  const qc = useQueryClient();
  const clinics = useClinics(true);
  const [editing, setEditing] = React.useState<ClinicFull | "new" | null>(null);
  return (
    <>
      <PageHeader title="Clinics" description="Locations, timezones and exam rooms." actions={<Button onClick={() => setEditing("new")}><Plus />Add clinic</Button>} />
      {clinics.isLoading ? <LoadingRows /> : !clinics.data?.length ? <Card><EmptyState icon={Building2} title="No clinics" /></Card> : (
        <div className="grid gap-4 md:grid-cols-2">
          {clinics.data.map((c) => (
            <Card key={c.id} className={c.is_active ? "" : "opacity-60"}>
              <CardHeader>
                <div><CardTitle>{c.name} <span className="ml-1 font-mono text-xs font-normal text-muted-foreground">{c.code}</span></CardTitle>
                  <CardDescription>{[c.address_line1, c.city, c.state].filter(Boolean).join(", ") || "No address"}</CardDescription></div>
                <Button variant="ghost" size="icon-sm" onClick={() => setEditing(c)} aria-label={`Edit ${c.name}`}><Pencil /></Button>
              </CardHeader>
              <CardContent className="space-y-2 text-table">
                <p className="flex items-center gap-2 text-muted-foreground"><Clock className="size-3.5" />{c.timezone}{c.phone ? ` · ${c.phone}` : ""}</p>
                <div className="flex flex-wrap gap-1">{c.rooms.map((r) => <Badge key={r} variant="outline">{r}</Badge>)}</div>
                {!c.is_active && <Badge variant="danger">Inactive</Badge>}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <FormDialog
        open={!!editing} onOpenChange={(o) => !o && setEditing(null)} title={editing === "new" ? "Add clinic" : "Edit clinic"}
        fields={[
          { name: "name", label: "Name", required: true },
          { name: "code", label: "Short code", required: true, span: 1 },
          { name: "timezone", label: "Timezone", type: "select", options: TIMEZONES.map((t) => [t, t]), span: 1 },
          { name: "phone", label: "Phone", span: 1 },
          { name: "address_line1", label: "Address", span: 1 },
          { name: "city", label: "City", span: 1 },
          { name: "state", label: "State", span: 1 },
          { name: "postal_code", label: "ZIP", span: 1 },
          { name: "rooms", label: "Rooms (comma-separated)", span: 2 },
          { name: "is_active", label: "Active", type: "checkbox" },
        ]}
        initial={editing && editing !== "new" ? { ...editing, rooms: editing.rooms.join(", ") } as unknown as Record<string, string> : { is_active: true, timezone: "America/New_York" }}
        onSubmit={async (v) => {
          const body = { ...v, rooms: String(v.rooms ?? "").split(",").map((r) => r.trim()).filter(Boolean) };
          if (editing === "new") await post("/clinics", body);
          else if (editing) await patch(`/clinics/${editing.id}`, body);
          qc.invalidateQueries({ queryKey: ["clinics"] });
          toast.success("Clinic saved");
        }}
      />
    </>
  );
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
type Block = { clinic_id: string; weekday: number; start_time: string; end_time: string };

function AvailabilityEditor({ provider, clinics }: { provider: Provider; clinics: ClinicFull[] }) {
  const qc = useQueryClient();
  const [blocks, setBlocks] = React.useState<Block[]>(provider.availability.map((b) => ({ ...b, start_time: b.start_time.slice(0, 5), end_time: b.end_time.slice(0, 5) })));
  const [busy, setBusy] = React.useState(false);
  const dirty = JSON.stringify(blocks) !== JSON.stringify(provider.availability.map((b) => ({ ...b, start_time: b.start_time.slice(0, 5), end_time: b.end_time.slice(0, 5) })));
  const upd = (i: number, k: keyof Block, v: string | number) => setBlocks(blocks.map((b, j) => (j === i ? { ...b, [k]: v } : b)));
  return (
    <Card>
      <CardHeader>
        <div><CardTitle>{provider.name}</CardTitle><CardDescription>{provider.specialty ?? "Provider"} · weekly hours</CardDescription></div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setBlocks([...blocks, { clinic_id: clinics[0]?.id ?? "", weekday: 0, start_time: "08:00", end_time: "12:00" }])}><Plus />Add hours</Button>
          <Button size="sm" disabled={!dirty} loading={busy} onClick={async () => {
            setBusy(true);
            try { await put(`/providers/${provider.id}/availability`, blocks.map((b) => ({ ...b, start_time: `${b.start_time}:00`, end_time: `${b.end_time}:00` }))); qc.invalidateQueries({ queryKey: ["providers"] }); toast.success("Hours saved"); }
            catch (e) { toastError(e); } finally { setBusy(false); }
          }}>Save</Button>
        </div>
      </CardHeader>
      <CardContent>
        {!blocks.length ? <p className="text-table text-muted-foreground">No scheduled hours — this provider can only be booked with an override.</p> : (
          <ul className="space-y-2">
            {blocks.map((b, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2">
                <NativeSelect value={b.weekday} onChange={(e) => upd(i, "weekday", +e.target.value)} className="w-24" aria-label="Day">{DAYS.map((d, j) => <option key={d} value={j}>{d}</option>)}</NativeSelect>
                <Input type="time" value={b.start_time} onChange={(e) => upd(i, "start_time", e.target.value)} className="w-32" aria-label="Start" />
                <span className="text-muted-foreground">to</span>
                <Input type="time" value={b.end_time} onChange={(e) => upd(i, "end_time", e.target.value)} className="w-32" aria-label="End" />
                <NativeSelect value={b.clinic_id} onChange={(e) => upd(i, "clinic_id", e.target.value)} className="w-48" aria-label="Clinic">{clinics.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</NativeSelect>
                <Button variant="ghost" size="icon-sm" onClick={() => setBlocks(blocks.filter((_, j) => j !== i))} aria-label="Remove"><Trash2 /></Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function SchedulingSetupPage() {
  const qc = useQueryClient();
  const types = useQuery({ queryKey: ["appointment-types"], queryFn: () => get<AppointmentType[]>("/appointment-types") });
  const providers = useQuery({ queryKey: ["providers"], queryFn: () => get<Provider[]>("/providers") });
  const clinics = useClinics();
  const [editing, setEditing] = React.useState<AppointmentType | "new" | null>(null);
  return (
    <>
      <PageHeader title="Scheduling setup" description="Visit types and provider working hours." />
      <Card className="mb-5 overflow-hidden">
        <CardHeader><div><CardTitle>Visit types</CardTitle></div><Button size="sm" onClick={() => setEditing("new")}><Plus />Add type</Button></CardHeader>
        <Table>
          <THead><TR><TH>Name</TH><TH>Duration</TH><TH>Mode</TH><TH>Status</TH><TH className="w-10" /></TR></THead>
          <TBody>
            {types.data?.map((t) => (
              <TR key={t.id}>
                <TD className="font-medium">{t.name}</TD><TD>{t.duration_minutes} min</TD><TD>{t.is_telehealth ? "Telehealth" : "In person"}</TD>
                <TD>{t.is_active ? <Badge variant="success">Active</Badge> : <Badge>Inactive</Badge>}</TD>
                <TD><Button variant="ghost" size="icon-sm" onClick={() => setEditing(t)} aria-label={`Edit ${t.name}`}><Pencil /></Button></TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </Card>
      <h2 className="mb-3 text-section font-semibold">Provider hours</h2>
      <div className="grid gap-4 xl:grid-cols-2">
        {providers.data?.map((p) => <AvailabilityEditor key={p.id + JSON.stringify(p.availability)} provider={p} clinics={clinics.data ?? []} />)}
      </div>
      <FormDialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)} title={editing === "new" ? "Add visit type" : "Edit visit type"}
        fields={[
          { name: "name", label: "Name", required: true },
          { name: "duration_minutes", label: "Duration (minutes)", type: "number", required: true, span: 1 },
          { name: "color", label: "Color", type: "select", options: ["blue", "violet", "emerald", "amber", "rose", "cyan", "slate"].map((c) => [c, c]), span: 1 },
          { name: "is_telehealth", label: "Telehealth visit", type: "checkbox" },
          { name: "is_active", label: "Active", type: "checkbox" },
        ]}
        initial={editing && editing !== "new" ? { ...editing, duration_minutes: String(editing.duration_minutes) } as unknown as Record<string, string> : { duration_minutes: "20", is_active: true }}
        onSubmit={async (v) => {
          const body = { ...v, duration_minutes: Number(v.duration_minutes) };
          if (editing === "new") await post("/appointment-types", body);
          else if (editing) await put(`/appointment-types/${editing.id}`, body);
          qc.invalidateQueries({ queryKey: ["appointment-types"] });
          toast.success("Visit type saved");
        }} />
    </>
  );
}
