import { useQuery } from "@tanstack/react-query";
import { Mic, PhoneOff } from "lucide-react";
import * as React from "react";
import { SimulatedBadge, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { get, post } from "@/lib/api";

type Status = { mode: "openai" | "simulated"; model: string | null; reason: string | null };
type Session = { mode: "openai"; value: string; expires_at: number | null; model: string; calls_url: string } | { mode: "simulated"; reason: string; model: string | null };
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

  const stop = React.useCallback(() => {
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
      events.onmessage = (m) => {
        try {
          const ev = JSON.parse(m.data) as { type: string; transcript?: string };
          if (ev.transcript && ev.type.endsWith(".done")) {
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
          ? <Button size="sm" variant="destructive" onClick={stop}><PhoneOff />End</Button>
          : <Button size="sm" onClick={start} loading={state === "connecting"} disabled={!st || st.mode !== "openai"}><Mic />Start voice session</Button>}
      </CardHeader>
      <CardContent className="space-y-2 text-[13px]">
        {st?.mode !== "openai" && <p className="text-muted-foreground">{st?.reason ?? "Checking configuration…"} Until then, use the typed call simulator below.</p>}
        {st?.mode === "openai" && <p className="text-muted-foreground">Uses synthetic scenarios only. Administrative help — the assistant gives no medical advice. Your microphone audio goes to OpenAI for this session.</p>}
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
