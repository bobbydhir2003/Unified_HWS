import { useQuery } from "@tanstack/react-query";
import { Bot, FileSearch, HeartPulse, MessageSquareText, Mic, ShieldAlert, Stethoscope } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { AIBadge, LoadingRows, PageHeader, SimulatedBadge, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import { titleCase } from "@/lib/utils";

type ProviderStatus = { configured: string; active: string; live: boolean; note: string; openai_key_configured: boolean; models: Record<string, string | null>; phi_allowed: boolean; org_is_synthetic: boolean; cost_tracking: boolean; live_validation: string };
type Jobs = { jobs: { id: string; kind: string; status: string; provider: string; model: string | null; latency_ms: number | null; input_tokens: number | null; output_tokens: number | null; cost_usd: number | null; error: string | null; created_at: string; phi_sent_externally: boolean }[]; cost_30d_usd: number; cost_tracking: boolean };

const usd = (n: number) => "$" + n.toFixed(4);

const TOOLS = [
  { to: "/patients", icon: MessageSquareText, title: "Chart assistant", body: "Ask questions about one patient's chart. Every answer cites the records it used; it refuses diagnosis and ordering.", how: "Open a chart → Ask AI" },
  { to: "/encounters", icon: Mic, title: "Medical scribe", body: "Consented visit audio or transcript → SOAP draft. The clinician edits and attests before signing.", how: "Open a visit → Scribe" },
  { to: "/documents", icon: FileSearch, title: "Document intelligence", body: "Faxes, uploads and portal cards are classified and extracted. Staff confirm identity before anything is filed.", how: "Documents → review queue" },
  { to: "/insurance", icon: HeartPulse, title: "Insurance card reading", body: "Portal card photos are read into a draft; insurance staff compare and confirm, then the payer is re-checked.", how: "Insurance Guardian → Card review" },
];

export function AIWorkspace() {
  const { can } = useAuth();
  const st = useQuery({ queryKey: ["ai", "provider"], queryFn: () => get<ProviderStatus>("/ai/provider") });
  const jobs = useQuery({ queryKey: ["ai", "jobs"], queryFn: () => get<Jobs>("/ai/jobs"), enabled: can("clinic:manage") });
  const [checking, setChecking] = React.useState(false);
  const s = st.data;
  const health = async () => {
    setChecking(true);
    try {
      const r = await post<{ ok: boolean | null; detail?: string; error?: string; latency_ms?: number }>("/ai/provider/health");
      if (r.ok) toast.success(`Provider reachable (${r.latency_ms} ms)`);
      else toast.error(r.detail ?? r.error ?? "Provider check failed");
    } catch (e) { toastError(e); } finally { setChecking(false); }
  };
  return (
    <>
      <PageHeader title="AI assistants" description="One place for the AI tools. AI output is always a draft: a person reviews, edits and approves before anything reaches a chart, a claim or a patient." />
      <Card className="mb-5">
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
          <div><CardTitle className="flex items-center gap-2"><Bot className="size-4" />AI provider</CardTitle>
            {s && <p className="mt-1 text-[13px] text-muted-foreground">{s.note}</p>}</div>
          {s && (s.live ? <Badge variant="ai">Live: {titleCase(s.active)}</Badge> : <SimulatedBadge label="Rule-based simulation" />)}
        </CardHeader>
        <CardContent>{!s ? <LoadingRows rows={2} /> : (
          <div className="grid gap-3 text-[13px] sm:grid-cols-2 lg:grid-cols-4">
            <div><p className="text-xs text-muted-foreground">Configured provider</p><p className="font-medium">{titleCase(s.configured)}{s.configured === "openai" && !s.openai_key_configured ? " (no key)" : ""}</p></div>
            <div><p className="text-xs text-muted-foreground">Models</p><p className="font-medium">{s.models.text ?? "—"}{s.models.transcription ? ` · ${s.models.transcription}` : ""}</p></div>
            <div><p className="text-xs text-muted-foreground">Patient data policy</p><p className="font-medium">{s.phi_allowed ? "External AI allowed (BAA required)" : s.org_is_synthetic ? "Synthetic org — demo data only" : "Blocked for patient data"}</p></div>
            <div><p className="text-xs text-muted-foreground">Live provider validation</p><p className="font-medium">{s.live_validation === "pending" ? "Pending (no credentials)" : "Run a health check"}</p></div>
            {can("clinic:manage") && s.configured === "openai" && (
              <div className="col-span-full"><Button size="sm" variant="outline" loading={checking} onClick={health}>Check provider connection</Button></div>
            )}
          </div>
        )}</CardContent>
      </Card>
      <div className="mb-5 grid gap-4 md:grid-cols-2">{TOOLS.map((t) => (
        <Link key={t.title} to={t.to} className="group rounded-xl border bg-card p-5 hover:border-primary/40 hover:shadow-sm">
          <div className="flex items-center gap-2"><span className="rounded-lg bg-ai-soft p-2 text-ai"><t.icon className="size-4" /></span><p className="font-semibold">{t.title}</p><AIBadge label="Draft only" className="ml-auto" /></div>
          <p className="mt-2 text-[13.5px] text-muted-foreground">{t.body}</p>
          <p className="mt-3 text-xs font-medium text-primary group-hover:underline">{t.how} →</p>
        </Link>))}</div>
      <Card className="mb-5 border-warning/40">
        <CardContent className="flex gap-3 p-4 text-[13px]"><ShieldAlert className="mt-0.5 size-5 shrink-0 text-warning" />
          <p>AI never signs notes, prescribes, diagnoses, changes claim codes or messages patients on its own. Those actions require an authorized person, and agent actions wait in the approval queue (<Link className="text-primary hover:underline" to="/worklist">My work → Approvals</Link>).</p></CardContent>
      </Card>
      {can("clinic:manage") && (
        <Card className="overflow-hidden">
          <CardHeader className="flex-row items-center justify-between"><CardTitle className="flex items-center gap-2"><Stethoscope className="size-4" />Recent AI activity</CardTitle>
            {jobs.data && <span className="text-[13px] text-muted-foreground">{jobs.data.cost_tracking ? `Cost (30 days): ${usd(jobs.data.cost_30d_usd)}` : "Cost tracking off (set AI_PRICES)"}</span>}</CardHeader>
          {jobs.isLoading ? <LoadingRows /> : (
            <Table><THead><TR><TH>When</TH><TH>Task</TH><TH>Provider</TH><TH>Status</TH><TH className="text-right">Tokens</TH><TH className="text-right">Latency</TH><TH className="text-right">Cost</TH></TR></THead>
              <TBody>{(jobs.data?.jobs ?? []).slice(0, 25).map((j) => (
                <TR key={j.id}><TD>{fmtDateTime(j.created_at)}</TD><TD>{titleCase(j.kind.replace(/_/g, " "))}</TD><TD>{j.provider}{j.model ? ` · ${j.model}` : ""}</TD>
                  <TD><Badge variant={j.status === "succeeded" ? "success" : j.status === "failed" ? "danger" : "neutral"} title={j.error ?? undefined}>{j.status}</Badge></TD>
                  <TD className="text-right tabular">{j.input_tokens != null ? `${j.input_tokens}/${j.output_tokens}` : "—"}</TD>
                  <TD className="text-right tabular">{j.latency_ms != null ? `${j.latency_ms} ms` : "—"}</TD>
                  <TD className="text-right tabular">{j.cost_usd != null ? usd(j.cost_usd) : "—"}</TD></TR>))}</TBody></Table>
          )}
        </Card>
      )}
    </>
  );
}
