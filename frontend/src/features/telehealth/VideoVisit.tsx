import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, ExternalLink, Loader2, Mic, MicOff, PhoneOff, ShieldCheck, Stethoscope, Video, VideoOff, Wifi, WifiOff } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ErrorState, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { get, post } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type JoinInfo = {
  session_id: string; role: "patient" | "provider"; status: string; ice_servers: RTCIceServer[]; encounter_id: string | null;
  appointment: { id: string; start_at: string; patient: string; provider: string; reason: string | null; patient_id: string };
};
type Signal = { id: number; kind: "hello" | "offer" | "answer" | "ice" | "hangup"; payload: Record<string, unknown> };
type ConnState = "connecting-media" | "waiting" | "connecting" | "connected" | "reconnecting" | "ended";

/** Minimal WebRTC call over the app's authenticated signaling API. Provider is always the offerer. */
function useVideoCall(info: JoinInfo | undefined) {
  const localRef = React.useRef<HTMLVideoElement>(null);
  const remoteRef = React.useRef<HTMLVideoElement>(null);
  const pcRef = React.useRef<RTCPeerConnection | null>(null);
  const streamRef = React.useRef<MediaStream | null>(null);
  const lastId = React.useRef(0);
  const pendingIce = React.useRef<RTCIceCandidateInit[]>([]);
  const gotOffer = React.useRef(false);
  const nidRef = React.useRef<string>(""); // negotiation id: correlates offer ↔ answer ↔ ICE
  const [state, setState] = React.useState<ConnState>("connecting-media");
  const [mediaError, setMediaError] = React.useState<string | null>(null);
  const [micOn, setMicOn] = React.useState(true);
  const [camOn, setCamOn] = React.useState(true);
  const [remoteVideo, setRemoteVideo] = React.useState(false);

  const send = React.useCallback((kind: Signal["kind"], payload: Record<string, unknown> = {}) =>
    info ? post(`/telehealth/sessions/${info.session_id}/signal`, { kind, payload }).catch(() => {}) : Promise.resolve(), [info]);

  const newPeer = React.useCallback((nid = "") => {
    pcRef.current?.close();
    nidRef.current = nid;
    const pc = new RTCPeerConnection({ iceServers: info?.ice_servers ?? [] });
    streamRef.current?.getTracks().forEach((t) => pc.addTrack(t, streamRef.current!));
    if (!streamRef.current) { pc.addTransceiver("audio", { direction: "recvonly" }); pc.addTransceiver("video", { direction: "recvonly" }); }
    pc.onicecandidate = (e) => e.candidate && send("ice", { ...(e.candidate.toJSON() as Record<string, unknown>), nid });
    pc.ontrack = (e) => {
      if (remoteRef.current && e.streams[0]) { remoteRef.current.srcObject = e.streams[0]; setRemoteVideo(true); }
    };
    pc.onconnectionstatechange = () => {
      const s = pc.connectionState;
      if (s === "connected") setState("connected");
      else if (s === "connecting" || s === "new") setState("connecting");
      else if (s === "disconnected") setState("reconnecting");
      else if (s === "failed") setState("waiting");
    };
    pendingIce.current = [];
    pcRef.current = pc;
    return pc;
  }, [info, send]);

  // Acquire media, then announce presence.
  React.useEffect(() => {
    if (!info) return;
    let cancelled = false;
    (async () => {
      try {
        streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true, video: { width: 1280, height: 720 } });
      } catch {
        try {
          streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
          setMediaError("Camera unavailable — joining with audio only.");
          setCamOn(false);
        } catch {
          setMediaError("Camera and microphone are blocked or missing. You can still see and hear the other person; allow access in your browser to share yours.");
          setMicOn(false); setCamOn(false);
        }
      }
      if (cancelled) return;
      if (localRef.current && streamRef.current) localRef.current.srcObject = streamRef.current;
      setState("waiting");
      newPeer();
      await send("hello");
    })();
    return () => { cancelled = true; };
  }, [info, newPeer, send]);

  // Poll signals.
  React.useEffect(() => {
    if (!info || state === "connecting-media" || state === "ended") return;
    let stop = false;
    const tick = async () => {
      try {
        const r = await get<{ status: string; signals: Signal[] }>(`/telehealth/sessions/${info.session_id}/signals`, { after: lastId.current });
        if (r.status === "ended" && info.role === "patient") { setState("ended"); return; }
        // Coalesce: only the latest hello (provider) / latest offer and the ICE after it (patient) matter in a batch.
        let batch = r.signals;
        if (info.role === "provider") {
          const lastHello = batch.map((x) => x.kind).lastIndexOf("hello");
          batch = batch.filter((x, i) => x.kind !== "hello" || i === lastHello);
        } else {
          const lastOffer = batch.map((x) => x.kind).lastIndexOf("offer");
          if (lastOffer > 0) batch = batch.filter((x, i) => i >= lastOffer || (x.kind !== "offer" && x.kind !== "ice"));
        }
        if (r.signals.length) lastId.current = Math.max(lastId.current, ...r.signals.map((x) => x.id));
        for (const s of batch) {
          try {
            let pc = pcRef.current!;
            if (s.kind === "hello") {
              if (info.role === "provider") {
                pc = newPeer(crypto.randomUUID());
                const offer = await pc.createOffer();
                await pc.setLocalDescription(offer);
                await send("offer", { sdp: offer.sdp, type: offer.type, nid: nidRef.current });
                setState("connecting");
              } else if (!gotOffer.current) await send("hello"); // provider joined after us
            } else if (s.kind === "offer" && info.role === "patient") {
              gotOffer.current = true;
              pc = newPeer(String(s.payload.nid ?? ""));
              await pc.setRemoteDescription({ type: "offer", sdp: String(s.payload.sdp) });
              for (const c of pendingIce.current) await pc.addIceCandidate(c).catch(() => {});
              pendingIce.current = [];
              const answer = await pc.createAnswer();
              await pc.setLocalDescription(answer);
              await send("answer", { sdp: answer.sdp, type: answer.type, nid: nidRef.current });
              setState("connecting");
            } else if (s.kind === "answer" && info.role === "provider") {
              if (s.payload.nid !== nidRef.current || pc.signalingState !== "have-local-offer") continue; // answer to a superseded offer
              await pc.setRemoteDescription({ type: "answer", sdp: String(s.payload.sdp) });
              for (const c of pendingIce.current) await pc.addIceCandidate(c).catch(() => {});
              pendingIce.current = [];
            } else if (s.kind === "ice") {
              const { nid, ...cand } = s.payload as RTCIceCandidateInit & { nid?: string };
              if (nid !== nidRef.current) continue; // candidate from a superseded negotiation
              if (pc.remoteDescription) await pc.addIceCandidate(cand).catch(() => {});
              else pendingIce.current.push(cand);
            } else if (s.kind === "hangup") {
              gotOffer.current = false;
              setRemoteVideo(false);
              if (remoteRef.current) remoteRef.current.srcObject = null;
              newPeer();
              setState("waiting");
            }
          } catch (err) {
            console.warn("signal handling failed", s.kind, err); // isolate failures to one signal
          }
        }
      } catch { /* transient network error: keep polling */ }
      if (!stop) setTimeout(tick, 900);
    };
    tick();
    return () => { stop = true; };
  }, [info, state === "connecting-media" || state === "ended", newPeer, send]); // eslint-disable-line react-hooks/exhaustive-deps

  // Cleanup media on unmount.
  React.useEffect(() => () => { pcRef.current?.close(); streamRef.current?.getTracks().forEach((t) => t.stop()); }, []);

  const toggleMic = () => { streamRef.current?.getAudioTracks().forEach((t) => (t.enabled = !micOn)); setMicOn(!micOn); };
  const toggleCam = () => { streamRef.current?.getVideoTracks().forEach((t) => (t.enabled = !camOn)); setCamOn(!camOn); };
  const hasAudio = !!streamRef.current?.getAudioTracks().length;
  const hasVideo = !!streamRef.current?.getVideoTracks().length;
  const end = () => { pcRef.current?.close(); streamRef.current?.getTracks().forEach((t) => t.stop()); setState("ended"); };
  return { localRef, remoteRef, state, mediaError, micOn, camOn, toggleMic, toggleCam, hasAudio, hasVideo, remoteVideo, end };
}

const STATE_LABEL: Record<ConnState, [string, "neutral" | "warning" | "success" | "danger" | "info"]> = {
  "connecting-media": ["Starting camera…", "neutral"], waiting: ["Waiting for the other person", "warning"], connecting: ["Connecting…", "info"],
  connected: ["Connected", "success"], reconnecting: ["Reconnecting…", "warning"], ended: ["Visit ended", "neutral"],
};

export function VideoVisit({ portal = false }: { portal?: boolean }) {
  const { appointmentId = "" } = useParams();
  const navigate = useNavigate();
  const join = useQuery({ queryKey: ["tele-join", appointmentId], queryFn: () => post<JoinInfo>(`/telehealth/appointments/${appointmentId}/join`), retry: false, staleTime: Infinity, refetchOnWindowFocus: false });
  const call = useVideoCall(join.data);
  const leave = useMutation({
    mutationFn: (endForAll: boolean) => post(`/telehealth/sessions/${join.data!.session_id}/leave${endForAll ? "?end_for_all=true" : ""}`),
    onSuccess: () => { call.end(); toast.success("You left the video visit"); },
    onError: (e) => toastError(e),
  });
  const startNotes = useMutation({
    mutationFn: () => post<{ id: string }>("/encounters", { patient_id: join.data!.appointment.patient_id, appointment_id: appointmentId }),
    onSuccess: (e) => window.open(`/encounters/${e.id}`, "_blank", "noopener"),
    onError: (e) => toastError(e),
  });
  if (join.error) return <ErrorState error={join.error} className="min-h-[60vh]" />;
  if (!join.data) return <div className="grid min-h-[60vh] place-items-center"><Loader2 className="size-6 animate-spin text-primary" /></div>;
  const info = join.data;
  const [label, tone] = STATE_LABEL[call.state];
  const other = info.role === "patient" ? info.appointment.provider : info.appointment.patient;
  if (call.state === "ended") {
    return (
      <div className="mx-auto mt-16 max-w-md space-y-3 text-center">
        <p className="text-lg font-semibold">The video visit has ended</p>
        <p className="text-[13.5px] text-muted-foreground">{portal ? "Your visit summary will appear in your portal after your clinician signs the note." : "Remember to complete and sign the visit note."}</p>
        <Button onClick={() => navigate(portal ? "/portal" : info.encounter_id ? `/encounters/${info.encounter_id}` : "/schedule")}>{portal ? "Back to portal" : info.encounter_id ? "Open visit notes" : "Back to schedule"}</Button>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-lg font-semibold tracking-tight">Video visit with {other}</h1>
        <Badge variant={tone}>{call.state === "connected" ? <Wifi /> : call.state === "waiting" ? <WifiOff /> : <Loader2 className="animate-spin" />}{label}</Badge>
        <span className="text-[13px] text-muted-foreground">Scheduled {fmtTime(info.appointment.start_at)}{info.appointment.reason ? ` · ${info.appointment.reason}` : ""}</span>
        <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground"><ShieldCheck className="size-3.5" />Peer-to-peer encrypted (WebRTC) · not recorded</span>
      </div>
      {call.mediaError && <div role="alert" className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning-soft px-3 py-2 text-[13px]"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />{call.mediaError}</div>}
      <div className={cn("grid gap-3", !portal && "xl:grid-cols-[1fr_300px]")}>
        <div className="relative aspect-video overflow-hidden rounded-xl bg-slate-950">
          <video ref={call.remoteRef} autoPlay playsInline className={cn("size-full object-cover", !call.remoteVideo && "hidden")} aria-label={`${other}'s video`} />
          {!call.remoteVideo && (
            <div className="absolute inset-0 grid place-items-center text-center text-slate-300">
              <div>
                <Loader2 className="mx-auto mb-3 size-7 animate-spin opacity-70" />
                <p className="text-[15px] font-medium">{info.role === "patient" ? "You're in the virtual waiting room" : `Waiting for ${other} to join`}</p>
                <p className="mt-1 text-[13px] opacity-70">{info.role === "patient" ? "Your clinician will connect shortly. Keep this page open." : "The patient has been notified when they joined; they'll appear here."}</p>
              </div>
            </div>
          )}
          <video ref={call.localRef} autoPlay playsInline muted className={cn("absolute bottom-3 right-3 aspect-video w-40 rounded-lg border-2 border-white/20 bg-slate-800 object-cover shadow-xl sm:w-56", !call.camOn && "opacity-30")} aria-label="Your video" />
          <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 gap-2 rounded-full bg-slate-900/80 p-1.5 backdrop-blur">
            <Button size="icon" variant="ghost" className="rounded-full text-white hover:bg-white/15" onClick={call.toggleMic} disabled={!call.hasAudio} aria-label={call.micOn ? "Mute microphone" : "Unmute microphone"} aria-pressed={!call.micOn}>
              {call.micOn ? <Mic /> : <MicOff className="text-destructive" />}
            </Button>
            <Button size="icon" variant="ghost" className="rounded-full text-white hover:bg-white/15" onClick={call.toggleCam} disabled={!call.hasVideo} aria-label={call.camOn ? "Turn camera off" : "Turn camera on"} aria-pressed={!call.camOn}>
              {call.camOn ? <Video /> : <VideoOff className="text-destructive" />}
            </Button>
            <Button size="icon" variant="destructive" className="rounded-full" onClick={() => leave.mutate(false)} aria-label="Leave visit"><PhoneOff /></Button>
          </div>
        </div>
        {!portal && (
          <aside className="space-y-3 rounded-xl border bg-card p-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Patient</p>
              <Link to={`/patients/${info.appointment.patient_id}`} target="_blank" className="font-medium text-primary hover:underline">{info.appointment.patient} <ExternalLink className="inline size-3" /></Link>
            </div>
            <Button className="w-full" variant="soft" loading={startNotes.isPending} onClick={() => info.encounter_id ? window.open(`/encounters/${info.encounter_id}`, "_blank", "noopener") : startNotes.mutate()}>
              <Stethoscope />{info.encounter_id ? "Open visit notes" : "Start visit notes"}
            </Button>
            <Button className="w-full" variant="outline" onClick={() => leave.mutate(true)}><PhoneOff />End visit for everyone</Button>
            <p className="text-[11.5px] text-muted-foreground">Development video uses direct browser-to-browser WebRTC with STUN only. Production requires a BAA-covered video vendor with TURN relays.</p>
          </aside>
        )}
      </div>
    </div>
  );
}
