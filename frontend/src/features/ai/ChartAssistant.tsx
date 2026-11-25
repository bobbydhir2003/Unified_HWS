import { Bot, Loader2, Send, ShieldAlert, Sparkles } from "lucide-react";
import { Dialog as D } from "radix-ui";
import * as React from "react";
import { Link } from "react-router-dom";
import { AIBadge, SimulatedBadge, toastError } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, SheetContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tooltip } from "@/components/ui/menu";
import { post } from "@/lib/api";
import { HMSAssistSheet, useAssistAgent } from "@/features/assist/HMSAssistPanel";
import { cn, titleCase } from "@/lib/utils";

type Citation = { id: string; type: string; title: string; date: string | null; snippet: string; link: string };
type Reply = { answer: string; citations: Citation[]; refused: boolean; insufficient: boolean; provider: string };
type Turn = { role: "user" | "assistant"; content: string; reply?: Reply };

const SUGGESTIONS = ["Summarize this patient's history", "What allergies are recorded?", "List current medications", "What happened at the last visit?", "Show recent lab results", "Blood pressure trend"];

function AnswerText({ text, citations }: { text: string; citations: Citation[] }) {
  const byId = new Map(citations.map((c) => [c.id, c]));
  const parts = text.split(/(\[S\d+\])/g);
  return (
    <p className="whitespace-pre-wrap leading-relaxed">
      {parts.map((p, i) => {
        const m = p.match(/^\[(S\d+)\]$/);
        const c = m && byId.get(m[1]);
        if (!m) return <React.Fragment key={i}>{p}</React.Fragment>;
        return c ? (
          <Tooltip key={i} content={`${c.title}${c.date ? ` · ${c.date}` : ""}`}>
            <Link to={c.link} className="mx-0.5 inline-flex rounded bg-accent px-1 align-baseline font-mono text-label font-semibold text-accent-foreground hover:underline">{m[1]}</Link>
          </Tooltip>
        ) : <span key={i} className="font-mono text-label text-muted-foreground">{p}</span>;
      })}
    </p>
  );
}

/** HMS Assist · Chart: the shared conversational panel bound to this patient (persistent, cited). Falls back to the original
 * in-memory assistant only when HMS Assist conversations are not enabled for the organization. */
export function ChartAssistant(props: { patientId: string; patientName: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const ctx = { type: "patient" as const, id: props.patientId };
  const { agent, loading } = useAssistAgent("doctor_assistant", ctx);
  if (agent) return props.open ? <HMSAssistSheet agent={agent} context={ctx} open={props.open} onOpenChange={props.onOpenChange} /> : null;
  if (loading && props.open) return null;
  return <LegacyChartAssistant {...props} />;
}

function LegacyChartAssistant({ patientId, patientName, open, onOpenChange }: { patientId: string; patientName: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [q, setQ] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const pane = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => { setTurns([]); }, [patientId]);
  React.useEffect(() => { pane.current?.scrollTo({ top: pane.current.scrollHeight, behavior: "smooth" }); }, [turns, busy]);
  const ask = async (question: string) => {
    if (!question.trim() || busy) return;
    const history = turns.map((t) => ({ role: t.role, content: t.content }));
    setTurns((t) => [...t, { role: "user", content: question }]);
    setQ("");
    setBusy(true);
    try {
      const r = await post<Reply>(`/patients/${patientId}/assistant`, { question, history });
      setTurns((t) => [...t, { role: "assistant", content: r.answer, reply: r }]);
    } catch (e) { toastError(e); setTurns((t) => t.slice(0, -1)); setQ(question); } finally { setBusy(false); }
  };
  const provider = [...turns].reverse().find((t) => t.reply)?.reply?.provider;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <SheetContent className="max-w-lg" aria-describedby={undefined}>
        <div className="border-b px-5 py-4">
          <D.Title className="flex items-center gap-2 text-base font-semibold"><Sparkles className="size-4 text-ai" />Chart assistant</D.Title>
          <p className="mt-0.5 text-table text-muted-foreground">Answers come only from {patientName}'s chart, with sources. It won't prescribe, order or diagnose.</p>
          <div className="mt-2 flex gap-1.5"><AIBadge label="AI — verify before acting" />{provider === "simulated" && <SimulatedBadge label="Rule-based simulation" />}</div>
        </div>
        <div ref={pane} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4 text-body">
          {!turns.length && (
            <div className="space-y-2">
              <p className="text-table text-muted-foreground">Try asking:</p>
              <div className="flex flex-wrap gap-1.5">{SUGGESTIONS.map((s) => <button key={s} onClick={() => ask(s)} className="rounded-full border px-3 py-1 text-table hover:border-primary hover:text-primary">{s}</button>)}</div>
            </div>
          )}
          {turns.map((t, i) => t.role === "user" ? (
            <div key={i} className="ml-auto max-w-[85%] rounded-2xl bg-primary px-3.5 py-2 text-primary-foreground">{t.content}</div>
          ) : (
            <div key={i} className="space-y-2">
              <div className={cn("rounded-2xl border px-3.5 py-2.5", t.reply?.refused ? "border-warning/40 bg-warning-soft" : "bg-card")}>
                <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">{t.reply?.refused ? <ShieldAlert className="size-3.5 text-warning" /> : <Bot className="size-3.5 text-ai" />}{t.reply?.refused ? "Can't help with that" : "From the chart"}</div>
                <AnswerText text={t.content} citations={t.reply?.citations ?? []} />
              </div>
              {!!t.reply?.citations.length && (
                <details className="text-label">
                  <summary className="cursor-pointer text-muted-foreground">{t.reply.citations.length} source{t.reply.citations.length > 1 ? "s" : ""}</summary>
                  <ul className="mt-1.5 space-y-1">{t.reply.citations.map((c) => (
                    <li key={c.id}><Link to={c.link} className="block rounded-md border px-2 py-1.5 hover:bg-muted/50"><span className="font-mono font-semibold text-primary">{c.id}</span> {titleCase(c.type)} · {c.title}{c.date ? ` · ${c.date}` : ""}<span className="block truncate text-muted-foreground">{c.snippet}</span></Link></li>
                  ))}</ul>
                </details>
              )}
            </div>
          ))}
          {busy && <p className="flex items-center gap-2 text-muted-foreground"><Loader2 className="size-4 animate-spin" />Searching the chart…</p>}
        </div>
        <form className="flex gap-2 border-t p-3" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about this patient's chart…" aria-label="Question" autoFocus />
          <Button type="submit" disabled={!q.trim() || busy}><Send /></Button>
        </form>
      </SheetContent>
    </Dialog>
  );
}
