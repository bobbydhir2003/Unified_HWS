import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FlaskConical, Keyboard, Loader2, Mic, MicOff, Pause, Pill, Play, RefreshCw, Sparkles, Square, Trash2, Wand2 } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { AIBadge, SimulatedBadge, toastError, useConfirm } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, get, post } from "@/lib/api";
import type { NoteContent } from "@/lib/types";
import { cn } from "@/lib/utils";

type Seg = { speaker: "clinician" | "patient" | "other"; text: string };
type Session = {
  id: string; status: "recording" | "transcribing" | "transcribed" | "drafting" | "ready" | "applied" | "discarded" | "failed";
  consent_method: string; consent_recorded_at: string; transcript_source: "audio" | "manual" | "synthetic_demo" | null;
  audio_seconds: number | null; transcript: Seg[] | null; transcript_edited: boolean; error: string | null; draft_count: number;
  applied_note_version: number | null;
  draft: null | (NoteContent & { chief_complaint: string | null; follow_up: string | null; medications_mentioned: string[];
    allergies_mentioned: string[]; uncertainties: string[]; provider: string; model: string | null });
};

const SECTIONS: (keyof NoteContent)[] = ["subjective", "objective", "assessment", "plan"];
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export function parseTranscript(text: string): Seg[] {
  const out: Seg[] = [];
  for (const raw of text.split(/\n+/)) {
    const line = raw.trim();
    if (!line) continue;
    const m = line.match(/^(dr\.?|doctor|clinician|provider|np|pa|patient|pt|parent|guardian|other)\s*:\s*(.*)$/i);
    if (m) {
      const who = m[1].toLowerCase();
      out.push({ speaker: /^(patient|pt)$/.test(who) ? "patient" : /^(parent|guardian|other)$/.test(who) ? "other" : "clinician", text: m[2] });
    } else if (out.length) out[out.length - 1].text += ` ${line}`;
    else out.push({ speaker: "other", text: line });
  }
  return out.filter((s) => s.text.trim());
}
const toText = (segs: Seg[]) => segs.map((s) => `${s.speaker === "clinician" ? "Clinician" : s.speaker === "patient" ? "Patient" : "Other"}: ${s.text}`).join("\n");

function Recorder({ onDone }: { onDone: (blob: Blob, seconds: number) => void }) {
  const [state, setState] = React.useState<"idle" | "recording" | "paused">("idle");
  const [seconds, setSeconds] = React.useState(0);
  const [level, setLevel] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);
  const rec = React.useRef<MediaRecorder | null>(null);
  const chunks = React.useRef<Blob[]>([]);
  const stream = React.useRef<MediaStream | null>(null);
  const raf = React.useRef<number>(0);
  const ctx = React.useRef<AudioContext | null>(null);

  React.useEffect(() => {
    if (state !== "recording") return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [state]);
  const cleanup = () => {
    cancelAnimationFrame(raf.current);
    stream.current?.getTracks().forEach((t) => t.stop());
    ctx.current?.close().catch(() => {});
  };
  React.useEffect(() => cleanup, []);

  const start = async () => {
    setError(null);
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      stream.current = s;
      const r = new MediaRecorder(s);
      chunks.current = [];
      r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      r.start(1000);
      rec.current = r;
      const ac = new AudioContext();
      ctx.current = ac;
      const an = ac.createAnalyser();
      an.fftSize = 512;
      ac.createMediaStreamSource(s).connect(an);
      const buf = new Uint8Array(an.frequencyBinCount);
      const tick = () => {
        an.getByteTimeDomainData(buf);
        let peak = 0;
        for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
        setLevel(Math.min(1, peak / 64));
        raf.current = requestAnimationFrame(tick);
      };
      tick();
      setSeconds(0);
      setState("recording");
    } catch (e) {
      setError(e instanceof DOMException && e.name === "NotAllowedError"
        ? "Microphone access was blocked. Allow it in your browser's site settings, or type the conversation instead."
        : "No microphone is available on this device. Type the conversation instead.");
    }
  };
  const pause = () => { rec.current?.pause(); setState("paused"); };
  const resume = () => { rec.current?.resume(); setState("recording"); };
  const stop = () => {
    const r = rec.current;
    if (!r) return;
    r.onstop = () => {
      cleanup();
      onDone(new Blob(chunks.current, { type: r.mimeType || "audio/webm" }), seconds);
      setState("idle");
    };
    r.stop();
  };

  return (
    <div className="space-y-3">
      {error && <p role="alert" className="flex items-start gap-1.5 text-table text-destructive"><MicOff className="mt-0.5 size-4 shrink-0" />{error}</p>}
      <div className="flex items-center gap-3">
        {state === "idle" ? (
          <Button onClick={start}><Mic />Start recording</Button>
        ) : (
          <>
            <span className={cn("flex items-center gap-2 rounded-full px-3 py-1 text-table font-medium tabular", state === "recording" ? "bg-destructive-soft text-destructive" : "bg-muted text-muted-foreground")}>
              <span className={cn("size-2 rounded-full", state === "recording" ? "animate-pulse bg-destructive" : "bg-muted-foreground")} />
              {state === "recording" ? "Recording" : "Paused"} {mmss(seconds)}
            </span>
            <span className="h-2 w-24 overflow-hidden rounded-full bg-muted" aria-label="Microphone level"><span className="block h-full bg-success transition-[width]" style={{ width: `${level * 100}%` }} /></span>
            {state === "recording" ? <Button variant="outline" size="sm" onClick={pause}><Pause />Pause</Button> : <Button variant="outline" size="sm" onClick={resume}><Play />Resume</Button>}
            <Button variant="destructive" size="sm" onClick={stop}><Square />Stop</Button>
          </>
        )}
      </div>
      <p className="text-xs text-muted-foreground">Audio is uploaded only when you stop, and is deleted after transcription.</p>
    </div>
  );
}

export function ScribePanel({ encounterId, patientId, chartAllergies, noteId, noteVersion, noteDirty, synthetic, onApplied, onClose }: {
  encounterId: string; patientId: string; chartAllergies: string[] | null; noteId?: string; noteVersion?: number; noteDirty: boolean;
  synthetic: boolean; onApplied: () => void; onClose: () => void;
}) {
  const qc = useQueryClient();
  const { confirm, dialog } = useConfirm();
  const key = ["scribe", encounterId];
  const q = useQuery({
    queryKey: key, queryFn: () => get<Session | null>(`/encounters/${encounterId}/scribe`),
    refetchInterval: (query) => (["transcribing", "drafting"].includes(query.state.data?.status ?? "") ? 1200 : false),
  });
  const s = q.data;
  const [consent, setConsent] = React.useState(false);
  const [method, setMethod] = React.useState<"verbal" | "written">("verbal");
  const [typed, setTyped] = React.useState("");
  const [editingTranscript, setEditingTranscript] = React.useState(false);
  const [sections, setSections] = React.useState<NoteContent | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  React.useEffect(() => { if (s?.draft) setSections({ subjective: s.draft.subjective, objective: s.draft.objective, assessment: s.draft.assessment, plan: s.draft.plan }); }, [s?.draft_count]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (v: Session) => qc.setQueryData(key, v);
  const run = async (k: string, fn: () => Promise<Session>) => {
    setBusy(k);
    try { set(await fn()); } catch (e) { toastError(e); } finally { setBusy(null); }
  };

  if (q.isLoading) return null;
  const active = s && !["applied", "discarded"].includes(s.status) ? s : null;

  const header = (
    <CardHeader className="border-b pb-3">
      <div className="flex flex-wrap items-center gap-2">
        <CardTitle className="flex items-center gap-2"><Sparkles className="size-4 text-ai" />AI scribe</CardTitle>
        {active && <Badge variant="outline">Consent: {active.consent_method}</Badge>}
        {active?.transcript_source === "synthetic_demo" && <SimulatedBadge label="Synthetic demo conversation" />}
      </div>
      <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
    </CardHeader>
  );

  if (!active) {
    return (
      <Card className="border-ai/30">
        {header}
        <CardContent className="space-y-4 pt-4">
          {s?.status === "applied" && <p className="text-table text-success">Last draft was inserted into the note (v{s.applied_note_version}).</p>}
          <p className="text-table text-muted-foreground">Capture the visit conversation and get a draft SOAP note to review. Nothing is added to the chart until you insert it, and AI-drafted notes need your attestation to sign.</p>
          <div className="flex gap-2" role="radiogroup" aria-label="Consent method">
            {(["verbal", "written"] as const).map((m) => (
              <button key={m} role="radio" aria-checked={method === m} onClick={() => setMethod(m)}
                className={cn("rounded-lg border px-3 py-1.5 text-table capitalize", method === m && "border-primary bg-accent/50 font-medium")}>{m} consent</button>
            ))}
          </div>
          <label className="flex items-start gap-2 rounded-lg border p-3 text-table">
            <Checkbox checked={consent} onCheckedChange={(c) => setConsent(!!c)} className="mt-0.5" />
            <span>The patient (or their representative) was informed and agreed to this visit being recorded and documented with AI assistance.</span>
          </label>
          <Button disabled={!consent} loading={busy === "start"} onClick={() => run("start", () => post(`/encounters/${encounterId}/scribe`, { consent_method: method, consent_confirmed: true }))}>
            <Mic />Start scribe session
          </Button>
        </CardContent>
      </Card>
    );
  }

  const processing = active.status === "transcribing" || active.status === "drafting";
  const capture = active.status === "recording" || active.status === "failed";

  return (
    <Card className="border-ai/30">
      {dialog}
      {header}
      <CardContent className="space-y-4 pt-4">
        {active.status === "failed" && active.error && (
          <div role="alert" className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive-soft px-3 py-2 text-table text-destructive">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />{active.error}
          </div>
        )}
        {processing && (
          <p className="flex items-center gap-2 text-body"><Loader2 className="size-4 animate-spin text-ai" />{active.status === "transcribing" ? "Transcribing recording…" : "Drafting SOAP note…"}</p>
        )}
        {capture && (
          <Tabs defaultValue="record">
            <TabsList>
              <TabsTrigger value="record"><Mic />Record</TabsTrigger>
              <TabsTrigger value="type"><Keyboard />Type or paste</TabsTrigger>
              {synthetic && <TabsTrigger value="demo"><FlaskConical />Synthetic demo</TabsTrigger>}
            </TabsList>
            <TabsContent value="record">
              <Recorder onDone={async (blob, seconds) => {
                const fd = new FormData();
                fd.append("file", blob, "visit.webm");
                fd.append("seconds", String(seconds));
                await run("audio", () => api<Session>(`/scribe/${active.id}/audio`, { method: "POST", body: fd }));
              }} />
            </TabsContent>
            <TabsContent value="type" className="space-y-2">
              <Textarea rows={7} value={typed} onChange={(e) => setTyped(e.target.value)} aria-label="Conversation"
                placeholder={"Clinician: What brings you in today?\nPatient: I've had a cough for five days…"} />
              <p className="text-xs text-muted-foreground">Start lines with “Clinician:” or “Patient:” so speakers are labeled.</p>
              <Button disabled={parseTranscript(typed).length === 0} loading={busy === "typed"}
                onClick={() => run("typed", () => post(`/scribe/${active.id}/transcript`, { segments: parseTranscript(typed) }))}>
                <Wand2 />Draft note from conversation
              </Button>
            </TabsContent>
            {synthetic && (
              <TabsContent value="demo" className="space-y-2">
                <p className="text-table text-muted-foreground">Loads a scripted, fictional conversation matched to the chief complaint so you can try the workflow. It is not this patient's visit.</p>
                <Button variant="outline" loading={busy === "demo"} onClick={() => run("demo", () => post(`/scribe/${active.id}/demo`))}><FlaskConical />Use synthetic conversation</Button>
              </TabsContent>
            )}
          </Tabs>
        )}

        {active.status === "ready" && active.draft && sections && (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <section aria-label="Transcript" className="min-w-0">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-table font-semibold">Transcript {active.transcript_edited && <span className="font-normal text-muted-foreground">(edited)</span>}</h3>
                <Button size="xs" variant="ghost" onClick={() => { setTyped(toText(active.transcript ?? [])); setEditingTranscript((v) => !v); }}>{editingTranscript ? "Cancel" : "Edit"}</Button>
              </div>
              {editingTranscript ? (
                <div className="space-y-2">
                  <Textarea rows={12} value={typed} onChange={(e) => setTyped(e.target.value)} aria-label="Edit transcript" />
                  <Button size="sm" loading={busy === "retx"} disabled={!parseTranscript(typed).length}
                    onClick={async () => { await run("retx", () => post(`/scribe/${active.id}/transcript`, { segments: parseTranscript(typed) })); setEditingTranscript(false); }}>
                    Save & redraft
                  </Button>
                </div>
              ) : (
                <ol className="max-h-[420px] space-y-2 overflow-y-auto rounded-lg border bg-muted/30 p-3 text-table">
                  {active.transcript?.map((t, i) => (
                    <li key={i} className="flex gap-2">
                      <span className={cn("mt-0.5 shrink-0 rounded px-1.5 text-label font-semibold uppercase", t.speaker === "clinician" ? "bg-accent text-accent-foreground" : t.speaker === "patient" ? "bg-success-soft text-success" : "bg-muted text-muted-foreground")}>
                        {t.speaker === "clinician" ? "Clin" : t.speaker === "patient" ? "Pt" : "Oth"}
                      </span>
                      <span>{t.text}</span>
                    </li>
                  ))}
                </ol>
              )}
            </section>
            <section aria-label="Draft note" className="min-w-0 space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-table font-semibold">Draft note</h3>
                <AIBadge label="AI draft — review every line" />
                {active.draft.provider === "simulated" && <SimulatedBadge label="Rule-based simulation" />}
              </div>
              {active.draft.uncertainties.length > 0 && (
                <ul className="space-y-1 rounded-lg bg-warning-soft px-3 py-2 text-table">
                  {active.draft.uncertainties.map((u, i) => <li key={i} className="flex gap-1.5"><AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" />{u}</li>)}
                </ul>
              )}
              {SECTIONS.map((k) => (
                <div key={k}>
                  <label htmlFor={`scribe-${k}`} className="text-label font-semibold uppercase tracking-wide text-muted-foreground">{k}</label>
                  <Textarea id={`scribe-${k}`} rows={k === "plan" || k === "subjective" ? 4 : 3} value={sections[k]} onChange={(e) => setSections({ ...sections, [k]: e.target.value })} className="mt-1" />
                </div>
              ))}
              {(() => {
                const known = (chartAllergies ?? []).map((a) => a.toLowerCase());
                const missing = chartAllergies ? active.draft.allergies_mentioned.filter((a) => !known.some((k) => k.includes(a.toLowerCase()) || a.toLowerCase().includes(k))) : [];
                return missing.length > 0 && (
                  <div role="alert" className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive-soft px-3 py-2 text-table text-destructive">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                    <span><strong>Allergy discrepancy:</strong> {missing.join(", ")} mentioned in the conversation but not on the chart's allergy list.{" "}
                      <Link to={`/patients/${patientId}/allergies`} className="font-medium underline">Review allergies</Link></span>
                  </div>
                );
              })()}
              {active.draft.medications_mentioned.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 text-xs">
                  <span className="text-muted-foreground">Medications mentioned:</span>
                  {active.draft.medications_mentioned.map((m) => <Badge key={m} variant="outline"><Pill />{m}</Badge>)}
                </div>
              )}
              {active.draft.follow_up && <p className="text-table"><span className="text-muted-foreground">Follow-up mentioned:</span> {active.draft.follow_up}</p>}
              <p className="text-label text-muted-foreground">Mentioned medications and allergies are not added to the chart lists automatically — update them in the chart if appropriate.</p>
              {noteDirty && <p className="text-table text-warning">Save or discard your unsaved note edits before inserting the draft.</p>}
              <div className="flex flex-wrap gap-2">
                <Button disabled={noteDirty} loading={busy === "apply"} onClick={async () => {
                  let mode: "replace" | "append" = "replace";
                  if (noteId && (noteVersion ?? 0) > 0) {
                    const choice = await confirm({ title: "Insert draft into the note?", description: "Your existing note text is kept; the AI draft is appended below it in each section. You can edit everything before signing.", confirmLabel: "Append to note" });
                    if (!choice) return;
                    mode = "append";
                  }
                  setBusy("apply");
                  try {
                    set(await post<Session>(`/scribe/${active.id}/apply`, { mode, expected_version: noteVersion ?? null, sections }));
                    toast.success("Draft inserted into the note — review and edit before signing");
                    onApplied();
                  } catch (e) { toastError(e); } finally { setBusy(null); }
                }}><Wand2 />Insert into note</Button>
                <Button variant="outline" loading={busy === "regen"} onClick={() => run("regen", () => post(`/scribe/${active.id}/regenerate`))}><RefreshCw />Regenerate</Button>
                <Button variant="ghost" className="text-destructive" onClick={async () => {
                  if (await confirm({ title: "Discard this scribe session?", description: "The transcript and draft will be discarded; any recording is deleted.", destructive: true, confirmLabel: "Discard" }))
                    run("discard", () => post(`/scribe/${active.id}/discard`));
                }}><Trash2 />Discard</Button>
              </div>
            </section>
          </div>
        )}
        {capture && (
          <div className="flex justify-end">
            <Button variant="ghost" size="sm" className="text-destructive" onClick={() => run("discard", () => post(`/scribe/${active.id}/discard`))}><Trash2 />Cancel session</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
