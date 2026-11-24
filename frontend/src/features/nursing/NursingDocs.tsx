/** Patient chart › Clinical › Nursing: flowsheet (vitals + observations + intake/output), assessments, care plans. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck, Droplets, FilePen, Plus, Target } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState, LoadingRows, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Segmented } from "@/components/ui/tabs";
import { get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import { cn, titleCase } from "@/lib/utils";

type RowDef = { key: string; group: string; label: string; kind: "number" | "choice" | "text"; unit: string | null; min: number | null; max: number | null; options: string[] | null };
type FieldDef = { key: string; label: string; type: "text" | "choice"; options?: string[]; required?: boolean };
type Template = { key: string; label: string; fields: FieldDef[] };
type Defs = { rows: RowDef[]; vitals: { key: string; label: string; unit: string }[]; templates: Template[] };
type Obs = { id: string; row_key: string; value: string | number; unit: string | null; observed_at: string; recorded_by: string; corrected: boolean; correction_reason: string | null };
type Flowsheet = { observations: Obs[]; vitals: Record<string, string | number | null>[]; io: { intake_ml: number; output_ml: number; balance_ml: number; hours: number } };
type Assessment = { id: string; template_key: string; template: string; fields: FieldDef[]; data: Record<string, string>; status: "draft" | "signed" | "amended";
  author: string; author_id: string; signed_by: string | null; signed_at: string | null; amends_id: string | null; amendment_reason: string | null; created_at: string };
type Plan = { id: string; problem: string; goal: string; interventions: string[]; responsible_role: string | null; status: string; review_due_at: string | null;
  progress: { at: string; by: string; note: string; status: string }[]; created_by: string; overdue_review: boolean };

const hhmm = (iso: string) => new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

export function NursingTab({ patientId }: { patientId: string }) {
  const [view, setView] = React.useState("flowsheet");
  const defs = useQuery({ queryKey: ["nursing", "defs"], queryFn: () => get<Defs>("/nursing/definitions"), staleTime: 3600_000 });
  if (defs.isError) return <ErrorState error={defs.error} retry={defs.refetch} />;
  if (!defs.data) return <LoadingRows />;
  return (
    <div className="space-y-3" data-testid="nursing-docs">
      <Segmented label="Nursing documentation" value={view} onChange={setView}
        options={[{ value: "flowsheet", label: "Flowsheet & I/O" }, { value: "assessments", label: "Assessments" }, { value: "careplans", label: "Care plans" }]} />
      {view === "flowsheet" && <FlowsheetView patientId={patientId} defs={defs.data} />}
      {view === "assessments" && <AssessmentsView patientId={patientId} defs={defs.data} />}
      {view === "careplans" && <CarePlansView patientId={patientId} />}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- flowsheet

function FlowsheetView({ patientId, defs }: { patientId: string; defs: Defs }) {
  const { can } = useAuth();
  const [hours, setHours] = React.useState("24");
  const q = useQuery({ queryKey: ["flowsheet", patientId, hours], queryFn: () => get<Flowsheet>(`/patients/${patientId}/flowsheet`, { hours }) });
  const [rec, setRec] = React.useState(false);
  if (q.isError) return <ErrorState error={q.error} retry={q.refetch} />;
  if (!q.data) return <LoadingRows />;
  const fs = q.data;
  const times = [...new Set([...fs.observations.map((o) => o.observed_at), ...fs.vitals.map((v) => String(v.at))])].sort().slice(-12);
  const cell = (key: string, t: string) => fs.observations.filter((o) => o.row_key === key && o.observed_at === t);
  const groups = [...new Set(defs.rows.map((r) => r.group))];
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        {[["Intake", fs.io.intake_ml], ["Output", fs.io.output_ml], ["Net balance", fs.io.balance_ml]].map(([l, v]) => (
          <Card key={l as string} className="px-4 py-3">
            <p className="flex items-center gap-1.5 text-label text-muted-foreground"><Droplets className="size-3.5" />{l} · last {fs.io.hours} h</p>
            <p className="text-metric font-semibold tabular text-heading" data-testid={`io-${String(l).toLowerCase().replace(" ", "-")}`}>{(v as number) > 0 && l === "Net balance" ? "+" : ""}{v} mL</p>
          </Card>
        ))}
      </div>
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
          <span className="text-section font-semibold text-heading">Flowsheet</span>
          <NativeSelect className="h-8 w-auto" value={hours} onChange={(e) => setHours(e.target.value)} aria-label="Time window">
            <option value="12">Last 12 h</option><option value="24">Last 24 h</option><option value="72">Last 72 h</option>
          </NativeSelect>
          {can("nursing:write") && <Button size="sm" className="ml-auto" onClick={() => setRec(true)}><Plus />Record observations</Button>}
        </div>
        {!times.length ? <EmptyState compact icon={ClipboardCheck} title="Nothing documented in this window" /> : (
          <div className="overflow-x-auto scrollbar-thin">
            <table className="w-full text-table" aria-label="Flowsheet">
              <thead><tr className="border-b bg-subtle">
                <th className="sticky left-0 z-[1] bg-subtle px-3 py-2 text-left text-label font-medium text-muted-foreground">Row</th>
                {times.map((t) => <th key={t} className="whitespace-nowrap px-2 py-2 text-right text-label font-medium tabular text-muted-foreground">{hhmm(t)}</th>)}
              </tr></thead>
              <tbody>
                <tr className="bg-muted/40"><td colSpan={times.length + 1} className="px-3 py-1 text-label font-semibold uppercase tracking-wide text-muted-foreground">Vital signs (from Vitals)</td></tr>
                {defs.vitals.map((v) => (
                  <tr key={v.key} className="border-b last:border-0">
                    <td className="sticky left-0 bg-card px-3 py-1.5">{v.label} <span className="text-muted-foreground">{v.unit}</span></td>
                    {times.map((t) => { const row = fs.vitals.find((x) => x.at === t); return <td key={t} className="px-2 py-1.5 text-right tabular">{row?.[v.key] ?? ""}</td>; })}
                  </tr>
                ))}
                {groups.map((g) => (
                  <React.Fragment key={g}>
                    <tr className="bg-muted/40"><td colSpan={times.length + 1} className="px-3 py-1 text-label font-semibold uppercase tracking-wide text-muted-foreground">{g}</td></tr>
                    {defs.rows.filter((r) => r.group === g).map((r) => (
                      <tr key={r.key} className="border-b last:border-0">
                        <td className="sticky left-0 bg-card px-3 py-1.5">{r.label} {r.unit && <span className="text-muted-foreground">{r.unit}</span>}</td>
                        {times.map((t) => (
                          <td key={t} className="px-2 py-1.5 text-right tabular">
                            {cell(r.key, t).map((o) => <span key={o.id} title={`${o.recorded_by}${o.corrected ? ` · corrected: ${o.correction_reason}` : ""}`} className={cn(o.corrected && "underline decoration-dotted")}>{o.value}</span>)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {rec && <RecordDialog patientId={patientId} defs={defs} onClose={() => setRec(false)} />}
    </div>
  );
}

function RecordDialog({ patientId, defs, onClose }: { patientId: string; defs: Defs; onClose: () => void }) {
  const qc = useQueryClient();
  const [vals, setVals] = React.useState<Record<string, string>>({});
  const [busy, setBusy] = React.useState(false);
  const save = async () => {
    const values = Object.fromEntries(Object.entries(vals).filter(([, v]) => v !== ""));
    if (!Object.keys(values).length) return;
    setBusy(true);
    try { await post(`/patients/${patientId}/flowsheet`, { values }); toast.success("Observations recorded"); qc.invalidateQueries({ queryKey: ["flowsheet", patientId] }); onClose(); }
    catch (e) { toastError(e); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="lg">
        <DialogHeader><DialogTitle>Record observations</DialogTitle><DialogDescription>Time-stamped now and attributed to you. Leave anything not observed empty. Record vital signs in Vitals.</DialogDescription></DialogHeader>
        {[...new Set(defs.rows.map((r) => r.group))].map((g) => (
          <fieldset key={g} className="grid gap-3 sm:grid-cols-3">
            <legend className="mb-1 text-label font-semibold uppercase tracking-wide text-muted-foreground">{g}</legend>
            {defs.rows.filter((r) => r.group === g).map((r) => (
              <Field key={r.key} label={`${r.label}${r.unit ? ` (${r.unit})` : ""}`}>
                {r.kind === "choice" ? (
                  <NativeSelect value={vals[r.key] ?? ""} onChange={(e) => setVals({ ...vals, [r.key]: e.target.value })}>
                    <option value="">—</option>{r.options!.map((o) => <option key={o}>{o}</option>)}
                  </NativeSelect>
                ) : <Input inputMode={r.kind === "number" ? "decimal" : undefined} value={vals[r.key] ?? ""} onChange={(e) => setVals({ ...vals, [r.key]: e.target.value })} />}
              </Field>
            ))}
          </fieldset>
        ))}
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={save} loading={busy}>Save observations</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------------------------- assessments

function AssessmentsView({ patientId, defs }: { patientId: string; defs: Defs }) {
  const { can, me } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["nursing-assessments", patientId], queryFn: () => get<Assessment[]>(`/patients/${patientId}/nursing-assessments`) });
  const [editing, setEditing] = React.useState<Assessment | null>(null);
  const [tpl, setTpl] = React.useState(defs.templates[0]?.key ?? "");
  const refresh = () => qc.invalidateQueries({ queryKey: ["nursing-assessments", patientId] });
  const start = async () => {
    try { const a = await post<Assessment>(`/patients/${patientId}/nursing-assessments`, { template_key: tpl, data: {} }); refresh(); setEditing(a); } catch (e) { toastError(e); }
  };
  const amend = async (a: Assessment) => {
    const reason = window.prompt("Reason for the amendment (kept with the record)");
    if (!reason || reason.trim().length < 5) return;
    try { const n = await post<Assessment>(`/nursing-assessments/${a.id}/amend`, { reason }); refresh(); setEditing(n); } catch (e) { toastError(e); }
  };
  if (q.isError) return <ErrorState error={q.error} retry={q.refetch} />;
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
        <span className="text-section font-semibold text-heading">Nursing assessments</span>
        {can("nursing:write") && (
          <span className="ml-auto flex gap-2">
            <NativeSelect className="h-8 w-auto" value={tpl} onChange={(e) => setTpl(e.target.value)} aria-label="Assessment template">
              {defs.templates.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
            </NativeSelect>
            <Button size="sm" onClick={start}><FilePen />Start assessment</Button>
          </span>
        )}
      </div>
      {q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState compact icon={FilePen} title="No assessments yet" /> : (
        <ul className="divide-y">{q.data.map((a) => (
          <li key={a.id} className="flex flex-wrap items-start gap-3 px-3 py-2.5">
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-center gap-2 text-body font-medium text-heading">{a.template}
                <Badge variant={a.status === "signed" ? "success" : a.status === "draft" ? "warning" : "neutral"}>{a.status === "amended" ? "Amended (superseded)" : titleCase(a.status)}</Badge>
                {a.amends_id && <Badge variant="info">Amendment</Badge>}</p>
              <p className="text-label text-muted-foreground">{a.status === "draft" ? `Draft by ${a.author}` : `Signed by ${a.signed_by} · ${fmtDateTime(a.signed_at!)}`}{a.amendment_reason ? ` · reason: ${a.amendment_reason}` : ""}</p>
              {a.status !== "draft" && <dl className="mt-1 grid gap-x-4 gap-y-0.5 text-table sm:grid-cols-2">{a.fields.filter((f) => a.data[f.key]).map((f) => (
                <div key={f.key} className="flex gap-2"><dt className="text-muted-foreground">{f.label}:</dt><dd className="text-foreground">{a.data[f.key]}</dd></div>))}</dl>}
            </div>
            {a.status === "draft" && a.author_id === me?.user.id && <Button size="xs" variant="outline" onClick={() => setEditing(a)}>Continue</Button>}
            {a.status === "signed" && can("nursing:write") && <Button size="xs" variant="ghost" onClick={() => amend(a)}>Amend</Button>}
          </li>
        ))}</ul>
      )}
      {editing && <AssessmentEditor a={editing} onClose={() => { setEditing(null); refresh(); }} />}
    </Card>
  );
}

function AssessmentEditor({ a, onClose }: { a: Assessment; onClose: () => void }) {
  const [data, setData] = React.useState<Record<string, string>>(a.data ?? {});
  const [busy, setBusy] = React.useState<string | null>(null);
  const save = async (sign: boolean) => {
    setBusy(sign ? "sign" : "save");
    try {
      await put(`/nursing-assessments/${a.id}`, { data });
      if (sign) { await post(`/nursing-assessments/${a.id}/sign`); toast.success("Assessment signed"); } else toast.success("Draft saved");
      onClose();
    } catch (e) { toastError(e); } finally { setBusy(null); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="lg">
        <DialogHeader><DialogTitle>{a.template}</DialogTitle><DialogDescription>{a.amends_id ? `Amendment — ${a.amendment_reason}. The signed original is kept.` : "Saved as a draft until you sign. Signed assessments can't be changed, only amended."}</DialogDescription></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          {a.fields.map((f) => (
            <Field key={f.key} label={f.label} required={f.required} className={f.type === "text" ? "sm:col-span-2" : undefined}>
              {f.type === "choice" ? (
                <NativeSelect value={data[f.key] ?? ""} onChange={(e) => setData({ ...data, [f.key]: e.target.value })}><option value="">—</option>{f.options!.map((o) => <option key={o}>{o}</option>)}</NativeSelect>
              ) : <Textarea rows={2} value={data[f.key] ?? ""} onChange={(e) => setData({ ...data, [f.key]: e.target.value })} />}
            </Field>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => save(false)} loading={busy === "save"}>Save draft</Button>
          <Button onClick={() => save(true)} loading={busy === "sign"}>Sign assessment</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------------------------- care plans

function CarePlansView({ patientId }: { patientId: string }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["care-plans", patientId], queryFn: () => get<Plan[]>(`/patients/${patientId}/care-plans`) });
  const [create, setCreate] = React.useState(false);
  const [prog, setProg] = React.useState<Plan | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["care-plans", patientId] });
  if (q.isError) return <ErrorState error={q.error} retry={q.refetch} />;
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <span className="text-section font-semibold text-heading">Care plans</span>
        {can("nursing:write") && <Button size="sm" className="ml-auto" onClick={() => setCreate(true)}><Plus />New care plan</Button>}
      </div>
      {q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState compact icon={Target} title="No care plans" /> : (
        <ul className="divide-y">{q.data.map((c) => (
          <li key={c.id} className="grid gap-2 px-3 py-3 md:grid-cols-[minmax(0,1fr)_auto]">
            <div className="min-w-0">
              <p className="flex flex-wrap items-center gap-2 text-body font-semibold text-heading">{c.problem}
                <Badge variant={c.status === "active" ? "info" : c.status === "met" ? "success" : "neutral"}>{titleCase(c.status.replace("_", " "))}</Badge>
                {c.overdue_review && <Badge variant="warning">Review overdue</Badge>}</p>
              <p className="text-table"><span className="text-muted-foreground">Goal:</span> {c.goal}</p>
              <ul className="mt-1 list-disc pl-5 text-table">{c.interventions.map((i) => <li key={i}>{i}</li>)}</ul>
              {!!c.progress.length && <p className="mt-1 text-label text-muted-foreground">Latest: {c.progress[c.progress.length - 1].note} — {c.progress[c.progress.length - 1].by}, {hhmm(c.progress[c.progress.length - 1].at)}</p>}
              <p className="text-label text-muted-foreground">Responsible: {titleCase(c.responsible_role ?? "nurse")}{c.review_due_at && c.status === "active" ? ` · review by ${hhmm(c.review_due_at)}` : ""}</p>
            </div>
            {c.status === "active" && can("nursing:write") && <Button size="xs" variant="outline" onClick={() => setProg(c)}>Record progress</Button>}
          </li>
        ))}</ul>
      )}
      {create && <NewPlanDialog patientId={patientId} onClose={() => { setCreate(false); refresh(); }} />}
      {prog && <ProgressDialog plan={prog} onClose={() => { setProg(null); refresh(); }} />}
    </Card>
  );
}

function NewPlanDialog({ patientId, onClose }: { patientId: string; onClose: () => void }) {
  const [f, setF] = React.useState({ problem: "", goal: "", interventions: "", review_in_hours: "24" });
  const [busy, setBusy] = React.useState(false);
  const save = async () => {
    setBusy(true);
    try { await post(`/patients/${patientId}/care-plans`, { problem: f.problem, goal: f.goal, interventions: f.interventions.split("\n").filter((x) => x.trim()), review_in_hours: Number(f.review_in_hours) || 24 }); toast.success("Care plan created"); onClose(); }
    catch (e) { toastError(e); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="md">
        <DialogHeader><DialogTitle>New care plan</DialogTitle><DialogDescription>Describe the nursing problem or need in your own words; this is not a coded nursing taxonomy.</DialogDescription></DialogHeader>
        <Field label="Problem / need" required><Input value={f.problem} onChange={(e) => setF({ ...f, problem: e.target.value })} /></Field>
        <Field label="Goal" required><Input value={f.goal} onChange={(e) => setF({ ...f, goal: e.target.value })} /></Field>
        <Field label="Interventions (one per line)" required><Textarea rows={4} value={f.interventions} onChange={(e) => setF({ ...f, interventions: e.target.value })} /></Field>
        <Field label="Review within (hours)"><Input inputMode="numeric" value={f.review_in_hours} onChange={(e) => setF({ ...f, review_in_hours: e.target.value.replace(/\D/g, "") })} /></Field>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={save} loading={busy} disabled={f.problem.length < 3 || f.goal.length < 3 || !f.interventions.trim()}>Create</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ProgressDialog({ plan, onClose }: { plan: Plan; onClose: () => void }) {
  const [note, setNote] = React.useState("");
  const [status, setStatus] = React.useState("active");
  const [busy, setBusy] = React.useState(false);
  const save = async () => {
    setBusy(true);
    try { await post(`/care-plans/${plan.id}/progress`, { note, status }); toast.success("Progress recorded"); onClose(); } catch (e) { toastError(e); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="sm">
        <DialogHeader><DialogTitle>Progress · {plan.problem}</DialogTitle><DialogDescription>Goal: {plan.goal}</DialogDescription></DialogHeader>
        <Field label="Progress note" required><Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        <Field label="Status"><NativeSelect value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="active">Continue plan</option><option value="met">Goal met</option><option value="not_met">Goal not met</option><option value="discontinued">Discontinue</option>
        </NativeSelect></Field>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={save} loading={busy} disabled={note.trim().length < 3}>Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

