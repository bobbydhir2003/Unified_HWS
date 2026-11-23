import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot, CheckCircle2, ClipboardCheck, FilePlus2, FileSignature, History, HeartPulse, Lock, Plus, Save, Sparkles, Stethoscope, X,
} from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { AIBadge, ErrorState, LoadingRows, toastError, useUnsavedChanges } from "@/components/common";
import { Icd10Picker } from "@/components/common/FormDialog";
import { useCrumb } from "@/components/layout/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Checkbox, Kbd, Skeleton } from "@/components/ui/misc";
import { Dialog as D } from "radix-ui";
import { AllergyStrip, type Summary } from "@/features/patients/PatientChart";
import { VitalsDialog, VitalsSummary } from "@/features/patients/Vitals";
import { ScribePanel } from "./ScribePanel";
import { ChartAssistant } from "@/features/ai/ChartAssistant";
import { EncounterOrdersCard } from "@/features/orders/OrdersPages";
import { ApiError, get, patch, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cToF, fmtDateTime, fmtDob, sexShort } from "@/lib/format";
import type { EncounterDetail, Note, NoteContent, Template, Vitals } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";

const SECTIONS: { key: keyof NoteContent; label: string; hint: string }[] = [
  { key: "subjective", label: "Subjective", hint: "History of present illness, ROS, patient-reported information" },
  { key: "objective", label: "Objective", hint: "Vitals, exam findings, results" },
  { key: "assessment", label: "Assessment", hint: "Clinical impression / diagnoses (required to sign)" },
  { key: "plan", label: "Plan", hint: "Treatment, orders, education, follow-up (required to sign)" },
];

function AutoTextarea(props: React.ComponentProps<"textarea">) {
  const ref = React.useRef<HTMLTextAreaElement>(null);
  React.useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(88, el.scrollHeight + 2)}px`;
  }, [props.value]);
  return <Textarea ref={ref} {...props} className={cn("resize-none", props.className)} />;
}

function vitalsText(v: Vitals) {
  const parts = [];
  if (v.systolic) parts.push(`BP ${v.systolic}/${v.diastolic}`);
  if (v.heart_rate) parts.push(`HR ${v.heart_rate}`);
  if (v.respiratory_rate) parts.push(`RR ${v.respiratory_rate}`);
  if (v.temperature_c) parts.push(`T ${cToF(v.temperature_c)}°F`);
  if (v.spo2) parts.push(`SpO2 ${v.spo2}%`);
  if (v.weight_kg) parts.push(`Wt ${Math.round(Number(v.weight_kg) * 2.20462)} lb`);
  if (v.bmi) parts.push(`BMI ${v.bmi}`);
  return `Vitals: ${parts.join(", ")}`;
}

function NoteEditor({ note, encounter, onChanged, onDirtyChange }: { note: Note; encounter: EncounterDetail; onChanged: () => void; onDirtyChange: (d: boolean) => void }) {
  const { can } = useAuth();
  const [content, setContent] = React.useState<NoteContent>(note.content);
  const [version, setVersion] = React.useState(note.current_version);
  const [saving, setSaving] = React.useState(false);
  const [signOpen, setSignOpen] = React.useState(false);
  const [attest, setAttest] = React.useState(false);
  const [signing, setSigning] = React.useState(false);
  const [conflict, setConflict] = React.useState(false);
  const dirty = JSON.stringify(content) !== JSON.stringify(note.content) || version !== note.current_version;
  const blocker = useUnsavedChanges(dirty);
  React.useEffect(() => { onDirtyChange(dirty); return () => onDirtyChange(false); }, [dirty, onDirtyChange]);
  const editable = encounter.status === "in_progress" && can("clinical:write");

  React.useEffect(() => { setContent(note.content); setVersion(note.current_version); setConflict(false); }, [note.id, note.current_version]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = React.useCallback(async () => {
    if (!dirty || saving) return true;
    setSaving(true);
    try {
      const n = await put<Note>(`/notes/${note.id}`, { content, expected_version: version });
      setVersion(n.current_version);
      onChanged();
      toast.success(`Draft saved · v${n.current_version}`);
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.code === "version_conflict") setConflict(true);
      toastError(e);
      return false;
    } finally { setSaving(false); }
  }, [content, dirty, note.id, onChanged, saving, version]);

  React.useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); if (editable) save(); } };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [save, editable]);

  const sign = async () => {
    setSigning(true);
    try {
      if (dirty && !(await save())) return;
      await post(`/notes/${note.id}/sign`, { expected_version: dirty ? version + 1 : version, attest_ai_reviewed: attest });
      toast.success("Note signed");
      setSignOpen(false);
      onChanged();
    } catch (e) { toastError(e); } finally { setSigning(false); }
  };

  const missingAP = !content.assessment.trim() || !content.plan.trim();
  const latestVitals = encounter.vitals[0];

  return (
    <Card>
      {blocker}
      <CardHeader className="border-b pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>{note.title}</CardTitle>
          <Badge variant="warning">Draft</Badge>
          {note.has_ai_content && <AIBadge label="Contains AI-generated text" />}
          <span className="text-xs text-muted-foreground">v{version} · {note.author.name}</span>
          {dirty && <span className="text-xs font-medium text-warning">Unsaved changes</span>}
        </div>
        {editable && (
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={save} loading={saving} disabled={!dirty}><Save />Save <Kbd>⌘S</Kbd></Button>
            {can("clinical:sign") && <Button size="sm" onClick={() => { setAttest(false); setSignOpen(true); }}><FileSignature />Sign</Button>}
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-5 pt-4">
        {conflict && (
          <div role="alert" className="flex items-center justify-between gap-2 rounded-lg border border-warning/40 bg-warning-soft px-3 py-2 text-table">
            Someone else saved this note. Reload to see their version (your edits will be replaced).
            <Button size="xs" variant="outline" onClick={onChanged}>Reload</Button>
          </div>
        )}
        {SECTIONS.map((s) => (
          <div key={s.key}>
            <div className="mb-1.5 flex items-end justify-between gap-2">
              <label htmlFor={`sec-${s.key}`} className="text-table font-semibold">{s.label}</label>
              {s.key === "objective" && latestVitals && editable && (
                <Button size="xs" variant="ghost" onClick={() => setContent((c) => ({ ...c, objective: `${vitalsText(latestVitals)}\n${c.objective}` }))}>
                  <HeartPulse />Insert vitals
                </Button>
              )}
            </div>
            <AutoTextarea id={`sec-${s.key}`} value={content[s.key]} placeholder={s.hint} readOnly={!editable}
              onChange={(e) => setContent((c) => ({ ...c, [s.key]: e.target.value }))} />
          </div>
        ))}
      </CardContent>

      <Dialog open={signOpen} onOpenChange={setSignOpen}>
        <DialogContent size="sm">
          <DialogHeader>
            <DialogTitle>Sign note</DialogTitle>
            <DialogDescription>Once signed, the note is locked. Corrections must be added as addenda.</DialogDescription>
          </DialogHeader>
          {missingAP && <div className="rounded-lg border border-destructive/30 bg-destructive-soft px-3 py-2 text-table text-destructive">Assessment and Plan are required before signing.</div>}
          {note.has_ai_content && (
            <label className="flex items-start gap-2 rounded-lg border border-ai/30 bg-ai-soft p-3 text-table">
              <Checkbox checked={attest} onCheckedChange={(c) => setAttest(!!c)} className="mt-0.5" />
              <span>I have reviewed and, where needed, corrected the AI-generated content in this note, and it accurately reflects this encounter.</span>
            </label>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setSignOpen(false)}>Cancel</Button>
            <Button onClick={sign} loading={signing} disabled={missingAP || (note.has_ai_content && !attest)}><FileSignature />Sign note</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function SignedNote({ note, onChanged }: { note: Note; onChanged: () => void }) {
  const { can } = useAuth();
  const [addOpen, setAddOpen] = React.useState(false);
  const [body, setBody] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  return (
    <Card>
      <CardHeader className="border-b pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>{note.title}</CardTitle>
          <Badge variant="success"><Lock />Signed</Badge>
          {note.has_ai_content && <AIBadge label={note.ai_reviewed ? "AI-assisted · clinician reviewed" : "AI-assisted"} />}
        </div>
        {can("clinical:write") && <Button variant="outline" size="sm" onClick={() => setAddOpen((o) => !o)}><FilePlus2 />Addendum</Button>}
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
        <p className="text-xs text-muted-foreground">Signed by <strong className="text-foreground">{note.signed_by?.name}</strong> · {fmtDateTime(note.signed_at)} · v{note.current_version}</p>
        {SECTIONS.map((s) => (
          <section key={s.key}>
            <h3 className="mb-1 text-label font-semibold uppercase tracking-wide text-muted-foreground">{s.label}</h3>
            <p className="whitespace-pre-wrap text-body leading-relaxed">{note.content[s.key] || <span className="text-muted-foreground">—</span>}</p>
          </section>
        ))}
        {note.addenda.length > 0 && (
          <section className="space-y-2 border-t pt-4">
            <h3 className="text-label font-semibold uppercase tracking-wide text-muted-foreground">Addenda</h3>
            {note.addenda.map((a) => (
              <div key={a.id} className="rounded-lg border-l-4 border-primary bg-muted/40 px-3 py-2">
                <p className="whitespace-pre-wrap text-body">{a.body}</p>
                <p className="mt-1 text-xs text-muted-foreground">{a.author.name} · {fmtDateTime(a.created_at)}</p>
              </div>
            ))}
          </section>
        )}
        {addOpen && (
          <form className="space-y-2 border-t pt-4" onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try { await post(`/notes/${note.id}/addenda`, { body }); setBody(""); setAddOpen(false); toast.success("Addendum added"); onChanged(); }
            catch (err) { toastError(err); } finally { setBusy(false); }
          }}>
            <label htmlFor="addendum" className="text-table font-semibold">New addendum</label>
            <Textarea id="addendum" rows={3} value={body} onChange={(e) => setBody(e.target.value)} autoFocus />
            <p className="text-xs text-muted-foreground">Addenda are timestamped, attributed to you and cannot be edited.</p>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setAddOpen(false)}>Cancel</Button>
              <Button type="submit" size="sm" loading={busy} disabled={!body.trim()}>Add addendum</Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

function VersionHistory({ noteId, open, onOpenChange }: { noteId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const q = useQuery({ queryKey: ["versions", noteId], queryFn: () => get<{ version: number; content: NoteContent; source: string; created_by: { name: string } | null; created_at: string }[]>(`/notes/${noteId}/versions`), enabled: open });
  const [sel, setSel] = React.useState<number | null>(null);
  const v = q.data?.find((x) => x.version === sel) ?? q.data?.[0];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <SheetContent className="max-w-2xl" aria-describedby={undefined}>
        <div className="border-b px-6 py-4"><D.Title className="text-base font-semibold">Version history</D.Title><p className="text-table text-muted-foreground">Every save is kept. Versions can't be edited or deleted.</p></div>
        <div className="grid min-h-0 flex-1 grid-cols-[180px_1fr]">
          <ul className="overflow-y-auto border-r p-2">
            {q.data?.map((x) => (
              <li key={x.version}>
                <button onClick={() => setSel(x.version)} className={cn("w-full rounded-md px-2.5 py-2 text-left text-table hover:bg-muted", v?.version === x.version && "bg-accent")}>
                  <span className="flex items-center gap-1.5 font-medium">v{x.version}{x.source === "sign" && <Lock className="size-3" />}{x.source === "ai_scribe" && <Badge variant="ai" className="px-1">AI</Badge>}</span>
                  <span className="block text-xs text-muted-foreground">{titleCase(x.source)} · {x.created_by?.name ?? "—"}</span>
                  <span className="block text-label text-muted-foreground">{fmtDateTime(x.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="space-y-4 overflow-y-auto p-5">
            {q.isLoading && <LoadingRows />}
            {v && SECTIONS.map((s) => (
              <section key={s.key}>
                <h3 className="mb-1 text-label font-semibold uppercase tracking-wide text-muted-foreground">{s.label}</h3>
                <p className="whitespace-pre-wrap text-table">{v.content[s.key] || "—"}</p>
              </section>
            ))}
          </div>
        </div>
      </SheetContent>
    </Dialog>
  );
}

function Diagnoses({ enc, onChanged }: { enc: EncounterDetail; onChanged: () => void }) {
  const { can } = useAuth();
  const editable = enc.status === "in_progress" && can("clinical:write");
  const [addToProblems, setAddToProblems] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const update = async (list: { code: string; description: string; add_to_problem_list?: boolean }[]) => {
    setBusy(true);
    try { await put(`/encounters/${enc.id}/diagnoses`, list); onChanged(); } catch (e) { toastError(e); } finally { setBusy(false); }
  };
  const current = enc.diagnoses.map((d) => ({ code: d.code, description: d.description }));
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle>Diagnoses</CardTitle>{busy && <span className="size-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />}</CardHeader>
      <CardContent className="space-y-3">
        {!enc.diagnoses.length && <p className="text-table text-muted-foreground">No diagnoses yet. At least one is required to complete the visit.</p>}
        <ol className="space-y-1.5">
          {enc.diagnoses.map((d, i) => (
            <li key={d.id} className="flex items-start gap-2 rounded-lg border px-2.5 py-2 text-table">
              <span className="mt-0.5 w-4 text-xs font-semibold text-muted-foreground">{i + 1}</span>
              <span className="min-w-0 flex-1"><span className="font-mono text-xs font-semibold text-primary">{d.code}</span><span className="block">{d.description}</span></span>
              {editable && <Button variant="ghost" size="icon-sm" aria-label={`Remove ${d.code}`} onClick={() => update(current.filter((c) => c.code !== d.code))}><X /></Button>}
            </li>
          ))}
        </ol>
        {editable && (
          <div className="space-y-2">
            <Icd10Picker value="" clearOnPick placeholder="Add diagnosis (ICD-10)…" onPick={(code, description) => {
              if (current.some((c) => c.code === code)) { toast.info(`${code} is already listed`); return; }
              update([...current, { code, description, add_to_problem_list: addToProblems }]);
            }} />
            <label className="flex items-center gap-2 text-xs text-muted-foreground"><Checkbox checked={addToProblems} onCheckedChange={(c) => setAddToProblems(!!c)} />Also add new diagnoses to problem list</label>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

type Intake = { submitted_at: string; reviewed_at: string | null; answers: {
  reason_details: string; symptoms: string[]; symptom_duration: string | null; pain_score: number | null; medications_confirmed: boolean;
  medication_changes: string | null; allergies_confirmed: boolean; allergy_changes: string | null; phq2_interest: number; phq2_mood: number;
  questions_for_clinician: string | null } };

function IntakeCard({ appointmentId }: { appointmentId: string }) {
  const q = useQuery({ queryKey: ["intake-staff", appointmentId], queryFn: () => get<Intake | null>(`/appointments/${appointmentId}/intake`) });
  if (!q.data) return null;
  const a = q.data.answers;
  const phq2 = a.phq2_interest + a.phq2_mood;
  return (
    <Card className="border-primary/25">
      <CardHeader className="pb-2"><CardTitle>Pre-visit intake</CardTitle><span className="text-xs text-muted-foreground">from patient · {fmtDateTime(q.data.submitted_at)}</span></CardHeader>
      <CardContent className="space-y-2 text-table">
        <p>{a.reason_details}</p>
        {!!a.symptoms.length && <p><span className="text-muted-foreground">Symptoms:</span> {a.symptoms.join(", ")}{a.symptom_duration ? ` · ${a.symptom_duration}` : ""}{a.pain_score != null ? ` · pain ${a.pain_score}/10` : ""}</p>}
        {!a.medications_confirmed && <p className="text-warning"><strong>Medication changes:</strong> {a.medication_changes || "patient indicated the list is incorrect"}</p>}
        {!a.allergies_confirmed && <p className="text-destructive"><strong>Allergy changes:</strong> {a.allergy_changes || "patient indicated the list is incorrect"}</p>}
        <p className={phq2 >= 3 ? "font-medium text-destructive" : "text-muted-foreground"}>PHQ-2 score {phq2}/6{phq2 >= 3 ? " — positive screen; consider PHQ-9" : ""}</p>
        {a.questions_for_clinician && <p><span className="text-muted-foreground">Questions:</span> {a.questions_for_clinician}</p>}
      </CardContent>
    </Card>
  );
}

export function EncounterPage() {
  const { encounterId = "" } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["encounter", encounterId], queryFn: () => get<EncounterDetail>(`/encounters/${encounterId}`) });
  const enc = q.data;
  const summary = useQuery({ queryKey: ["summary", enc?.patient_id], queryFn: () => get<Summary>(`/patients/${enc!.patient_id}/summary`), enabled: !!enc });
  const templates = useQuery({ queryKey: ["templates"], queryFn: () => get<Template[]>("/templates"), enabled: !!enc && enc.status === "in_progress" && !enc.notes.length });
  const [templateId, setTemplateId] = React.useState("");
  const [creating, setCreating] = React.useState(false);
  const [vitalsOpen, setVitalsOpen] = React.useState(false);
  const [historyOpen, setHistoryOpen] = React.useState(false);
  const [completing, setCompleting] = React.useState(false);
  const [cc, setCc] = React.useState<string | null>(null);
  const [scribeOpen, setScribeOpen] = React.useState(false);
  const [askOpen, setAskOpen] = React.useState(false);
  const [noteDirty, setNoteDirty] = React.useState(false);
  const { membership } = useAuth();
  const org = useQuery({ queryKey: ["organization", membership?.organization_id], queryFn: () => get<{ settings: { synthetic_data?: boolean } }>("/organization"), staleTime: 300_000 });
  const [followUp, setFollowUp] = React.useState<string | null>(null);
  useCrumb(enc ? `${enc.patient.name} · ${fmtDateTime(enc.started_at)}` : null);

  const refresh = React.useCallback(() => {
    qc.invalidateQueries({ queryKey: ["encounter", encounterId] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    if (enc) { qc.invalidateQueries({ queryKey: ["summary", enc.patient_id] }); qc.invalidateQueries({ queryKey: ["encounters", enc.patient_id] }); qc.invalidateQueries({ queryKey: ["timeline", enc.patient_id] }); }
  }, [qc, encounterId, enc]);

  if (q.error) return <ErrorState error={q.error} retry={q.refetch} />;
  if (!enc) return <div className="space-y-4"><Skeleton className="h-24 rounded-xl" /><LoadingRows rows={6} /></div>;
  const note = enc.notes[0];
  const open = enc.status === "in_progress";
  const writable = open && can("clinical:write");
  const canComplete = open && can("clinical:sign") && note?.status === "signed" && enc.diagnoses.length > 0;

  const saveField = async (field: "chief_complaint" | "follow_up", value: string) => {
    try { await patch(`/encounters/${enc.id}`, { [field]: value || null }); refresh(); } catch (e) { toastError(e); }
  };

  return (
    <>
      <Card className="sticky top-[60px] z-20 mb-4">
        <div className="flex flex-col gap-3 p-4 md:flex-row md:items-center">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <Link to={`/patients/${enc.patient_id}`} className="text-lg font-semibold tracking-tight hover:underline">{enc.patient.name}</Link>
              <Badge variant={open ? "ai" : enc.status === "completed" ? "success" : "danger"}>{open ? "Visit in progress" : titleCase(enc.status)}</Badge>
            </div>
            <p className="mt-0.5 text-table text-muted-foreground tabular">
              {sexShort(enc.patient.sex_at_birth)} · DOB {fmtDob(enc.patient.date_of_birth)} · MRN <span className="font-mono">{enc.patient.mrn}</span> · {titleCase(enc.encounter_type)} · {enc.provider.name} · started {fmtDateTime(enc.started_at)}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {open && can("ai:use") && can("clinical:write") && note?.status !== "signed" && !scribeOpen && (
              <Button variant="soft" size="sm" onClick={() => setScribeOpen(true)}><Sparkles />AI scribe</Button>
            )}
            {can("ai:use") && <Button variant="ghost" size="sm" onClick={() => setAskOpen(true)}><Bot />Ask chart</Button>}
            {note && <Button variant="outline" size="sm" onClick={() => setHistoryOpen(true)}><History />Versions</Button>}
            {open && can("clinical:sign") && (
              <Button size="sm" variant="success" disabled={!canComplete} loading={completing}
                title={!canComplete ? "Sign the note and add at least one diagnosis first" : undefined}
                onClick={async () => {
                  setCompleting(true);
                  try { await post(`/encounters/${enc.id}/complete`); toast.success("Visit completed"); refresh(); qc.invalidateQueries({ queryKey: ["queue"] }); }
                  catch (e) { toastError(e); } finally { setCompleting(false); }
                }}>
                <CheckCircle2 />Complete visit
              </Button>
            )}
          </div>
        </div>
        <div className="border-t bg-subtle px-4 py-2"><AllergyStrip summary={summary.data} /></div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <Card>
            <CardContent className="grid gap-3 pt-4 sm:grid-cols-2">
              <div>
                <label htmlFor="cc" className="text-table font-semibold">Chief complaint</label>
                <Input id="cc" className="mt-1.5" readOnly={!writable} value={cc ?? enc.chief_complaint ?? ""} onChange={(e) => setCc(e.target.value)}
                  onBlur={() => { if (cc !== null && cc !== (enc.chief_complaint ?? "")) saveField("chief_complaint", cc); setCc(null); }} placeholder="Reason for visit" />
              </div>
              <div>
                <label htmlFor="fu" className="text-table font-semibold">Follow-up</label>
                <Input id="fu" className="mt-1.5" readOnly={!writable} value={followUp ?? enc.follow_up ?? ""} onChange={(e) => setFollowUp(e.target.value)}
                  onBlur={() => { if (followUp !== null && followUp !== (enc.follow_up ?? "")) saveField("follow_up", followUp); setFollowUp(null); }} placeholder="e.g. Return in 3 months" />
              </div>
            </CardContent>
          </Card>

          {scribeOpen && open && (
            <ScribePanel encounterId={enc.id} patientId={enc.patient_id}
              chartAllergies={summary.data?.clinical_access ? (summary.data.allergies ?? []).map((a) => a.substance) : null} noteId={note?.id} noteVersion={note?.current_version} noteDirty={noteDirty}
              synthetic={!!org.data?.settings.synthetic_data} onApplied={refresh} onClose={() => setScribeOpen(false)} />
          )}
          {!note ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
                <span className="rounded-full bg-accent p-3 text-accent-foreground"><Stethoscope className="size-5" /></span>
                <p className="font-medium">No note for this visit yet</p>
                {writable ? (
                  <div className="flex w-full max-w-md flex-col gap-2 sm:flex-row">
                    <NativeSelect value={templateId} onChange={(e) => setTemplateId(e.target.value)} aria-label="Template">
                      <option value="">Blank SOAP note</option>
                      {templates.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </NativeSelect>
                    <Button loading={creating} onClick={async () => {
                      setCreating(true);
                      try { await post(`/encounters/${enc.id}/notes`, { template_id: templateId || null }); refresh(); }
                      catch (e) { toastError(e); } finally { setCreating(false); }
                    }}><Plus />Start note</Button>
                  </div>
                ) : <p className="text-table text-muted-foreground">This visit was closed without a note.</p>}
              </CardContent>
            </Card>
          ) : note.status === "signed" ? <SignedNote note={note} onChanged={refresh} /> : <NoteEditor note={note} encounter={enc} onChanged={refresh} onDirtyChange={setNoteDirty} />}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle>Vitals</CardTitle>
              {writable && <Button size="xs" variant="outline" onClick={() => setVitalsOpen(true)}><Plus />Record</Button>}
            </CardHeader>
            <CardContent>
              {enc.vitals[0] ? (
                <><VitalsSummary v={enc.vitals[0]} className="sm:grid-cols-4" /><p className="mt-2 text-xs text-muted-foreground">{fmtDateTime(enc.vitals[0].measured_at)}{enc.vitals.length > 1 ? ` · ${enc.vitals.length} sets this visit` : ""}</p></>
              ) : <p className="text-table text-muted-foreground">Not recorded for this visit.</p>}
            </CardContent>
          </Card>
          {enc.appointment_id && <IntakeCard appointmentId={enc.appointment_id} />}
          <Diagnoses enc={enc} onChanged={refresh} />
          {can("clinical:read") && <EncounterOrdersCard patientId={enc.patient_id} encounterId={enc.id} diagnosisCodes={enc.diagnoses.map((d) => d.code)} editable={open} />}
          {summary.data?.clinical_access && (
            <Card>
              <CardHeader className="pb-2"><CardTitle>Patient context</CardTitle><Link to={`/patients/${enc.patient_id}`} className="text-table font-medium text-primary hover:underline">Full chart</Link></CardHeader>
              <CardContent className="space-y-3 text-table">
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Active problems</p>
                  {summary.data.problems?.length ? <ul className="space-y-0.5">{summary.data.problems.map((p) => <li key={p.id}>{p.description}</li>)}</ul> : <p className="text-muted-foreground">None</p>}
                </div>
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Medications</p>
                  {summary.data.medications?.length ? <ul className="space-y-0.5">{summary.data.medications.map((m) => <li key={m.id}>{m.name} <span className="text-muted-foreground">{m.dose}</span></li>)}</ul> : <p className="text-muted-foreground">None</p>}
                </div>
              </CardContent>
            </Card>
          )}
          {!open && (
            <div className="flex items-center gap-2 rounded-lg border bg-success-soft px-3 py-2 text-table text-success">
              <ClipboardCheck className="size-4" />Visit {enc.status} {enc.completed_at ? fmtDateTime(enc.completed_at) : ""}
            </div>
          )}
        </div>
      </div>
      <VitalsDialog patientId={enc.patient_id} encounterId={enc.id} open={vitalsOpen} onOpenChange={setVitalsOpen} />
      {note && <VersionHistory noteId={note.id} open={historyOpen} onOpenChange={setHistoryOpen} />}
      <ChartAssistant patientId={enc.patient_id} patientName={enc.patient.name} open={askOpen} onOpenChange={setAskOpen} />
    </>
  );
}
