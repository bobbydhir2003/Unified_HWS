import { useQuery } from "@tanstack/react-query";
import { Mic, PhoneOff } from "lucide-react";
import * as React from "react";
import { SimulatedBadge, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { get, post } from "@/lib/api";

type Status = { mode: "openai" | "simulated"; model: string | null; reason: string | null };
type Session = { mode: "openai"; value: string; expires_at: number | null; model: string; calls_url: string; max_seconds?: number } | { mode: "simulated"; reason: string; model: string | null };
type Line = { who: "caller" | "assistant" | "system"; text: string };

/** Live voice practice for the front desk (OpenAI Realtime over WebRTC). The browser only ever holds a short-lived
 *  client secret minted by the backend; audio goes straight to OpenAI. Synthetic organizations only unless PHI is allowed. */
export function RealtimeVoicePanel() {
  const status = useQuery({ queryKey: ["ai", "realtime-status"], queryFn: () => get<Status>("/ai/realtime/status") });
  const [state, setState] = React.useState<"idle" | "connecting" | "live">("idle");
  const [lines, setLines] = React.useState<Line[]>([]);
  const pc = React.useRef<RTCPeerConnection | null>(null);
  const mic = React.useRef<MediaStream | null>(null);
  const audio = React.useRef<HTMLAudioElement | null>(null);
  const timer = React.useRef<number | null>(null);
  const [left, setLeft] = React.useState<number | null>(null);

  const stop = React.useCallback(() => {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
    setLeft(null);
    pc.current?.close();
    pc.current = null;
    mic.current?.getTracks().forEach((t) => t.stop());
    mic.current = null;
    setState("idle");
  }, []);
  React.useEffect(() => stop, [stop]);

  const start = async () => {
    setState("connecting");
    setLines([]);
    try {
      const s = await post<Session>("/ai/realtime/session", { purpose: "receptionist_practice" });
      if (s.mode !== "openai") { setLines([{ who: "system", text: s.reason }]); setState("idle"); return; }
      const conn = new RTCPeerConnection();
      pc.current = conn;
      conn.ontrack = (e) => { if (audio.current) audio.current.srcObject = e.streams[0]; };
      mic.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      mic.current.getTracks().forEach((t) => conn.addTrack(t, mic.current!));
      const events = conn.createDataChannel("oai-events");
      // The model may call a server-validated tool; the browser only relays the call and returns the server's answer.
      const runTool = async (name: string, callId: string, rawArgs: string) => {
        let output: unknown;
        try {
          output = await post(`/ai/realtime/tools/${encodeURIComponent(name)}`, JSON.parse(rawArgs || "{}"));
          if (name === "request_staff_callback") setLines((l) => [...l, { who: "system", text: "Callback task created for the front desk (nothing booked)." }]);
        } catch {
          output = { error: "That action isn't available. Offer a staff callback instead." };
        }
        if (events.readyState !== "open") return;
        events.send(JSON.stringify({ type: "conversation.item.create", item: { type: "function_call_output", call_id: callId, output: JSON.stringify(output) } }));
        events.send(JSON.stringify({ type: "response.create" }));
      };
      events.onmessage = (m) => {
        try {
          const ev = JSON.parse(m.data) as { type: string; transcript?: string; item?: { type?: string; name?: string; call_id?: string; arguments?: string } };
          if (ev.type === "response.output_item.done" && ev.item?.type === "function_call" && ev.item.name && ev.item.call_id) {
            void runTool(ev.item.name, ev.item.call_id, ev.item.arguments ?? "{}");
          } else if (ev.transcript && ev.type.endsWith(".done")) {
            setLines((l) => [...l, { who: ev.type.includes("input_audio") ? "caller" : "assistant", text: ev.transcript! }]);
          } else if (ev.type === "error") {
            setLines((l) => [...l, { who: "system", text: "The voice service reported an error." }]);
          }
        } catch { /* ignore non-JSON events */ }
      };
      const offer = await conn.createOffer();
      await conn.setLocalDescription(offer);
      const r = await fetch(s.calls_url, { method: "POST", body: offer.sdp, headers: { Authorization: `Bearer ${s.value}`, "Content-Type": "application/sdp" } });
      if (!r.ok) throw new Error(`Voice service refused the call (${r.status})`);
      await conn.setRemoteDescription({ type: "answer", sdp: await r.text() });
      setState("live");
      const limit = s.max_seconds ?? 300;
      const endAt = Date.now() + limit * 1000;
      setLeft(limit);
      timer.current = window.setInterval(() => {
        const sec = Math.max(0, Math.round((endAt - Date.now()) / 1000));
        setLeft(sec);
        if (sec <= 0) { setLines((l) => [...l, { who: "system", text: "Session time limit reached." }]); stop(); }
      }, 1000);
    } catch (e) {
      stop();
      toastError(e);
    }
  };

  const st = status.data;
  return (
    <Card className="mb-4" data-testid="realtime-voice">
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2">Live voice practice {st?.mode === "openai" ? <Badge variant="ai">{st.model}</Badge> : <SimulatedBadge />}</CardTitle>
        {state === "live"
          ? <span className="flex items-center gap-2">{left != null && <span className="text-label text-muted-foreground tabular-nums" data-testid="voice-time-left">{Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")} left</span>}<Button size="sm" variant="destructive" onClick={stop}><PhoneOff />End</Button></span>
          : <Button size="sm" onClick={start} loading={state === "connecting"} disabled={!st || st.mode !== "openai"}><Mic />Start voice session</Button>}
      </CardHeader>
      <CardContent className="space-y-2 text-table">
        {st?.mode !== "openai" && <p className="text-muted-foreground">{st?.reason ?? "Checking configuration…"} Until then, use the typed call simulator below.</p>}
        {st?.mode === "openai" && <p className="text-muted-foreground">Uses synthetic scenarios only. Administrative help — the assistant gives no medical advice, can't see patient records and can't book or change anything; it can read facility details and create a callback task. Your microphone audio goes to OpenAI for this session.</p>}
        {!!lines.length && (
          <ul className="max-h-48 space-y-1 overflow-auto rounded-md border p-2">
            {lines.map((l, i) => <li key={i}><span className="font-medium">{l.who === "caller" ? "Caller" : l.who === "assistant" ? "Assistant" : "System"}:</span> {l.text}</li>)}
          </ul>
        )}
        <audio ref={audio} autoPlay className="hidden" />
      </CardContent>
    </Card>
  );
}
