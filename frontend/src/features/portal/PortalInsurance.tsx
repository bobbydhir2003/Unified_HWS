import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Camera, CircleAlert, ShieldCheck, Sparkles } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { ErrorState, LoadingRows, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api, get } from "@/lib/api";
import { fmtDate } from "@/lib/format";

type PortalIns = {
  insurances: { id: string; payer_name: string; plan_name: string | null; member_id: string; priority: string; termination_date: string | null }[];
  requests: { id: string; reason: string; status: string; review_note: string | null; created_at: string }[];
  sample_cards_available: boolean;
};

export function usePortalInsurance() {
  return useQuery({ queryKey: ["portal", "insurance"], queryFn: () => get<PortalIns>("/portal/insurance") });
}

export function PortalInsurance() {
  const qc = useQueryClient();
  const q = usePortalInsurance();
  const [file, setFile] = React.useState<File | null>(null);
  const [f, setF] = React.useState({ payer_name: "", member_id: "", group_number: "" });
  const [busy, setBusy] = React.useState(false);
  const submit = async (sample = false) => {
    setBusy(true);
    try {
      const fd = new FormData();
      const open = q.data?.requests.find((r) => r.status === "requested");
      if (open) fd.append("request_id", open.id);
      if (sample) fd.append("use_sample_card", "true");
      else if (file) fd.append("file", file);
      Object.entries(f).forEach(([k, v]) => v && fd.append(k, v));
      const res = await api<Response>("/portal/insurance/update", { method: "POST", body: fd, raw: true });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail ?? "Upload failed"); }
      toast.success("Thanks — we'll confirm your insurance and let you know if we need anything else.");
      setFile(null); setF({ payer_name: "", member_id: "", group_number: "" });
      qc.invalidateQueries({ queryKey: ["portal"] });
    } catch (e) { toastError(e); } finally { setBusy(false); }
  };
  if (q.isLoading) return <LoadingRows />;
  if (q.isError || !q.data) return <ErrorState error={q.error} retry={q.refetch} />;
  const req = q.data.requests[0];
  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-semibold">Insurance</h1><p className="text-body text-muted-foreground">Keep your coverage up to date so your visits aren't delayed.</p></div>
      {req && (
        <Card className={req.status === "requested" ? "border-warning/50 bg-warning-soft/40" : "border-primary/30 bg-accent/40"}>
          <CardContent className="flex gap-3 p-4">
            {req.status === "requested" ? <CircleAlert className="mt-0.5 size-5 shrink-0 text-warning" /> : <ShieldCheck className="mt-0.5 size-5 shrink-0 text-primary" />}
            <div className="text-body">
              <p className="font-medium">{req.status === "requested" ? "Action needed: please confirm your insurance" : "Thanks — your care team is reviewing your card"}</p>
              <p className="text-muted-foreground">{req.reason}</p>
              {req.review_note && <p className="mt-1 text-destructive">Note from our team: {req.review_note}</p>}
            </div>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader><CardTitle>Coverage on file</CardTitle></CardHeader>
        <CardContent>{!q.data.insurances.length ? <p className="text-body text-muted-foreground">No insurance on file.</p> : (
          <ul className="divide-y">{q.data.insurances.map((i) => (
            <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-body">
              <div><p className="font-medium">{i.payer_name}{i.plan_name ? ` · ${i.plan_name}` : ""}</p><p className="text-xs text-muted-foreground">Member ID {i.member_id}{i.termination_date ? ` · plan end date on file ${fmtDate(i.termination_date)}` : ""}</p></div>
              <Badge variant="outline">{i.priority}</Badge>
            </li>))}</ul>
        )}</CardContent>
      </Card>
      {req?.status !== "submitted" && (
        <Card>
          <CardHeader><CardTitle>Update my insurance</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-6 text-center hover:bg-muted/40">
              <Camera className="size-6 text-primary" />
              <span className="text-body font-medium">{file ? file.name : "Upload a photo or PDF of your insurance card"}</span>
              <span className="text-xs text-muted-foreground">Front and back if possible · JPG, PNG or PDF</span>
              <input type="file" accept="image/png,image/jpeg,image/webp,application/pdf" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </label>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Insurance company"><Input value={f.payer_name} onChange={(e) => setF({ ...f, payer_name: e.target.value })} /></Field>
              <Field label="Member ID"><Input value={f.member_id} onChange={(e) => setF({ ...f, member_id: e.target.value })} /></Field>
              <Field label="Group number"><Input value={f.group_number} onChange={(e) => setF({ ...f, group_number: e.target.value })} /></Field>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button loading={busy} disabled={!file && !f.member_id} onClick={() => submit(false)}><BadgeCheck />Send to my care team</Button>
              {q.data.sample_cards_available && <Button variant="outline" loading={busy} onClick={() => submit(true)}><Sparkles />Use a synthetic demo card</Button>}
            </div>
            <p className="text-xs text-muted-foreground">Our staff confirms every card before it's used. Nothing changes on your record until they do.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
