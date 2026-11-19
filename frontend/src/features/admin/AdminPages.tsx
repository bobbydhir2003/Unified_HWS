import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronLeft, ChevronRight, FlaskConical, Mail, Plus, ScrollText, XCircle } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { EmptyState, ErrorState, KeyValue, LoadingRows, PageHeader } from "@/components/common";
import { FormDialog } from "@/components/common/FormDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import type { Page } from "@/lib/types";
import { titleCase } from "@/lib/utils";

type AuditRow = { id: string; action: string; actor_name: string | null; resource_type: string | null; resource_id: string | null; patient_id: string | null; outcome: string; ip_address: string | null; details: Record<string, unknown>; created_at: string };

export function AuditPage() {
  const [action, setAction] = React.useState("");
  const [outcome, setOutcome] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [dAction, setDAction] = React.useState("");
  React.useEffect(() => { const t = setTimeout(() => { setDAction(action); setPage(1); }, 300); return () => clearTimeout(t); }, [action]);
  const q = useQuery({
    queryKey: ["audit", dAction, outcome, page],
    queryFn: () => get<Page<AuditRow>>("/audit", { action: dAction, outcome, page, page_size: 50 }),
    placeholderData: keepPreviousData,
  });
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / 50)) : 1;
  return (
    <>
      <PageHeader title="Audit log" description="Append-only record of sign-ins, chart access and changes. Entries cannot be edited or deleted." />
      <Card className="overflow-hidden">
        <div className="flex flex-wrap gap-2 border-b p-3">
          <Input value={action} onChange={(e) => setAction(e.target.value)} placeholder="Action prefix, e.g. patient. or auth.login" className="max-w-xs" aria-label="Filter by action" />
          <NativeSelect value={outcome} onChange={(e) => { setOutcome(e.target.value); setPage(1); }} className="w-40" aria-label="Outcome">
            <option value="">All outcomes</option><option value="success">Success</option><option value="failure">Failure</option><option value="denied">Denied</option>
          </NativeSelect>
        </div>
        {q.error ? <ErrorState error={q.error} /> : q.isLoading ? <LoadingRows rows={10} /> : !q.data?.items.length ? <EmptyState icon={ScrollText} title="No matching events" /> : (
          <Table>
            <THead><TR><TH>Time</TH><TH>Actor</TH><TH>Action</TH><TH className="hidden md:table-cell">Resource</TH><TH>Outcome</TH><TH className="hidden lg:table-cell">IP</TH></TR></THead>
            <TBody>
              {q.data.items.map((r) => (
                <TR key={r.id}>
                  <TD className="whitespace-nowrap text-muted-foreground tabular">{fmtDateTime(r.created_at)}</TD>
                  <TD>{r.actor_name ?? <span className="text-muted-foreground">—</span>}</TD>
                  <TD><code className="rounded bg-muted px-1.5 py-0.5 text-xs">{r.action}</code>
                    {Object.keys(r.details).length > 0 && <span className="ml-2 text-xs text-muted-foreground">{Object.entries(r.details).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`).join(" · ").slice(0, 80)}</span>}
                  </TD>
                  <TD className="hidden md:table-cell">
                    {r.patient_id ? <Link to={`/patients/${r.patient_id}`} className="text-primary hover:underline">{r.resource_type ?? "patient"}</Link> : r.resource_type ?? "—"}
                  </TD>
                  <TD><Badge variant={r.outcome === "success" ? "success" : "danger"}>{r.outcome}</Badge></TD>
                  <TD className="hidden font-mono text-xs text-muted-foreground lg:table-cell">{r.ip_address ?? "—"}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
        {q.data && q.data.total > 50 && (
          <div className="flex items-center justify-between border-t px-4 py-2.5 text-[13px] text-muted-foreground">
            <span>Page {page} of {pages} · {q.data.total.toLocaleString()} events</span>
            <div className="flex gap-1">
              <Button variant="outline" size="icon-sm" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page"><ChevronLeft /></Button>
              <Button variant="outline" size="icon-sm" disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label="Next page"><ChevronRight /></Button>
            </div>
          </div>
        )}
      </Card>
    </>
  );
}

type Outbox = { id: string; channel: string; to_address: string; subject: string; body: string; status: string; created_at: string };

export function OutboxPage() {
  const q = useQuery({ queryKey: ["outbox"], queryFn: () => get<Outbox[]>("/outbox") });
  const [open, setOpen] = React.useState<string | null>(null);
  return (
    <>
      <PageHeader title="Message outbox" description="Emails and texts generated by the system. Delivery is simulated — nothing leaves this environment." />
      <Card className="overflow-hidden">
        {q.isLoading ? <LoadingRows /> : !q.data?.length ? <EmptyState icon={Mail} title="No messages yet" description="Invitations, password resets and reminders will appear here." /> : (
          <ul className="divide-y">
            {q.data.map((m) => (
              <li key={m.id}>
                <button onClick={() => setOpen(open === m.id ? null : m.id)} className="flex w-full items-center gap-3 px-5 py-3 text-left hover:bg-muted/40">
                  <Mail className="size-4 text-muted-foreground" />
                  <span className="min-w-0 flex-1"><span className="block text-[13.5px] font-medium">{m.subject}</span><span className="block text-xs text-muted-foreground">To {m.to_address} · {fmtDateTime(m.created_at)}</span></span>
                  <Badge variant="warning"><FlaskConical />{m.status}</Badge>
                </button>
                {open === m.id && <pre className="mx-5 mb-4 whitespace-pre-wrap rounded-lg bg-muted p-3 font-sans text-[13px]">{m.body}</pre>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

type Status = {
  checks: Record<string, { ok: boolean; latency_ms?: number; error?: string; detail?: string }>;
  environment: string; migration: string; ai_provider: string; ai_phi_allowed: boolean; storage_backend: string; mfa_enforced: boolean;
  integrations: Record<string, string>;
};

export function SystemPage() {
  const q = useQuery({ queryKey: ["system"], queryFn: () => get<Status>("/system/status"), refetchInterval: 30_000 });
  const s = q.data;
  return (
    <>
      <PageHeader title="System status" description="Dependency health and configuration for this environment." />
      {q.error ? <ErrorState error={q.error} /> : !s ? <LoadingRows /> : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader><CardTitle>Dependencies</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {Object.entries(s.checks).map(([k, c]) => (
                <div key={k} className="flex items-center gap-3 rounded-lg border px-3 py-2">
                  {c.ok ? <CheckCircle2 className="size-4 text-success" /> : <XCircle className="size-4 text-destructive" />}
                  <span className="flex-1 text-[13.5px] font-medium">{titleCase(k)}</span>
                  <span className="text-xs text-muted-foreground">{c.ok ? c.detail ?? `${c.latency_ms} ms` : c.error}</span>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Configuration</CardTitle></CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-4">
                <KeyValue label="Environment" value={s.environment} />
                <KeyValue label="Schema version" value={<code className="text-xs">{s.migration}</code>} />
                <KeyValue label="AI provider" value={s.ai_provider} />
                <KeyValue label="PHI to external AI" value={s.ai_phi_allowed ? "Allowed (BAA required)" : "Blocked"} />
                <KeyValue label="Document storage" value={s.storage_backend} />
                <KeyValue label="MFA enforcement" value={s.mfa_enforced ? "Enforced for admins" : "Optional"} />
              </dl>
            </CardContent>
          </Card>
          <Card className="lg:col-span-2">
            <CardHeader><CardTitle>External integrations</CardTitle></CardHeader>
            <CardContent className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {Object.entries(s.integrations).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between rounded-lg border px-3 py-2 text-[13px]">
                  <span className="font-medium">{titleCase(k)}</span><Badge variant="warning"><FlaskConical />{v}</Badge>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}

type Org = { id: string; name: string; slug: string; status: string; created_at: string };

export function OrganizationsPage() {
  const qc = useQueryClient();
  const { switchOrg, me } = useAuth();
  const [open, setOpen] = React.useState(false);
  const q = useQuery({ queryKey: ["orgs"], queryFn: () => get<Org[]>("/organizations") });
  const memberOf = new Set(me?.memberships.map((m) => m.organization_id));
  return (
    <>
      <PageHeader title="Organizations" description="Platform-level tenant management." actions={<Button onClick={() => setOpen(true)}><Plus />New organization</Button>} />
      <Card className="overflow-hidden">
        {q.isLoading ? <LoadingRows /> : (
          <Table>
            <THead><TR><TH>Name</TH><TH>Slug</TH><TH>Status</TH><TH>Created</TH><TH /></TR></THead>
            <TBody>
              {q.data?.map((o) => (
                <TR key={o.id}>
                  <TD className="font-medium">{o.name}</TD><TD className="font-mono text-xs">{o.slug}</TD>
                  <TD><Badge variant={o.status === "active" ? "success" : "danger"}>{o.status}</Badge></TD>
                  <TD className="text-muted-foreground">{fmtDateTime(o.created_at)}</TD>
                  <TD>{memberOf.has(o.id) && <Button size="xs" variant="outline" onClick={() => switchOrg(o.id)}>Switch to</Button>}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
      <FormDialog open={open} onOpenChange={setOpen} title="New organization" description="Creates the tenant, its first clinic and (optionally) invites its first administrator."
        fields={[
          { name: "name", label: "Organization name", required: true },
          { name: "slug", label: "Slug (lowercase, dashes)", required: true, span: 1 },
          { name: "timezone", label: "Timezone", type: "select", options: [["America/New_York", "Eastern"], ["America/Chicago", "Central"], ["America/Denver", "Mountain"], ["America/Los_Angeles", "Pacific"]], span: 1 },
          { name: "first_clinic_name", label: "First clinic name", required: true, span: 1 },
          { name: "first_clinic_code", label: "Clinic code", required: true, span: 1 },
          { name: "admin_email", label: "Admin email (optional)", span: 1 },
          { name: "admin_first_name", label: "Admin first name", span: 1 },
        ]}
        onSubmit={async (v) => {
          await post("/organizations", v);
          qc.invalidateQueries({ queryKey: ["orgs"] });
          toast.success("Organization created");
        }} />
    </>
  );
}
