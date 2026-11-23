import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Globe, Lock, OctagonX, PlugZap, Power, Save, Trash2, XCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { LoadingRows, toastError, useConfirm } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect } from "@/components/ui/input";
import { api, get, post, put } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { titleCase } from "@/lib/utils";

type Limits = {
  visitor_daily_requests: number; global_daily_requests: number; monthly_budget_usd: number; visitor_concurrency: number; global_concurrency: number;
  realtime_enabled: boolean; realtime_max_seconds: number; realtime_daily_sessions: number;
};
type Owner = {
  platform: { ai_disabled: boolean; key_configured: boolean }; demo_mode: boolean; operator_disabled: boolean;
  demo: {
    enabled: boolean; key_source: "dedicated" | "platform"; text_model: string; vision_model: string; transcription_model: string; realtime_model: string;
    allowed_models: string[]; allowed_agents: string[]; limits: Limits; active: boolean;
    dedicated_key: { configured: boolean; hint: string | null; updated_at: string | null };
    last_test: null | { at: string; ok: boolean; error?: string; capabilities?: Record<string, { ok: boolean; error?: string }> };
  };
  usage: { today: { requests: number; estimated_cost_usd: number; voice_sessions: number }; month: { estimated_cost_usd: number; budget_usd: number }; note: string };
  agents: string[];
};

const LIMIT_FIELDS: [keyof Limits, string, string][] = [
  ["visitor_daily_requests", "Requests per visitor per day", ""], ["global_daily_requests", "Requests per day (all visitors)", ""],
  ["monthly_budget_usd", "Estimated monthly budget (USD)", "Estimate, not a billing cap"], ["visitor_concurrency", "Concurrent requests per visitor", ""],
  ["global_concurrency", "Concurrent requests (all visitors)", ""], ["realtime_max_seconds", "Voice session length (seconds)", ""],
  ["realtime_daily_sessions", "Voice sessions per day", ""],
];

/** Platform owner (real Super Admin only): the persistent AI provider for public demo visitors, its limits, usage and kill switches. */
export function OwnerAICard() {
  const qc = useQueryClient();
  const { confirm, dialog } = useConfirm();
  const q = useQuery({ queryKey: ["ai", "owner"], queryFn: () => get<Owner>("/admin/ai-owner"), retry: false });
  const [f, setF] = React.useState<Owner["demo"] | null>(null);
  const [key, setKey] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (q.data && !f) setF(q.data.demo); }, [q.data, f]);
  if (q.isError) return null; // not the platform owner
  if (!q.data || !f) return <Card><CardContent className="p-4"><LoadingRows rows={3} /></CardContent></Card>;
  const o = q.data;
  const refresh = (d: Owner) => { qc.setQueryData(["ai", "owner"], d); setF(d.demo); qc.invalidateQueries({ queryKey: ["ai", "settings"] }); };
  const save = async (enabled = f.enabled) => {
    setBusy(true);
    try {
      const d = await put<Owner>("/admin/ai-owner/demo", { enabled, key_source: f.key_source, api_key: key || null, text_model: f.text_model,
        vision_model: f.vision_model || null, transcription_model: f.transcription_model || null, realtime_model: f.realtime_model || null,
        allowed_models: f.allowed_models, allowed_agents: f.allowed_agents, limits: f.limits });
      setKey(""); refresh(d); toast.success("Demo AI settings saved");
    } catch (e) { toastError(e); } finally { setBusy(false); }
  };
  const test = async () => {
    setBusy(true);
    try { const r = await post<{ ok: boolean; error?: string }>("/admin/ai-owner/demo/test"); r.ok ? toast.success("Demo provider verified with real calls") : toast.error(r.error ?? "Some capabilities failed"); qc.invalidateQueries({ queryKey: ["ai", "owner"] }); setF(null); }
    catch (e) { toastError(e); } finally { setBusy(false); }
  };
  const lim = (k: keyof Limits, v: string) => setF({ ...f, limits: { ...f.limits, [k]: k === "monthly_budget_usd" ? Number(v) : Math.round(Number(v)) } });
  const t = o.demo.last_test;
  return (
    <Card data-testid="owner-ai">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2"><Globe className="size-4" />Public demo AI (platform owner)</CardTitle>
        {o.demo.active ? <Badge variant="ai">On — owner-managed</Badge> : <Badge variant="neutral">Off</Badge>}
      </CardHeader>
      <CardContent className="space-y-4 text-table">
        <p className="text-muted-foreground">Gives demo visitors live AI using a key you control. Visitors never see the key. Requests stop at the limits below; if limits can't be enforced, requests are refused. {!o.demo_mode && "Demo mode is off on this server, so this has no effect until it is enabled."}</p>
        {o.operator_disabled && <p className="rounded-lg bg-warning-soft px-3 py-2">The server operator switched demo AI off (DEMO_AI_DISABLED). It stays off regardless of this setting.</p>}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Key source" hint="A separate OpenAI project key with its own spending limit is recommended.">
            <NativeSelect value={f.key_source} onChange={(e) => setF({ ...f, key_source: e.target.value as "dedicated" | "platform" })}>
              <option value="dedicated">Dedicated demo key</option><option value="platform" disabled={!o.platform.key_configured}>Platform key</option>
            </NativeSelect>
          </Field>
          {f.key_source === "dedicated" && (
            <Field label={o.demo.dedicated_key.configured ? "Replace demo key" : "Demo API key"} hint={o.demo.dedicated_key.configured ? `Stored (${o.demo.dedicated_key.hint})${o.demo.dedicated_key.updated_at ? ` · ${fmtDateTime(o.demo.dedicated_key.updated_at)}` : ""}` : "Encrypted on the server; never shown again."}>
              <Input type="password" autoComplete="off" spellCheck={false} value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-…" />
            </Field>
          )}
          <Field label="Text model"><Input value={f.text_model} onChange={(e) => setF({ ...f, text_model: e.target.value })} /></Field>
          <Field label="Vision model"><Input value={f.vision_model} onChange={(e) => setF({ ...f, vision_model: e.target.value })} /></Field>
          <Field label="Transcription model" hint="A speech-to-text model (e.g. one with 'transcribe' in its name)"><Input value={f.transcription_model} onChange={(e) => setF({ ...f, transcription_model: e.target.value })} /></Field>
          <Field label="Realtime voice model"><Input value={f.realtime_model} onChange={(e) => setF({ ...f, realtime_model: e.target.value })} /></Field>
          <Field label="Other allowed models" hint="Comma-separated; visitors can pick only these">
            <Input value={f.allowed_models.join(", ")} onChange={(e) => setF({ ...f, allowed_models: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
          </Field>
          <label className="flex items-center gap-2 self-end pb-2"><input type="checkbox" checked={f.limits.realtime_enabled} onChange={(e) => setF({ ...f, limits: { ...f.limits, realtime_enabled: e.target.checked } })} />Allow voice sessions</label>
        </div>
        <fieldset>
          <legend className="mb-2 text-label font-medium text-muted-foreground">Assistants available to visitors</legend>
          <div className="grid gap-1.5 sm:grid-cols-2">{o.agents.map((a) => (
            <label key={a} className="flex items-center gap-2"><input type="checkbox" checked={f.allowed_agents.includes(a)}
              onChange={(e) => setF({ ...f, allowed_agents: e.target.checked ? [...f.allowed_agents, a] : f.allowed_agents.filter((x) => x !== a) })} />{titleCase(a.replace(/_/g, " "))}</label>))}</div>
        </fieldset>
        <div className="grid gap-3 sm:grid-cols-2">{LIMIT_FIELDS.map(([k, l, h]) => (
          <Field key={k} label={l} hint={h || undefined}><Input type="number" min={0} step={k === "monthly_budget_usd" ? "0.5" : "1"} value={String(f.limits[k])} onChange={(e) => lim(k, e.target.value)} /></Field>))}</div>
        <div className="rounded-lg border bg-muted/30 p-3" data-testid="owner-ai-usage">
          <p className="font-medium">Usage (estimated)</p>
          <p className="text-muted-foreground">Today: {o.usage.today.requests} requests · ${o.usage.today.estimated_cost_usd.toFixed(4)} · {o.usage.today.voice_sessions} voice sessions. This month: ${o.usage.month.estimated_cost_usd.toFixed(4)} of ${o.usage.month.budget_usd.toFixed(2)}.</p>
          <p className="text-label text-muted-foreground">{o.usage.note}</p>
        </div>
        {t && (
          <div className="space-y-1">
            <p className="flex items-center gap-2 font-medium">{t.ok ? <CheckCircle2 className="size-4 text-success" /> : <XCircle className="size-4 text-destructive" />}Last test {fmtDateTime(t.at)}</p>
            {t.error && <p className="text-destructive">{t.error}</p>}
            {t.capabilities && <ul>{Object.entries(t.capabilities).map(([k, c]) => <li key={k} className="flex items-center gap-2">{c.ok ? <CheckCircle2 className="size-3.5 text-success" /> : <XCircle className="size-3.5 text-destructive" />}{titleCase(k)} {c.ok ? "works" : c.error}</li>)}</ul>}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <Button loading={busy} onClick={() => save()}><Save />Save</Button>
          <Button variant="outline" loading={busy} onClick={test}><PlugZap />Test demo provider</Button>
          {o.demo.enabled ? (
            <Button variant="destructive" loading={busy} onClick={async () => { try { refresh(await post<Owner>("/admin/ai-owner/demo/disable")); toast.success("Public demo AI turned off"); } catch (e) { toastError(e); } }}><OctagonX />Turn off now</Button>
          ) : (
            <Button variant="outline" loading={busy} onClick={async () => {
              if (!(await confirm({ title: "Turn on public demo AI?", description: "Demo visitors will use your key (server-side only) within the limits shown. Make sure the OpenAI project also has a spending limit.", confirmLabel: "Turn on" }))) return;
              await save(true);
            }}><Power />Turn on</Button>
          )}
          {o.demo.dedicated_key.configured && <Button variant="ghost" onClick={async () => {
            if (!(await confirm({ title: "Remove the demo key?", description: "Public demo AI turns off if it uses this key.", confirmLabel: "Remove", destructive: true }))) return;
            try { refresh(await api<Owner>("/admin/ai-owner/demo/key", { method: "DELETE" })); toast.success("Demo key removed"); } catch (e) { toastError(e); }
          }}><Trash2 />Remove demo key</Button>}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
          <p className="flex items-center gap-2"><Lock className="size-4" />All platform AI: {o.platform.ai_disabled ? <strong className="text-destructive">switched off</strong> : "on"}</p>
          <Button size="sm" variant={o.platform.ai_disabled ? "outline" : "destructive"} onClick={async () => {
            const off = !o.platform.ai_disabled;
            if (off && !(await confirm({ title: "Switch off all AI?", description: "Every AI feature shows its labelled simulation until you switch it back on. Rules, tasks and notifications keep working.", confirmLabel: "Switch off", destructive: true }))) return;
            try { refresh(await put<Owner>("/admin/ai-owner/platform", { ai_disabled: off })); toast.success(off ? "All AI switched off" : "AI switched back on"); } catch (e) { toastError(e); }
          }}>{o.platform.ai_disabled ? "Switch AI back on" : "Emergency: switch off all AI"}</Button>
        </div>
      </CardContent>
      {dialog}
    </Card>
  );
}
