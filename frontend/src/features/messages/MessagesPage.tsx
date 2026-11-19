import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Inbox, Send } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { EmptyState, LoadingRows, PageHeader, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { PatientPicker, type PatientPick } from "@/features/schedule/AppointmentDialog";
import { get, post } from "@/lib/api";
import { fmtDateTime, fmtDob } from "@/lib/format";
import { cn, titleCase } from "@/lib/utils";

type Thread = {
  id: string; subject: string; category: string; status: string; last_message_at: string; unread: number;
  patient: { id: string; name: string; mrn: string; date_of_birth: string } | null;
  messages: { id: string; body: string; created_at: string; from_patient: boolean; sender: string }[];
};

export function MessagesPage() {
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const threadId = params.get("thread");
  const composing = params.get("new") !== null;
  const [status, setStatus] = React.useState<"open" | "closed">("open");
  const [mine, setMine] = React.useState(false);
  const list = useQuery({ queryKey: ["inbox", status, mine], queryFn: () => get<{ unread_threads: number; items: Thread[] }>("/messages", { status, mine }), refetchInterval: 15_000 });
  const thread = useQuery({ queryKey: ["thread", threadId], queryFn: () => get<Thread>(`/messages/${threadId}`), enabled: !!threadId });
  React.useEffect(() => { if (thread.data) qc.invalidateQueries({ queryKey: ["inbox"] }); }, [thread.data?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const [reply, setReply] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [patient, setPatient] = React.useState<PatientPick | null>(null);
  const [compose, setCompose] = React.useState({ subject: "", body: "" });
  const open = (id: string) => setParams({ thread: id });

  return (
    <>
      <PageHeader title="Messages" description="Secure conversations with patients." actions={<Button onClick={() => setParams({ new: "" })}><Send />New message</Button>} />
      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <Card className="overflow-hidden">
          <div className="flex items-center gap-1 border-b p-2.5">
            {(["open", "closed"] as const).map((s) => <button key={s} onClick={() => setStatus(s)} className={cn("rounded-md px-2.5 py-1 text-[13px] font-medium capitalize text-muted-foreground", status === s && "bg-accent text-accent-foreground")}>{s}</button>)}
            <label className="ml-auto flex items-center gap-1.5 text-[12.5px] text-muted-foreground"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />My patients</label>
          </div>
          {list.isLoading ? <LoadingRows /> : !list.data?.items.length ? <EmptyState icon={Inbox} title="Inbox zero" /> : (
            <ul className="max-h-[70vh] divide-y overflow-y-auto">
              {list.data.items.map((t) => (
                <li key={t.id}>
                  <button onClick={() => open(t.id)} className={cn("block w-full px-4 py-3 text-left hover:bg-muted/40", t.id === threadId && "bg-accent/50")}>
                    <span className="flex items-center gap-2"><span className={cn("truncate text-[13.5px]", t.unread ? "font-semibold" : "font-medium")}>{t.patient?.name}</span>{t.unread > 0 && <span className="size-2 shrink-0 rounded-full bg-primary" />}<span className="ml-auto shrink-0 text-[11px] text-muted-foreground">{fmtDateTime(t.last_message_at)}</span></span>
                    <span className="block truncate text-[13px]">{t.subject}</span>
                    <span className="block truncate text-xs text-muted-foreground">{t.messages[t.messages.length - 1]?.body}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="min-h-[60vh]">
          {composing ? (
            <form className="space-y-3 p-5" onSubmit={async (e) => {
              e.preventDefault();
              if (!patient) return;
              setBusy(true);
              try { const t = await post<Thread>("/messages", { patient_id: patient.id, ...compose, category: "general" }); setCompose({ subject: "", body: "" }); setPatient(null); qc.invalidateQueries({ queryKey: ["inbox"] }); open(t.id); }
              catch (err) { toastError(err); } finally { setBusy(false); }
            }}>
              <h2 className="font-semibold">New message to a patient</h2>
              <Field label="Patient" required><div><PatientPicker value={patient} onChange={setPatient} /></div></Field>
              <Field label="Subject" required><Input value={compose.subject} onChange={(e) => setCompose({ ...compose, subject: e.target.value })} /></Field>
              <Field label="Message" required><Textarea rows={6} value={compose.body} onChange={(e) => setCompose({ ...compose, body: e.target.value })} /></Field>
              <p className="text-xs text-muted-foreground">The patient is notified in their portal{" "}(email/SMS alerts are simulated).</p>
              <Button type="submit" loading={busy} disabled={!patient || compose.subject.trim().length < 2 || !compose.body.trim()}><Send />Send</Button>
            </form>
          ) : !threadId ? <EmptyState icon={Inbox} title="Select a conversation" className="h-full" /> : thread.isLoading ? <LoadingRows /> : thread.data && (
            <div className="flex h-full flex-col">
              <div className="flex flex-wrap items-center gap-2 border-b px-5 py-3">
                <div className="min-w-0">
                  <p className="font-semibold">{thread.data.subject} <Badge variant="outline" className="ml-1">{titleCase(thread.data.category)}</Badge></p>
                  {thread.data.patient && <p className="text-xs text-muted-foreground tabular"><Link to={`/patients/${thread.data.patient.id}`} className="font-medium text-primary hover:underline">{thread.data.patient.name}</Link> · DOB {fmtDob(thread.data.patient.date_of_birth)} · MRN {thread.data.patient.mrn}</p>}
                </div>
                {thread.data.status === "open" && <Button size="sm" variant="outline" className="ml-auto" onClick={async () => { try { await post(`/messages/${threadId}/close`); thread.refetch(); qc.invalidateQueries({ queryKey: ["inbox"] }); } catch (e) { toastError(e); } }}><CheckCircle2 />Mark resolved</Button>}
              </div>
              <ol className="flex-1 space-y-3 overflow-y-auto p-5">
                {thread.data.messages.map((m) => (
                  <li key={m.id} className={cn("max-w-[80%] rounded-2xl px-4 py-2.5 text-[13.5px]", m.from_patient ? "bg-muted" : "ml-auto bg-primary text-primary-foreground")}>
                    <p className="whitespace-pre-wrap">{m.body}</p>
                    <p className={cn("mt-1 text-[11px]", m.from_patient ? "text-muted-foreground" : "text-primary-foreground/70")}>{m.sender} · {fmtDateTime(m.created_at)}</p>
                  </li>
                ))}
              </ol>
              <form className="flex gap-2 border-t p-3" onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                try { await post(`/messages/${threadId}/reply`, { body: reply }); setReply(""); thread.refetch(); qc.invalidateQueries({ queryKey: ["inbox"] }); } catch (err) { toastError(err); } finally { setBusy(false); }
              }}>
                <Textarea rows={2} value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Reply to patient…" aria-label="Reply" className="min-h-0" />
                <Button type="submit" loading={busy} disabled={!reply.trim()} className="self-end"><Send />Send</Button>
              </form>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
