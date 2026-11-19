import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleDashed, Clock, FileUp, Hospital } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { EmptyState, LoadingRows, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/misc";
import { api, get, put } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type Ready = { appointment_id: string; start_at: string; clinic: string; mode: string; provider: string | null; ready: boolean;
  items: { key: string; label: string; done: boolean; detail?: string; link?: string | null; pending_staff?: boolean; optional?: boolean }[] };

/** "Before your visit" checklist — shown on the portal home. */
export function ReadinessCard() {
  const q = useQuery({ queryKey: ["portal", "readiness"], queryFn: () => get<Ready[]>("/portal/readiness") });
  if (!q.data?.length) return null;
  return (
    <Card>
      <CardHeader><CardTitle>Before your next visit{q.data.length > 1 ? "s" : ""}</CardTitle></CardHeader>
      <CardContent className="space-y-4">{q.data.slice(0, 3).map((a) => (
        <div key={a.appointment_id}>
          <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[13.5px]"><span className="font-medium">{fmtDateTime(a.start_at)}</span><span className="text-muted-foreground">{a.provider} · {a.mode === "telehealth" ? "Video visit" : a.clinic}</span>
            <Badge variant={a.ready ? "success" : "warning"}>{a.ready ? "You're all set" : "Action needed"}</Badge></div>
          <ul className="space-y-1">{a.items.map((i) => (
            <li key={i.key} className="flex items-center gap-2 text-[13px]">
              {i.done ? <CheckCircle2 className="size-4 text-success" /> : i.pending_staff ? <Clock className="size-4 text-muted-foreground" /> : <CircleDashed className="size-4 text-warning" />}
              <span className={cn(i.done && "text-muted-foreground")}>{i.label}</span>{i.detail && <span className="text-xs text-muted-foreground">— {i.detail}</span>}
              {!i.done && i.link && <Link to={i.link} className="ml-auto text-xs font-medium text-primary hover:underline">Do it now</Link>}
            </li>))}</ul>
        </div>))}</CardContent>
    </Card>
  );
}

type Stay = { id: string; status: string; facility: string | null; reason: string; admitted_at: string | null; discharged_at: string | null; disposition: string | null;
  instructions: string | null; instructions_approved_at: string | null; follow_up_at: string | null };

export function PortalStays() {
  const q = useQuery({ queryKey: ["portal", "stays"], queryFn: () => get<Stay[]>("/portal/stays") });
  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-semibold">Hospital stays</h1><p className="text-[13.5px] text-muted-foreground">Your discharge instructions appear here once your care team has approved them.</p></div>
      {q.isLoading ? <LoadingRows /> : !q.data?.length ? <Card><EmptyState icon={Hospital} title="No hospital stays in the past year" /></Card> : q.data.map((s) => (
        <Card key={s.id}>
          <CardHeader className="flex-row flex-wrap items-center justify-between gap-2"><CardTitle>{s.facility ?? "Hospital stay"}</CardTitle>
            <Badge variant={s.status === "discharged" ? "success" : "info"}>{s.status === "discharged" ? `Discharged ${fmtDate(s.discharged_at)}` : "In the hospital"}</Badge></CardHeader>
          <CardContent className="space-y-3 text-[13.5px]">
            <p><span className="text-muted-foreground">Reason:</span> {s.reason}{s.admitted_at ? ` · admitted ${fmtDate(s.admitted_at)}` : ""}</p>
            {s.follow_up_at && <p><span className="text-muted-foreground">Follow-up appointment:</span> {fmtDateTime(s.follow_up_at)}</p>}
            {s.instructions ? <div className="rounded-lg border bg-muted/30 p-3"><p className="mb-1 font-medium">Discharge instructions</p><p className="whitespace-pre-wrap">{s.instructions}</p>
              <p className="mt-2 text-xs text-muted-foreground">Approved by your care team {fmtDate(s.instructions_approved_at)}</p></div>
              : s.status !== "admitted" && <p className="text-muted-foreground">Your discharge instructions will appear here once they're ready.</p>}
          </CardContent>
        </Card>))}
    </div>
  );
}

export function PortalDocuments() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["portal", "documents"], queryFn: () => get<{ id: string; filename: string; status: string; uploaded_at: string; note: string | null }[]>("/portal/documents") });
  const [busy, setBusy] = React.useState(false);
  const upload = async (f: File) => {
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("file", f);
      const r = await api<Response>("/portal/documents", { method: "POST", body: fd, raw: true });
      if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail ?? "Upload failed"); }
      toast.success("Thanks — your care team will review it."); qc.invalidateQueries({ queryKey: ["portal", "documents"] });
    } catch (e) { toastError(e); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-semibold">Documents</h1><p className="text-[13.5px] text-muted-foreground">Share records from other doctors or hospitals. Your care team reviews each one before it's added to your record.</p></div>
      <Card><CardContent className="p-4">
        <label className={cn("flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-6 text-center hover:bg-muted/40", busy && "opacity-60")}>
          <FileUp className="size-6 text-primary" /><span className="text-[13.5px] font-medium">Upload a PDF or photo</span><span className="text-xs text-muted-foreground">Up to the size limit · PDF, JPG, PNG</span>
          <input type="file" className="sr-only" accept="application/pdf,image/png,image/jpeg" disabled={busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        </label>
      </CardContent></Card>
      <Card><CardHeader><CardTitle>Shared with your care team</CardTitle></CardHeader>
        <CardContent>{!q.data?.length ? <p className="text-[13px] text-muted-foreground">Nothing shared yet.</p> : (
          <ul className="divide-y">{q.data.map((d) => <li key={d.id} className="flex items-center justify-between py-2 text-[13.5px]"><span>{d.filename}<span className="ml-2 text-xs text-muted-foreground">{fmtDate(d.uploaded_at)}</span></span><Badge variant="outline">{d.status}</Badge></li>)}</ul>
        )}</CardContent></Card>
    </div>
  );
}

type Pref = { category: string; label: string; email: boolean; sms: boolean; portal: boolean };

export function PortalNotifications() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["portal", "prefs"], queryFn: () => get<Pref[]>("/portal/notification-preferences") });
  const set = async (p: Pref, k: "email" | "sms" | "portal", v: boolean) => {
    try { await put("/portal/notification-preferences", { ...p, [k]: v }); qc.invalidateQueries({ queryKey: ["portal", "prefs"] }); } catch (e) { toastError(e); }
  };
  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-semibold">Notifications</h1><p className="text-[13.5px] text-muted-foreground">Choose how we contact you. Urgent safety messages may still be sent.</p></div>
      <Card>{!q.data ? <LoadingRows /> : (
        <table className="w-full text-[13.5px]"><thead className="text-xs text-muted-foreground"><tr><th className="px-4 py-2 text-left">Topic</th><th>Portal</th><th>Email</th><th>Text</th></tr></thead>
          <tbody>{q.data.map((p) => (
            <tr key={p.category} className="border-t"><td className="px-4 py-2.5">{p.label}</td>
              {(["portal", "email", "sms"] as const).map((k) => <td key={k} className="text-center"><Switch checked={p[k]} onCheckedChange={(v) => set(p, k, v)} aria-label={`${p.label} by ${k}`} /></td>)}</tr>))}</tbody></table>
      )}</Card>
    </div>
  );
}
