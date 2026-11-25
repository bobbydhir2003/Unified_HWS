import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, KeyRound, Lock, PlugZap, Save, ShieldAlert, Trash2, XCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { LoadingRows, PageHeader, SimulatedBadge, toastError, useConfirm } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect } from "@/components/ui/input";
import { api, get, post, put } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import { titleCase } from "@/lib/utils";
import { OwnerAICard } from "./OwnerAICard";

type Settings = {
  provider: string; source: string; key: { configured: boolean; hint: string | null; updated_at: string | null };
  models: Record<"text" | "vision" | "transcription" | "realtime", string | null>; agent_models: Record<string, string>; agents: string[];
  suggested: Record<string, string>; last_test: null | (TestResult & { at: string });
  active_provider: string; phi_allowed: boolean; encryption: string;
};
type TestResult = { ok: boolean; models?: Record<string, boolean>; error?: string; available_count?: number; latency_ms?: number;
  family_problems?: Record<string, string>; capabilities?: Record<string, { ok: boolean; error?: string }> };

const MODEL_FIELDS: [keyof Settings["models"], string, string][] = [
  ["text", "Text model", "Chart assistant, drafting, agents"], ["vision", "Vision model", "Document & insurance-card reading"],
  ["transcription", "Transcription model", "Medical scribe audio"], ["realtime", "Realtime voice model", "HMS Voice Concierge browser voice (WebRTC) — verify with Test connection"],
];

export function AISettingsPage() {
  const qc = useQueryClient();
  const { confirm, dialog } = useConfirm();
  const q = useQuery({ queryKey: ["ai", "settings"], queryFn: () => get<Settings>("/admin/ai-settings") });
  const { me } = useAuth();
  const [f, setF] = React.useState<{ provider: string; models: Record<string, string>; agent_models: Record<string, string> } | null>(null);
  const [key, setKey] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [test, setTest] = React.useState<TestResult | null>(null);
  React.useEffect(() => {
    if (q.data && !f) setF({ provider: q.data.provider === "anthropic" ? "openai" : q.data.provider, models: Object.fromEntries(MODEL_FIELDS.map(([k]) => [k, q.data!.models[k] ?? ""])), agent_models: { ...q.data.agent_models } });
  }, [q.data, f]);
  if (!q.data || !f) return <LoadingRows rows={6} />;
  const s = q.data;
  const save = async () => {
    setBusy(true);
    try {
      await put("/admin/ai-settings", { provider: f.provider, api_key: key || null, text_model: f.models.text || null, vision_model: f.models.vision || null,
        transcription_model: f.models.transcription || null, realtime_model: f.models.realtime || null, agent_models: f.agent_models });
      setKey(""); toast.success("AI settings saved"); qc.invalidateQueries({ queryKey: ["ai"] });
    } catch (e) { toastError(e); } finally { setBusy(false); }
  };
  const runTest = async () => {
    setBusy(true);
    try { const r = await post<TestResult>("/admin/ai-settings/test"); setTest(r); r.ok ? toast.success("Connection OK — configured models are available") : toast.error(r.error ?? "Some models are not available to this account"); qc.invalidateQueries({ queryKey: ["ai", "settings"] }); }
    catch (e) { toastError(e); } finally { setBusy(false); }
  };
  const shown = test ?? s.last_test;
  return (
    <>
      <PageHeader title="AI settings" description="Platform AI provider for every organization. The API key is encrypted on the server and can never be viewed again — only replaced or removed."
        actions={s.active_provider === "openai" ? <Badge variant="ai">Live: OpenAI</Badge> : <SimulatedBadge label="Rule-based simulation active" />} />
      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><KeyRound className="size-4" />Provider & API key</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <Field label="Provider"><NativeSelect value={f.provider} onChange={(e) => setF({ ...f, provider: e.target.value })}><option value="openai">OpenAI</option><option value="simulated">Rule-based simulation (no external AI)</option></NativeSelect></Field>
              <div className="rounded-lg border bg-muted/30 p-3 text-table">
                {s.key.configured ? <p className="flex items-center gap-2"><Lock className="size-4 text-success" />Key stored ({s.key.hint}){s.key.updated_at ? ` · updated ${fmtDateTime(s.key.updated_at)}` : ""}{s.source === "environment" ? " · from server environment" : ""}</p>
                  : <p className="flex items-center gap-2 text-muted-foreground"><Lock className="size-4" />No key stored</p>}
              </div>
              <Field label={s.key.configured ? "Replace API key" : "API key"} hint="Sent once over HTTPS, encrypted at rest, never shown again or stored in the browser.">
                <Input type="password" autoComplete="off" spellCheck={false} value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-…" />
              </Field>
              {s.key.configured && s.source === "ui" && <Button variant="outline" size="sm" onClick={async () => {
                if (!(await confirm({ title: "Remove the stored API key?", description: "AI features fall back to the rule-based simulation.", confirmLabel: "Remove key", destructive: true }))) return;
                try { await api("/admin/ai-settings/key", { method: "DELETE" }); toast.success("Key removed"); qc.invalidateQueries({ queryKey: ["ai"] }); } catch (e) { toastError(e); }
              }}><Trash2 />Remove key</Button>}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Models</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-muted-foreground">Suggestions are starting points, not guarantees: <strong>Test connection</strong> checks each id against the models your OpenAI account can use.</p>
              <div className="grid gap-3 sm:grid-cols-2">{MODEL_FIELDS.map(([k, l, h]) => (
                <Field key={k} label={l} hint={h}><div className="flex gap-2"><Input value={f.models[k]} onChange={(e) => setF({ ...f, models: { ...f.models, [k]: e.target.value } })} placeholder={s.suggested[k]} />
                  {!f.models[k] && <Button size="sm" variant="ghost" onClick={() => setF({ ...f, models: { ...f.models, [k]: s.suggested[k] } })}>Use</Button>}</div></Field>))}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Per-agent models</CardTitle></CardHeader>
            <CardContent>
              <p className="mb-3 text-xs text-muted-foreground">Leave blank to use the text model.</p>
              <div className="grid gap-3 sm:grid-cols-2">{s.agents.map((a) => (
                <Field key={a} label={titleCase(a.replace(/_/g, " "))}><Input value={f.agent_models[a] ?? ""} placeholder={f.models.text || "text model"} onChange={(e) => setF({ ...f, agent_models: { ...f.agent_models, [a]: e.target.value } })} /></Field>))}</div>
            </CardContent>
          </Card>
          <div className="flex gap-2"><Button loading={busy} onClick={save}><Save />Save settings</Button><Button variant="outline" loading={busy} onClick={runTest}><PlugZap />Test connection</Button></div>
        </div>
        <div className="space-y-4">
          {me?.user.is_superadmin && <OwnerAICard />}
          <Card>
            <CardHeader><CardTitle>Connection test</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-table">{!shown ? <p className="text-muted-foreground">Not tested yet. Live validation is pending until a key is saved and tested.</p> : (
              <>
                <p className="flex items-center gap-2 font-medium">{shown.ok ? <CheckCircle2 className="size-4 text-success" /> : <XCircle className="size-4 text-destructive" />}{shown.ok ? "Connected" : "Not connected"}{"at" in shown && shown.at ? <span className="font-normal text-muted-foreground">· {fmtDateTime(shown.at as string)}</span> : null}</p>
                {shown.error && <p className="text-destructive">{shown.error}</p>}
                {shown.family_problems && Object.values(shown.family_problems).map((p) => <p key={p} className="text-destructive">{p}</p>)}
                {shown.capabilities && <ul className="space-y-1" data-testid="ai-capabilities">{Object.entries(shown.capabilities).map(([k, c]) => <li key={k} className="flex items-center gap-2">{c.ok ? <CheckCircle2 className="size-3.5 text-success" /> : <XCircle className="size-3.5 text-destructive" />}{titleCase(k)}: {c.ok ? "real call succeeded" : c.error}</li>)}</ul>}
                {shown.models && <ul className="space-y-1">{Object.entries(shown.models).map(([k, ok]) => <li key={k} className="flex items-center gap-2">{ok ? <CheckCircle2 className="size-3.5 text-success" /> : <XCircle className="size-3.5 text-destructive" />}{titleCase(k.replace("agent:", "agent · ").replace(/_/g, " "))} {ok ? "available" : "not available to this account"}</li>)}</ul>}
              </>
            )}</CardContent>
          </Card>
          <Card className="border-warning/40">
            <CardContent className="space-y-2 p-4 text-table">
              <p className="flex items-center gap-2 font-medium"><ShieldAlert className="size-4 text-warning" />Patient data policy</p>
              <p className="text-muted-foreground">{s.phi_allowed ? "External AI is allowed for patient data (server setting AI_PHI_ALLOWED). A BAA must cover the provider." : "Real patient data is never sent to external AI (AI_PHI_ALLOWED=false). Organizations flagged as synthetic may use it for demos."}</p>
              <p className="text-muted-foreground">Key encryption: {s.encryption}.</p>
            </CardContent>
          </Card>
        </div>
      </div>
      {dialog}
    </>
  );
}
