import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, CheckCircle2, Play, RotateCcw, Save } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, LoadingRows, PageHeader, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/misc";
import { assistName } from "@/lib/assist";
import { get, patch, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, fromNow } from "@/lib/format";
import { titleCase } from "@/lib/utils";
import { CATEGORY_LABEL } from "./ops";

/** Case kinds that may receive optional AI assistance (backend/app/agents/case_assist.py RULES). */
type MonitorT = { key: string; name: string; description: string; category: string; is_enabled: boolean; config: Record<string, unknown>; config_help: Record<string, string>; version: number; open_cases: number;
  ai_assist?: { available: boolean; enabled: boolean; agent: string | null; trigger: string | null; actions: string[]; safety_rule_only: boolean } | null; last_run: { at: string; status: string; found: number; opened: number; closed: number; duration_ms: number; error: string | null } | null };
export type EngineHealth = { status: string; pending_events: number; retrying_events: number; oldest_pending_seconds: number; processed_24h: number; dead_events: { id: string; event_type: string; attempts: number; last_error: string; occurred_at: string }[]; monitor_failures_24h: number; last_monitor_run: string | null; notification_failures_24h: number };

export function EngineHealthCard() {
  const qc = useQueryClient();
  const { can } = useAuth();
  const h = useQuery({ queryKey: ["engine", "health"], queryFn: () => get<EngineHealth>("/engine/health"), refetchInterval: 30_000 });
  if (!h.data) return <Card><CardContent className="p-4"><LoadingRows rows={2} /></CardContent></Card>;
  const d = h.data;
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between"><CardTitle className="flex items-center gap-2"><Activity className="size-4" />Automation engine</CardTitle>
        <Badge variant={d.status === "healthy" ? "success" : "warning"}>{d.status === "healthy" ? <CheckCircle2 /> : <AlertTriangle />}{titleCase(d.status)}</Badge></CardHeader>
      <CardContent className="grid grid-cols-2 gap-3 text-table sm:grid-cols-4">
        <div><p className="text-xs text-muted-foreground">Events processed (24h)</p><p className="text-lg font-semibold tabular">{d.processed_24h}</p></div>
        <div><p className="text-xs text-muted-foreground">Queue</p><p className="text-lg font-semibold tabular">{d.pending_events}{d.retrying_events ? <span className="text-xs font-normal text-warning"> · {d.retrying_events} retrying</span> : null}</p></div>
        <div><p className="text-xs text-muted-foreground">Last monitor run</p><p className="font-medium">{d.last_monitor_run ? fromNow(d.last_monitor_run) : "Never"}</p></div>
        <div><p className="text-xs text-muted-foreground">Failures (24h)</p><p className="font-medium tabular">{d.monitor_failures_24h} monitor · {d.notification_failures_24h} notification</p></div>
        {d.dead_events.length > 0 && (
          <div className="col-span-full rounded-lg border border-destructive/30 bg-destructive-soft/40 p-3">
            <p className="mb-1 font-medium text-destructive">Failed events (after retries)</p>
            <ul className="space-y-1">{d.dead_events.map((e) => (
              <li key={e.id} className="flex items-center gap-2 text-xs"><code>{e.event_type}</code><span className="flex-1 truncate text-muted-foreground">{e.last_error}</span>
                {can("automation:manage") && <Button size="sm" variant="outline" onClick={async () => { try { await post(`/engine/events/${e.id}/retry`); toast.success("Queued for retry"); qc.invalidateQueries({ queryKey: ["engine"] }); } catch (err) { toastError(err); } }}><RotateCcw />Retry</Button>}
              </li>))}</ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function MonitorsPage() {
  const q = useQuery({ queryKey: ["monitors"], queryFn: () => get<MonitorT[]>("/monitors") });
  return (
    <>
      <PageHeader title="Monitors & rules" description="Deterministic monitors check live data on a schedule, open one accountable case per problem, and close it when the condition is verified as resolved." />
      <div className="mb-4"><EngineHealthCard /></div>
      {q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState title="No monitors registered" /> : (
        <div className="grid gap-4 lg:grid-cols-2">{q.data.map((m) => <MonitorCard key={m.key} m={m} />)}</div>
      )}
    </>
  );
}

function MonitorCard({ m }: { m: MonitorT }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const manage = can("automation:manage");
  const [cfg, setCfg] = React.useState<Record<string, string>>(() => Object.fromEntries(Object.entries(m.config).map(([k, v]) => [k, Array.isArray(v) ? v.join(", ") : String(v)])));
  const [busy, setBusy] = React.useState(false);
  const save = async (extra?: { is_enabled?: boolean }) => {
    const config: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(m.config)) {
      const raw = cfg[k];
      config[k] = Array.isArray(v) ? raw.split(",").map((x) => Number(x.trim())).filter((x) => !Number.isNaN(x)) : typeof v === "number" ? Number(raw) : typeof v === "boolean" ? raw === "true" : raw;
    }
    try { await patch(`/monitors/${m.key}`, extra ?? { config }); toast.success(extra ? (extra.is_enabled ? "Monitor enabled" : "Monitor paused") : "Saved — new rule version recorded"); qc.invalidateQueries({ queryKey: ["monitors"] }); } catch (e) { toastError(e); }
  };
  const run = async () => {
    setBusy(true);
    try { const r = await post<{ status: string; found: number; opened: number; closed: number }>(`/monitors/${m.key}/run`); toast.success(`Run ${r.status}: ${r.found} found · ${r.opened} opened · ${r.closed} closed`); qc.invalidateQueries({ queryKey: ["monitors"] }); qc.invalidateQueries({ queryKey: ["cases"] }); } catch (e) { toastError(e); } finally { setBusy(false); }
  };
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div><CardTitle>{m.name}</CardTitle><p className="mt-1 text-table text-muted-foreground">{m.description}</p></div>
        <Switch checked={m.is_enabled} disabled={!manage} onCheckedChange={(v) => save({ is_enabled: v })} aria-label={`Enable ${m.name}`} />
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2 text-xs"><Badge variant="outline">{CATEGORY_LABEL[m.category] ?? m.category}</Badge><Badge variant="neutral">Rule v{m.version}</Badge><Badge variant="neutral">Trigger: scheduled check · rule-based</Badge>
          {m.ai_assist?.enabled && <Badge variant="ai">{assistName(m.ai_assist.agent)} assists {m.ai_assist.trigger === "case_escalation" ? "escalated" : "new"} cases (approval required)</Badge>}
          {m.ai_assist?.safety_rule_only && <Badge variant="neutral">Safety-critical: rule-based only, no AI</Badge>}<Badge variant={m.open_cases ? "warning" : "success"}>{m.open_cases} open case{m.open_cases === 1 ? "" : "s"}</Badge>
          {m.last_run && <span className="text-muted-foreground">Last run {fmtDateTime(m.last_run.at)} · {m.last_run.status} · {m.last_run.found} found · {m.last_run.duration_ms} ms</span>}
        </div>
        {m.last_run?.error && <p className="text-xs text-destructive">{m.last_run.error}</p>}
        {m.ai_assist?.available && (
          <label className="flex items-center gap-2 rounded-md border bg-subtle px-3 py-2 text-table" data-testid={`monitor-ai-${m.key}`}>
            <Switch checked={m.ai_assist.enabled} disabled={!manage} aria-label={`AI assistance for ${m.name}`}
              onCheckedChange={async (v) => { try { await patch(`/monitors/${m.key}`, { ai_assist: v }); toast.success(v ? "AI assistance on for this monitor" : "AI assistance off for this monitor"); qc.invalidateQueries({ queryKey: ["monitors"] }); } catch (e) { toastError(e); } }} />
            <span>AI assistance by {assistName(m.ai_assist.agent)} — once per {m.ai_assist.trigger === "case_escalation" ? "escalation" : "new case"}, within daily and monthly AI limits; it can only propose {m.ai_assist.actions.map((a) => a.replace(/_/g, " ")).join(" or ")} for approval.</span>
          </label>
        )}
        <div className="grid gap-3 sm:grid-cols-2">{Object.keys(m.config).map((k) => (
          <Field key={k} label={titleCase(k.replace(/_/g, " "))} hint={m.config_help[k]}>
            <Input value={cfg[k]} disabled={!manage} onChange={(e) => setCfg({ ...cfg, [k]: e.target.value })} />
          </Field>))}</div>
        {manage && <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => save()}><Save />Save rule</Button><Button size="sm" variant="outline" loading={busy} onClick={run}><Play />Run now</Button></div>}
      </CardContent>
    </Card>
  );
}

