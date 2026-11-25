/**
 * HMS Voice Concierge — staff console for the conversational front-desk agent.
 *
 * Everything shown comes from the server: the call's transcript, verification state, workflow steps (derived from the
 * tool/action log), the records it actually created, the outcome, and the stats. Typed test calls and browser voice
 * sessions (OpenAI Realtime over WebRTC) use the same server-side engine and tools; the browser only relays the voice
 * model's tool requests and transcripts — it never executes anything. No telephony is connected unless the server says so.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowRight, AudioLines, CalendarCheck2, CalendarClock, CheckCircle2, Circle, CircleDot, Headset, Info, Loader2, Mic,
  MicOff, Phone, PhoneCall, PhoneOff, Send, ShieldAlert, ShieldCheck, ShieldQuestion, Users, Workflow, XCircle,
} from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ErrorState, LoadingRows, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, titleCase } from "@/lib/utils";

type Rec = { type: "appointment" | "task"; id: string; ref: string; label: string; link: string };
type Ev = { at: string; tool: string; status: "ok" | "refused" | "failed" | "pending" | "info"; label: string; detail: string | null };
type Step = { key: string; label: string; status: "done" | "in_progress" | "failed" | "not_started"; detail: string };
type Summary = { id: string; status: string; mode: string; channel: string; created_at: string; ended_at: string | null; duration_seconds: number;
  caller: string; verification: string; intent: string | null; outcome_code: string | null; outcome: string | null; end_reason: string | null;
  records: Rec[]; summary: string | null; follow_up: string | null };
type Detail = Summary & { from_number: string | null; consented: boolean; facility: { id: string; name: string; timezone: string } | null;
  patient: { id: string; name: string; mrn: string } | null; transcript: { speaker: string; text: string; at: string }[]; events: Ev[];
  workflow: Step[]; offers: { ref: string; label: string }[]; pending: string | null; test_code: string | null; stage: string };
type Overview = { stats: { active: number; pending_callbacks: number; completed_today: number; escalations_open: number };
  conversation: { mode: "openai" | "built_in"; model: string | null; reason: string | null };
  voice: { mode: "openai" | "simulated"; model: string | null; reason: string | null };
  telephony: { enabled: boolean; note: string | null }; synthetic: boolean; test_writes: boolean; timezone: string };

const PHRASES = ["I'd like to book an appointment", "It's Elena Moreau, April 12, 1986", "Can I come tomorrow?", "Actually, make that Friday",
  "Yes, please book it", "I need to reschedule my visit", "Where is your radiology department?", "What time do you open?",
  "Can someone call me back?", "I want to speak to a real person"];
const OUTCOMES: { code: string[]; label: string; icon: typeof CalendarCheck2 }[] = [
  { code: ["booked", "rescheduled", "cancelled"], label: "Appointment updated", icon: CalendarCheck2 },
  { code: ["callback"], label: "Callback requested", icon: PhoneCall },
  { code: ["handoff", "emergency"], label: "Handed to staff", icon: Users },
  { code: ["unresolved", "abandoned", "info"], label: "No change made", icon: AlertTriangle },
];
const OUTCOME_BADGE: Record<string, React.ComponentProps<typeof Badge>["variant"]> = {
  booked: "success", rescheduled: "success", cancelled: "warning", callback: "warning", handoff: "info", emergency: "danger", info: "neutral", unresolved: "danger", abandoned: "neutral",
};

function fmtDur(s: number) { return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; }
function fmtTime(iso: string) {
  const d = new Date(iso);
  const today = new Date().toDateString() === d.toDateString();
  return (today ? "Today " : d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + ", ") + d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
const VERIF: Record<string, { label: string; variant: React.ComponentProps<typeof Badge>["variant"]; icon: typeof ShieldCheck }> = {
  verified: { label: "Verified", variant: "success", icon: ShieldCheck }, code_sent: { label: "Code sent", variant: "warning", icon: ShieldQuestion },
  failed: { label: "Not verified", variant: "danger", icon: ShieldAlert }, unverified: { label: "Unverified", variant: "neutral", icon: ShieldQuestion },
};

// ============================================================================================ browser voice (Realtime)
type VoiceState = "idle" | "connecting" | "live" | "error";
function useVoice(callId: string | null, onChange: () => void) {
  const [state, setState] = React.useState<VoiceState>("idle");
  const [error, setError] = React.useState<string | null>(null);
  const [muted, setMuted] = React.useState(false);
  const pc = React.useRef<RTCPeerConnection | null>(null);
  const mic = React.useRef<MediaStream | null>(null);
  const audio = React.useRef<HTMLAudioElement | null>(null);
  const pendingSpeech = React.useRef(0);

  const stop = React.useCallback(() => {
    pc.current?.close(); pc.current = null;
    mic.current?.getTracks().forEach((t) => t.stop()); mic.current = null;
    setState((s) => (s === "error" ? s : "idle"));
  }, []);
  React.useEffect(() => stop, [stop]);

  const start = async () => {
    if (!callId) return;
    setState("connecting"); setError(null);
    try {
      const s = await post<{ mode: string; value?: string; calls_url?: string; reason?: string; greeting?: string }>(`/receptionist/calls/${callId}/voice/session`, {});
      if (s.mode !== "openai" || !s.value || !s.calls_url) { setError(s.reason ?? "Realtime voice isn't configured."); setState("error"); return; }
      if (!navigator.mediaDevices?.getUserMedia) { setError("This browser can't use a microphone."); setState("error"); return; }
      try { mic.current = await navigator.mediaDevices.getUserMedia({ audio: true }); }
      catch (e) { setError((e as Error).name === "NotAllowedError" ? "Microphone access was denied. Allow it in the browser to use voice." : "No microphone was found."); setState("error"); return; }
      const conn = new RTCPeerConnection();
      pc.current = conn;
      conn.ontrack = (e) => { if (audio.current) audio.current.srcObject = e.streams[0]; };
      mic.current.getTracks().forEach((t) => conn.addTrack(t, mic.current!));
      conn.onconnectionstatechange = () => { if (["failed", "disconnected"].includes(conn.connectionState)) { setError("The voice connection dropped."); stop(); } };
      const ch = conn.createDataChannel("oai-events");
      const relay = (speaker: "caller" | "assistant", text: string) =>
        post<{ emergency?: boolean; say?: string }>(`/receptionist/calls/${callId}/voice/utterance`, { speaker, text }).then((r) => {
          onChange();
          if (r.emergency && r.say && ch.readyState === "open") ch.send(JSONstr({ type: "response.create", response: { instructions: `Say exactly: ${r.say}` } }));
        }).catch(() => undefined);
      const waitForCallerText = async () => { for (let i = 0; i < 30 && pendingSpeech.current > 0; i++) await new Promise((r) => setTimeout(r, 100)); };
      const runTool = async (name: string, callIdTool: string, raw: string) => {
        let output: unknown;
        try {
          if (name === "confirm_pending_action") await waitForCallerText();  // the server checks the caller's latest words
          output = await post(`/receptionist/calls/${callId}/voice/tools/${encodeURIComponent(name)}`, JSON.parse(raw || "{}"));
        } catch { output = { ok: false, error: "That action failed on the server. Nothing was changed. Offer a staff callback." }; }
        onChange();
        if (ch.readyState !== "open") return;
        ch.send(JSONstr({ type: "conversation.item.create", item: { type: "function_call_output", call_id: callIdTool, output: JSON.stringify(output) } }));
        ch.send(JSONstr({ type: "response.create" }));
      };
      ch.onopen = () => { if (s.greeting) ch.send(JSONstr({ type: "response.create", response: { instructions: `Greet the caller by saying exactly: ${s.greeting}` } })); };
      ch.onmessage = (m) => {
        try {
          const ev = JSON.parse(m.data) as { type: string; transcript?: string; item?: { type?: string; name?: string; call_id?: string; arguments?: string } };
          if (ev.type === "input_audio_buffer.speech_stopped") pendingSpeech.current += 1;
          else if (ev.type === "conversation.item.input_audio_transcription.completed") { pendingSpeech.current = Math.max(0, pendingSpeech.current - 1); if (ev.transcript?.trim()) void relay("caller", ev.transcript); }
          else if (ev.type === "conversation.item.input_audio_transcription.failed") pendingSpeech.current = Math.max(0, pendingSpeech.current - 1);
          else if ((ev.type === "response.output_audio_transcript.done" || ev.type === "response.audio_transcript.done") && ev.transcript) void relay("assistant", ev.transcript);
          else if (ev.type === "response.output_item.done" && ev.item?.type === "function_call" && ev.item.name && ev.item.call_id) void runTool(ev.item.name, ev.item.call_id, ev.item.arguments ?? "{}");
          else if (ev.type === "error") setError("The voice service reported an error.");
        } catch { /* non-JSON event */ }
      };
      const offer = await conn.createOffer();
      await conn.setLocalDescription(offer);
      const r = await fetch(s.calls_url, { method: "POST", body: offer.sdp, headers: { Authorization: `Bearer ${s.value}`, "Content-Type": "application/sdp" } });
      if (!r.ok) throw new Error(`The voice service refused the session (${r.status}).`);
      await conn.setRemoteDescription({ type: "answer", sdp: await r.text() });
      setState("live");
    } catch (e) {
      stop(); setError((e as Error).message || "Couldn't start voice."); setState("error");
    }
  };
  const toggleMute = () => { mic.current?.getAudioTracks().forEach((t) => { t.enabled = muted; }); setMuted(!muted); };
  return { state, error, muted, start, stop, toggleMute, audio };
}
const JSONstr = (x: unknown) => JSON.stringify(x);

// ============================================================================================ page
export function VoiceConciergePage() {
  const qc = useQueryClient();
  const { can } = useAuth();
  const canRun = can("schedule:write");
  const [params, setParams] = useSearchParams();
  const callId = params.get("call");
  const ov = useQuery({ queryKey: ["concierge", "overview"], queryFn: () => get<Overview>("/receptionist/overview"), refetchInterval: 20_000 });
  const calls = useQuery({ queryKey: ["concierge", "calls"], queryFn: () => get<Summary[]>("/receptionist/calls"), refetchInterval: 20_000 });
  const detail = useQuery({ queryKey: ["concierge", "call", callId], queryFn: () => get<Detail>(`/receptionist/calls/${callId}`), enabled: !!callId && canRun,
    refetchInterval: (q) => (q.state.data?.status === "active" && q.state.data.channel === "browser_voice" ? 2500 : false) });
  const call = callId ? detail.data ?? null : null;
  const refresh = React.useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["concierge"] });
  }, [qc]);
  const voice = useVoice(call?.status === "active" && call.channel === "browser_voice" ? call.id : null, refresh);
  const setCall = (d: Detail | null) => {
    if (d) qc.setQueryData(["concierge", "call", d.id], d);
    const next = new URLSearchParams(params);
    if (d) next.set("call", d.id); else next.delete("call");
    setParams(next, { replace: true });
  };
  const startCall = async (channel: "text" | "browser_voice") => {
    try { const d = await post<Detail>("/receptionist/calls", { from_number: "+1 (555) 010-7788", channel }); setCall(d); refresh(); }
    catch (e) { toastError(e); }
  };
  const endCall = async () => {
    if (!call) return;
    voice.stop();
    try { qc.setQueryData(["concierge", "call", call.id], await post<Detail>(`/receptionist/calls/${call.id}/end`)); refresh(); } catch (e) { toastError(e); }
  };
  const o = ov.data;

  return (
    <div className="space-y-4" data-testid="voice-concierge">
      {/* Header */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <p className="text-label font-medium text-muted-foreground">AI &amp; automation</p>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-title font-semibold text-heading">HMS Voice Concierge</h1>
            {o && <ConnectionPill o={o} />}
          </div>
          <p className="mt-0.5 text-body text-muted-foreground">Intelligent assistance for administrative calls, appointments, callbacks, and staff handoffs.</p>
        </div>
        <Card className="flex w-full items-start gap-3 border-ai/25 bg-ai-soft/40 p-3.5 lg:w-[380px]" data-testid="concierge-engine">
          <span className="grid size-10 shrink-0 place-items-center rounded-full bg-ai-soft text-ai"><AudioLines className="size-5" aria-hidden /></span>
          <div className="min-w-0 text-table">
            <p className="font-semibold text-heading">Concierge engine</p>
            {!o ? <p className="text-muted-foreground">Checking configuration…</p> : <ul className="mt-0.5 space-y-0.5 text-muted-foreground">
              <li>Conversation: <span className="font-medium text-foreground">{o.conversation.mode === "openai" ? `OpenAI · ${o.conversation.model}` : "Built-in language engine"}</span></li>
              <li>Browser voice: <span className="font-medium text-foreground">{o.voice.mode === "openai" ? `Realtime · ${o.voice.model}` : "Not configured"}</span></li>
              <li>Phone line: <span className="font-medium text-foreground">{o.telephony.enabled ? "Connected" : "Not connected"}</span></li>
            </ul>}
          </div>
        </Card>
      </div>

      {/* Stats */}
      <ul className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="concierge-stats">
        <StatTile icon={Phone} label="Active calls" value={o?.stats.active} hint="Last 2 hours" />
        <StatTile icon={CalendarClock} label="Pending callbacks" value={o?.stats.pending_callbacks} hint="Open callback tasks" link="/worklist" />
        <StatTile icon={CheckCircle2} label="Today's completed requests" value={o?.stats.completed_today} hint="Calls with a recorded result" />
        <StatTile icon={Users} label="Escalations to staff" value={o?.stats.escalations_open} hint="Open handoffs and urgent alerts" link="/worklist" tone={o?.stats.escalations_open ? "warning" : undefined} />
      </ul>

      {/* Three panels */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.15fr_1fr_1fr]">
        <LiveCall call={call} loading={!!callId && detail.isLoading} error={detail.isError} canRun={canRun} o={o} voice={voice}
          onStart={startCall} onEnd={endCall} onUpdate={(d) => { qc.setQueryData(["concierge", "call", d.id], d); if (d.status !== "active") refresh(); else { void qc.invalidateQueries({ queryKey: ["concierge", "overview"] }); void qc.invalidateQueries({ queryKey: ["concierge", "calls"] }); } }} />
        <WorkflowPanel call={call} canRun={canRun} onUpdate={(d) => { qc.setQueryData(["concierge", "call", d.id], d); refresh(); }} />
        <div className="space-y-4">
          <OutcomePanel call={call} />
          <CallLog rows={calls.data} loading={calls.isLoading} selected={callId} onOpen={(id) => { const n = new URLSearchParams(params); n.set("call", id); setParams(n, { replace: true }); }} />
        </div>
      </div>

      <p className="flex items-start gap-2 rounded-lg border bg-card px-3 py-2 text-table text-muted-foreground" data-testid="concierge-policy">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>Administrative help only — no medical advice. Appointment details are shared and changed only after identity verification (name, date of birth and a one-time
          code sent to the patient portal) and an explicit yes from the caller. {o && !o.telephony.enabled && "No phone line is connected: browser voice sessions are staff tests, not phone calls, and there are no live call transfers."}
          {o && !o.test_writes && " Test calls in this organization never change appointments."}</span>
      </p>
    </div>
  );
}

function ConnectionPill({ o }: { o: Overview }) {
  if (o.telephony.enabled) return <Badge variant="success" data-testid="concierge-connection"><CircleDot className="size-3" />Phone line connected</Badge>;
  if (o.voice.mode === "openai") return <Badge variant="info" data-testid="concierge-connection"><CircleDot className="size-3" />Browser voice ready · test mode</Badge>;
  return <Badge variant="neutral" data-testid="concierge-connection"><CircleDot className="size-3" />Text test mode</Badge>;
}

function StatTile({ icon: Icon, label, value, hint, link, tone }: { icon: typeof Phone; label: string; value: number | undefined; hint: string; link?: string; tone?: "warning" }) {
  const body = (
    <span className="flex h-full items-start gap-3 rounded-xl border bg-card p-3.5 shadow-sm">
      <span className={cn("grid size-9 shrink-0 place-items-center rounded-lg", tone === "warning" ? "bg-warning-soft text-warning-foreground" : "bg-accent text-accent-foreground")}><Icon className="size-4" aria-hidden /></span>
      <span className="min-w-0"><span className="block text-label font-medium text-muted-foreground">{label}</span>
        <span className={cn("block text-2xl font-semibold tabular text-heading", !value && "text-muted-foreground")}>{value ?? "—"}</span>
        <span className="block text-label text-muted-foreground">{hint}</span></span>
    </span>
  );
  return <li>{link ? <Link to={link} className="block h-full rounded-xl hover:ring-1 hover:ring-primary/30">{body}</Link> : body}</li>;
}

// ---------------------------------------------------------------------------------------------- left: live call
function LiveCall({ call, loading, error, canRun, o, voice, onStart, onEnd, onUpdate }: {
  call: Detail | null; loading: boolean; error: boolean; canRun: boolean; o?: Overview; voice: ReturnType<typeof useVoice>;
  onStart: (c: "text" | "browser_voice") => void; onEnd: () => void; onUpdate: (d: Detail) => void;
}) {
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const pane = React.useRef<HTMLDivElement>(null);
  const [now, setNow] = React.useState(Date.now());
  React.useEffect(() => { const t = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(t); }, []);
  React.useEffect(() => { pane.current?.scrollTo({ top: pane.current.scrollHeight, behavior: "smooth" }); }, [call?.transcript.length]);
  const active = call?.status === "active";
  const dur = call ? (active ? Math.max(0, Math.round((now - new Date(call.created_at).getTime()) / 1000)) : call.duration_seconds) : 0;
  const send = async (t: string) => {
    if (!call || !t.trim() || busy) return;
    setBusy(true);
    try { onUpdate(await post<Detail>(`/receptionist/calls/${call.id}/message`, { text: t })); setText(""); }
    catch (e) { toastError(e); } finally { setBusy(false); }
  };
  const v = VERIF[call?.verification ?? "unverified"];
  return (
    <Card className="flex flex-col overflow-hidden" data-testid="live-call">
      <div className="flex items-center justify-between gap-2 border-b px-4 py-3">
        <h2 className="flex items-center gap-2 text-section font-semibold text-heading"><Phone className="size-4 text-primary" aria-hidden />Live call</h2>
        <div className="flex items-center gap-2">
          {call && <span className="rounded-md border px-2 py-0.5 font-mono text-table tabular" data-testid="call-duration">{fmtDur(dur)}</span>}
          {active ? <Button size="sm" variant="destructive" onClick={onEnd} data-testid="end-call"><PhoneOff />End call</Button>
            : canRun && <>
              <Button size="sm" variant="outline" onClick={() => onStart("browser_voice")} disabled={o?.voice.mode !== "openai"} title={o?.voice.mode !== "openai" ? o?.voice.reason ?? "" : "Browser voice test (not a phone call)"} data-testid="start-voice-call"><Mic />Voice test</Button>
              <Button size="sm" onClick={() => onStart("text")} data-testid="start-call"><PhoneCall />{call ? "New test call" : "Start test call"}</Button>
            </>}
        </div>
      </div>
      {call && (
        <div className="grid grid-cols-3 gap-2 border-b bg-muted/30 px-4 py-2.5 text-table" data-testid="call-strip">
          <div className="min-w-0"><p className="text-label text-muted-foreground">Caller</p><p className="truncate font-medium" data-testid="caller-name">{call.patient?.name ?? "Unverified caller"}</p>
            <p className="truncate text-label text-muted-foreground">{call.from_number ?? "No number"}</p></div>
          <div><p className="text-label text-muted-foreground">Verification</p><Badge variant={v.variant} data-testid="caller-verification"><v.icon className="size-3" />{v.label}</Badge></div>
          <div className="min-w-0"><p className="text-label text-muted-foreground">Intent detected</p>
            {call.intent ? <Badge variant="primary" data-testid="caller-intent">{titleCase(call.intent.replace("_", " "))}</Badge> : <span className="text-muted-foreground">—</span>}</div>
        </div>
      )}
      <div ref={pane} className="h-[420px] space-y-2.5 overflow-y-auto p-4 xl:h-[min(52dvh,520px)]" data-testid="call-transcript" aria-live="polite">
        {loading ? <LoadingRows /> : error ? <ErrorState error={new Error("Couldn't load this call.")} /> : !call ? (
          <div className="grid h-full place-items-center text-center">
            <div className="max-w-sm space-y-2">
              <span className="mx-auto grid size-12 place-items-center rounded-full bg-accent text-accent-foreground"><Headset className="size-6" aria-hidden /></span>
              <p className="font-medium text-heading">No call open</p>
              <p className="text-table text-muted-foreground">{canRun ? "Start a test call and speak as the caller — for example, book as the synthetic patient Elena Moreau (DOB April 12, 1986). Open any call in the log to review it." : "Open a call from the log to review it."}</p>
            </div>
          </div>
        ) : call.transcript.map((t, i) => (
          <div key={i} className={cn("max-w-[88%] rounded-xl px-3 py-2 text-body", t.speaker === "caller" ? "bg-muted" : "ml-auto bg-primary text-primary-foreground")} data-role={t.speaker}>
            <span className="mb-0.5 block text-label font-semibold uppercase tracking-wide opacity-75">{t.speaker === "caller" ? "Caller" : "Voice Concierge"} · {new Date(t.at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}</span>
            {t.text}
          </div>
        ))}
        {busy && <div className="ml-auto w-16 rounded-xl bg-primary/80 px-3 py-2 text-primary-foreground"><Loader2 className="size-4 animate-spin" aria-label="Concierge is replying" /></div>}
      </div>
      {call?.test_code && active && (
        <p className="mx-4 mb-2 flex items-center gap-2 rounded-md border border-warning/30 bg-warning-soft px-3 py-1.5 text-table text-warning-foreground" data-testid="test-code">
          <ShieldQuestion className="size-4" aria-hidden />Synthetic test: the code sent to the patient portal is <span className="font-mono font-semibold">{call.test_code}</span>
        </p>
      )}
      {active && call.channel === "browser_voice" && (
        <div className="mx-4 mb-2 flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-table" data-testid="voice-controls">
          {voice.state === "live" ? <>
            <Badge variant="success"><CircleDot className="size-3" />Voice connected</Badge>
            <Button size="xs" variant="outline" onClick={voice.toggleMute}>{voice.muted ? <><Mic />Unmute</> : <><MicOff />Mute</>}</Button>
            <Button size="xs" variant="ghost" onClick={voice.stop}>Disconnect voice</Button>
          </> : <Button size="xs" onClick={voice.start} loading={voice.state === "connecting"}><Mic />Connect microphone</Button>}
          <span className="text-muted-foreground">Browser voice test — not a phone call.</span>
          {voice.error && <span className="w-full text-destructive" role="alert">{voice.error}</span>}
          <audio ref={voice.audio} autoPlay className="hidden" />
        </div>
      )}
      {active && (
        <div className="space-y-2 border-t p-3">
          <div className="flex flex-wrap gap-1.5" aria-label="Synthetic caller phrases">
            {PHRASES.map((p) => <button key={p} type="button" onClick={() => send(p)} disabled={busy} className="rounded-full border bg-card px-2.5 py-0.5 text-label hover:border-primary hover:text-primary disabled:opacity-50">{p}</button>)}
          </div>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void send(text); }}>
            <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type what the caller says…" aria-label="Caller says" maxLength={500} autoFocus />
            <Button type="submit" loading={busy} disabled={!text.trim()} aria-label="Send" data-testid="caller-send"><Send /></Button>
          </form>
        </div>
      )}
      {call && !active && <p className="border-t bg-muted/30 px-4 py-2.5 text-table text-muted-foreground" data-testid="call-ended">Call {call.status} · {call.summary}</p>}
    </Card>
  );
}

// ---------------------------------------------------------------------------------------------- middle: workflow actions
const STEP_ICON = { done: CheckCircle2, in_progress: Loader2, failed: XCircle, not_started: Circle } as const;
const STEP_BADGE = { done: ["success", "Completed"], in_progress: ["info", "In progress"], failed: ["danger", "Failed"], not_started: ["neutral", "Not started"] } as const;
const EV_BADGE: Record<Ev["status"], React.ComponentProps<typeof Badge>["variant"]> = { ok: "success", refused: "warning", failed: "danger", pending: "info", info: "neutral" };

function WorkflowPanel({ call, canRun, onUpdate }: { call: Detail | null; canRun: boolean; onUpdate: (d: Detail) => void }) {
  const [dialog, setDialog] = React.useState<"callback" | "handoff" | null>(null);
  const events = (call?.events ?? []).filter((e) => !["disclosure", "end_call"].includes(e.tool)).slice(-8).reverse();
  return (
    <Card className="flex flex-col overflow-hidden" data-testid="workflow-actions">
      <div className="border-b px-4 py-3">
        <h2 className="flex items-center gap-2 text-section font-semibold text-heading"><Workflow className="size-4 text-primary" aria-hidden />Workflow actions</h2>
        <p className="text-table text-muted-foreground">What the concierge did on this call, with the system's results</p>
      </div>
      {!call ? <p className="p-4 text-table text-muted-foreground">Steps, tool results and staff actions appear here once a call is open.</p> : <>
        <ol className="divide-y" data-testid="workflow-steps">
          {call.workflow.map((s) => {
            const Icon = STEP_ICON[s.status];
            const [variant, text] = STEP_BADGE[s.status];
            return (
              <li key={s.key} className="flex items-start gap-3 px-4 py-2.5" data-step={s.key} data-status={s.status}>
                <Icon className={cn("mt-0.5 size-4 shrink-0", s.status === "done" && "text-success", s.status === "failed" && "text-destructive", s.status === "in_progress" && "animate-spin text-primary", s.status === "not_started" && "text-muted-foreground")} aria-hidden />
                <span className="min-w-0 flex-1"><span className="block text-table font-medium">{s.label}</span><span className="block text-label text-muted-foreground">{s.detail}</span></span>
                <Badge variant={variant}>{text}</Badge>
              </li>
            );
          })}
        </ol>
        {call.pending && (
          <div className="mx-4 my-3 rounded-lg border border-ai/25 bg-ai-soft/50 p-3 text-table" data-testid="pending-action">
            <p className="font-medium text-ai">Waiting for the caller's confirmation</p>
            <p className="text-foreground">{call.pending}</p>
            <p className="text-label text-muted-foreground">Nothing changes until the caller says yes; availability and conflicts are re-checked first.</p>
          </div>
        )}
        {!!call.offers.length && !call.pending && (
          <div className="mx-4 my-3 rounded-lg border bg-muted/30 p-3 text-table" data-testid="current-offers">
            <p className="mb-1 font-medium">Open times offered (from the live schedule)</p>
            <ul className="space-y-0.5">{call.offers.map((x) => <li key={x.ref}><span className="font-mono text-label text-muted-foreground">{x.ref}</span> {x.label}</li>)}</ul>
          </div>
        )}
        <div className="border-t px-4 py-3">
          <p className="mb-1.5 text-label font-semibold uppercase tracking-wide text-muted-foreground">Tool activity</p>
          {!events.length ? <p className="text-table text-muted-foreground">No tools used yet.</p> : (
            <ul className="space-y-1.5" data-testid="tool-activity">{events.map((e, i) => (
              <li key={i} className="flex items-start gap-2 text-table"><Badge variant={EV_BADGE[e.status]} className="mt-0.5 shrink-0">{e.status === "ok" ? "Done" : titleCase(e.status)}</Badge>
                <span className="min-w-0"><span className="block">{e.label}</span>{e.detail && <span className="block truncate text-label text-muted-foreground" title={e.detail}>{e.detail}</span>}</span></li>
            ))}</ul>
          )}
        </div>
        {canRun && (
          <div className="mt-auto border-t px-4 py-3">
            <p className="mb-2 text-label font-semibold uppercase tracking-wide text-muted-foreground">Take action</p>
            <div className="grid grid-cols-2 gap-2">
              <button type="button" onClick={() => setDialog("callback")} className="flex items-start gap-2 rounded-lg border bg-card p-2.5 text-left hover:border-primary/50" data-testid="action-callback">
                <CalendarClock className="mt-0.5 size-4 text-primary" aria-hidden /><span><span className="block text-table font-medium">Create callback task</span><span className="block text-label text-muted-foreground">Follow up with the caller later</span></span>
              </button>
              <button type="button" onClick={() => setDialog("handoff")} className="flex items-start gap-2 rounded-lg border bg-card p-2.5 text-left hover:border-primary/50" data-testid="action-handoff">
                <Users className="mt-0.5 size-4 text-primary" aria-hidden /><span><span className="block text-table font-medium">Hand off to staff</span><span className="block text-label text-muted-foreground">Front desk task with call summary</span></span>
              </button>
            </div>
          </div>
        )}
      </>}
      <StaffActionDialog call={call} kind={dialog} onClose={() => setDialog(null)} onDone={onUpdate} />
    </Card>
  );
}

function StaffActionDialog({ call, kind, onClose, onDone }: { call: Detail | null; kind: "callback" | "handoff" | null; onClose: () => void; onDone: (d: Detail) => void }) {
  const [note, setNote] = React.useState("");
  const [category, setCategory] = React.useState("scheduling");
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { setNote(""); setCategory("scheduling"); }, [kind]);
  const submit = async () => {
    if (!call || !kind) return;
    setBusy(true);
    try { onDone(await post<Detail>(`/receptionist/calls/${call.id}/staff-action`, { action: kind, note, category })); onClose(); }
    catch (e) { toastError(e); } finally { setBusy(false); }
  };
  return (
    <Dialog open={!!kind} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{kind === "callback" ? "Create callback task" : "Hand off to staff"}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          {kind === "callback" && <Field label="Team"><NativeSelect value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="scheduling">Scheduling (front desk)</option><option value="records">Records (front desk)</option><option value="billing">Billing</option>
            <option value="clinical_question">Clinical question (nursing)</option><option value="other">Other (front desk)</option></NativeSelect></Field>}
          <Field label="Reason"><Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={200} placeholder="Short administrative reason — no medical details" /></Field>
          {kind === "handoff" && <p className="text-table text-muted-foreground">Creates a high-priority front-desk task with the call summary. No live call transfer is made.</p>}
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={submit} loading={busy} disabled={note.trim().length < 2}>Create task</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------------------------- right: outcome + history
function OutcomePanel({ call }: { call: Detail | null }) {
  const code = call?.outcome_code ?? null;
  return (
    <Card className="overflow-hidden" data-testid="call-outcome">
      <div className="border-b px-4 py-3">
        <h2 className="flex items-center gap-2 text-section font-semibold text-heading"><CheckCircle2 className="size-4 text-primary" aria-hidden />Call outcome</h2>
        <p className="text-table text-muted-foreground">Set only by actions the system completed</p>
      </div>
      <div className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-4 xl:grid-cols-2 2xl:grid-cols-4" role="list">
        {OUTCOMES.map((x) => {
          const on = !!code && x.code.includes(code);
          return (
            <div key={x.label} role="listitem" aria-current={on || undefined} className={cn("flex flex-col items-center gap-1 rounded-lg border p-2.5 text-center text-label", on ? "border-primary bg-accent font-semibold text-accent-foreground" : "text-muted-foreground")} data-outcome={x.code[0]} data-active={on}>
              <x.icon className="size-4" aria-hidden />{x.label}
            </div>
          );
        })}
      </div>
      {!call ? <p className="px-4 pb-4 text-table text-muted-foreground">Open a call to see its result.</p> : (
        <div className="space-y-2 px-4 pb-4 text-table">
          <p className="flex flex-wrap items-center gap-2"><span className="font-medium">{call.outcome ?? (call.status === "active" ? "In progress — nothing completed yet" : "No action taken")}</span>
            {code && <Badge variant={OUTCOME_BADGE[code] ?? "neutral"}>{titleCase(code)}</Badge>}</p>
          {call.patient && <p>Patient: <Link to={`/patients/${call.patient.id}`} className="font-medium text-primary hover:underline">{call.patient.name} (MRN {call.patient.mrn})</Link></p>}
          {call.facility && <p className="text-muted-foreground">Facility: {call.facility.name}</p>}
          {!!call.records.length && (
            <ul className="space-y-1" data-testid="call-records">{call.records.map((r) => (
              <li key={r.id + r.ref}><Link to={r.link} className="group flex items-center gap-2 rounded-md border px-2.5 py-1.5 hover:border-primary/50">
                {r.type === "appointment" ? <CalendarCheck2 className="size-4 text-success" aria-hidden /> : <PhoneCall className="size-4 text-primary" aria-hidden />}
                <span className="min-w-0 flex-1 truncate">{r.label}</span><span className="font-mono text-label text-muted-foreground">{r.ref}</span>
                <ArrowRight className="size-3.5 text-muted-foreground group-hover:text-primary" aria-hidden /></Link></li>
            ))}</ul>
          )}
        </div>
      )}
    </Card>
  );
}

function CallLog({ rows, loading, selected, onOpen }: { rows?: Summary[]; loading: boolean; selected: string | null; onOpen: (id: string) => void }) {
  return (
    <Card className="overflow-hidden" data-testid="call-log">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 className="flex items-center gap-2 text-section font-semibold text-heading"><PhoneCall className="size-4 text-primary" aria-hidden />Recent call log</h2>
        <span className="text-label text-muted-foreground">{rows?.length ?? 0} calls</span>
      </div>
      {loading ? <LoadingRows /> : !rows?.length ? <p className="p-4 text-table text-muted-foreground">No calls yet.</p> : (
        <div className="max-h-[420px] overflow-y-auto">
          <table className="w-full text-table">
            <thead className="sticky top-0 bg-card text-left text-label text-muted-foreground"><tr><th className="px-4 py-2 font-medium">Time</th><th className="px-2 py-2 font-medium">Caller</th><th className="hidden px-2 py-2 font-medium sm:table-cell">Intent</th><th className="px-4 py-2 font-medium">Outcome</th></tr></thead>
            <tbody className="divide-y">{rows.map((c) => (
              <tr key={c.id} onClick={() => onOpen(c.id)} onKeyDown={(e) => e.key === "Enter" && onOpen(c.id)} tabIndex={0} className={cn("cursor-pointer hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:outline-none", selected === c.id && "bg-accent/60")} data-call={c.id}>
                <td className="whitespace-nowrap px-4 py-2 text-muted-foreground">{fmtTime(c.created_at)}</td>
                <td className="max-w-[9rem] truncate px-2 py-2">{c.caller}{c.mode === "test" && <span className="ml-1 text-label text-muted-foreground">(test)</span>}</td>
                <td className="hidden px-2 py-2 sm:table-cell">{c.intent ? titleCase(c.intent.replace("_", " ")) : "—"}</td>
                <td className="px-4 py-2">{c.status === "active" ? <Badge variant="info">In call</Badge> : <Badge variant={OUTCOME_BADGE[c.outcome_code ?? ""] ?? "neutral"}>{titleCase(c.outcome_code ?? "none")}</Badge>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
