import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, FileCheck2, Loader2, RefreshCw, UserSearch, XCircle } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { AIBadge, ErrorState, KeyValue, LoadingRows, SimulatedBadge, toastError, useConfirm } from "@/components/common";
import { useCrumb } from "@/components/layout/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Checkbox, Skeleton } from "@/components/ui/misc";
import { PatientPicker, type PatientPick } from "@/features/schedule/AppointmentDialog";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, fmtDob } from "@/lib/format";
import { cn } from "@/lib/utils";
import { UploadZone } from "./DocumentsPage";
import { type Candidate, ConfidenceMeter, DOC_TYPES, DocStatusBadge, type DocumentDetail, type DocumentRow, docTypeLabel, sourceLabel, useDocumentBlob } from "./shared";

function Preview({ doc }: { doc: DocumentDetail }) {
  const blob = useDocumentBlob(doc.id);
  return (
    <Card className="flex min-h-[60vh] flex-col overflow-hidden lg:sticky lg:top-[72px] lg:h-[calc(100dvh-96px)]">
      <div className="flex items-center justify-between border-b px-4 py-2 text-[13px]">
        <span className="truncate font-medium">{doc.filename}</span>
        <span className="text-xs text-muted-foreground">{doc.page_count ? `${doc.page_count} page${doc.page_count > 1 ? "s" : ""} · ` : ""}{Math.round(doc.size_bytes / 1024)} KB</span>
      </div>
      <div className="flex-1 bg-muted/40">
        {blob.isLoading ? <Skeleton className="m-4 h-[calc(100%-2rem)]" /> : blob.error ? <ErrorState error={blob.error} /> : doc.content_type === "application/pdf" ? (
          <iframe src={blob.data} title="Document preview" className="h-full min-h-[60vh] w-full" />
        ) : doc.content_type === "image/tiff" ? (
          <div className="p-6 text-center text-[13px] text-muted-foreground">TIFF preview isn't supported by browsers. <a className="text-primary underline" href={blob.data} download>Download</a> to view.</div>
        ) : (
          <img src={blob.data} alt="Uploaded document" className="mx-auto max-h-full object-contain p-4" />
        )}
      </div>
    </Card>
  );
}

const norm = (s?: string | null) => (s ?? "").trim().toLowerCase();

function IdentityCompare({ doc, patient }: { doc: DocumentDetail; patient: PatientPick }) {
  const id = doc.ai_output?.patient;
  const docName = [id?.first_name, id?.last_name].filter(Boolean).join(" ");
  const nameOk = !!id?.last_name && norm(patient.name).includes(norm(id.last_name));
  const dobOk = !!id?.date_of_birth && id.date_of_birth === patient.date_of_birth;
  const mrnOk = !id?.mrn || id.mrn === patient.mrn;
  const row = (label: string, onDoc: string | null | undefined, inChart: string, ok: boolean, unknown: boolean) => (
    <tr className="border-b last:border-0">
      <td className="py-1.5 pr-3 text-xs text-muted-foreground">{label}</td>
      <td className="py-1.5 pr-3 font-medium">{onDoc || <span className="text-muted-foreground">not found</span>}</td>
      <td className="py-1.5 pr-3">{inChart}</td>
      <td className="py-1.5">{unknown ? <AlertTriangle className="size-4 text-warning" aria-label="Not verifiable" /> : ok ? <CheckCircle2 className="size-4 text-success" aria-label="Matches" /> : <XCircle className="size-4 text-destructive" aria-label="Mismatch" />}</td>
    </tr>
  );
  return (
    <table className="w-full text-[13px]">
      <thead><tr className="text-left text-[11px] uppercase tracking-wide text-muted-foreground"><th className="pb-1 font-semibold">Field</th><th className="pb-1 font-semibold">On document</th><th className="pb-1 font-semibold">Selected patient</th><th /></tr></thead>
      <tbody>
        {row("Name", docName, patient.name, nameOk, !id?.last_name)}
        {row("DOB", id?.date_of_birth ? fmtDate(id.date_of_birth) : null, fmtDate(patient.date_of_birth), dobOk, !id?.date_of_birth)}
        {row("MRN", id?.mrn, patient.mrn, mrnOk, !id?.mrn)}
      </tbody>
    </table>
  );
}

export function DocumentReview() {
  const { documentId = "" } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { confirm, dialog } = useConfirm();
  const q = useQuery({
    queryKey: ["document", documentId], queryFn: () => get<DocumentDetail>(`/documents/${documentId}`),
    refetchInterval: (query) => (query.state.data?.status === "processing" ? 2000 : false),
  });
  const doc = q.data;
  useCrumb(doc ? doc.title ?? doc.filename : null);
  const [docType, setDocType] = React.useState("other");
  const [title, setTitle] = React.useState("");
  const [docDate, setDocDate] = React.useState("");
  const [summary, setSummary] = React.useState("");
  const [patient, setPatient] = React.useState<PatientPick | null>(null);
  const [searching, setSearching] = React.useState(false);
  const [confirmed, setConfirmed] = React.useState(false);
  const [busy, setBusy] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!doc || doc.status === "processing") return;
    setDocType(doc.doc_type ?? "other");
    setTitle(doc.title ?? "");
    setDocDate(doc.document_date ?? "");
    setSummary(doc.summary ?? "");
    const pid = doc.patient_id ?? doc.suggested_patient_id;
    const c = doc.match_candidates?.find((x) => x.patient_id === pid);
    setPatient(c ? { id: c.patient_id, name: c.name, mrn: c.mrn, date_of_birth: c.date_of_birth } : doc.patient_id && doc.patient_name ? { id: doc.patient_id, name: doc.patient_name, mrn: "", date_of_birth: "" } : null);
    setConfirmed(false);
  }, [doc?.id, doc?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["document", documentId] });
    qc.invalidateQueries({ queryKey: ["documents"] });
    qc.invalidateQueries({ queryKey: ["doc-counts"] });
  };

  if (q.error) return <ErrorState error={q.error} retry={q.refetch} />;
  if (!doc) return <div className="grid gap-4 lg:grid-cols-2"><Skeleton className="h-[70vh] rounded-xl" /><LoadingRows rows={8} /></div>;
  const ai = doc.ai_output;
  const reviewable = doc.status === "needs_review" && can("documents:review");
  const pickCandidate = (c: Candidate) => { setPatient({ id: c.patient_id, name: c.name, mrn: c.mrn, date_of_birth: c.date_of_birth }); setConfirmed(false); setSearching(false); };

  const fileIt = async () => {
    if (!patient) return;
    setBusy("file");
    try {
      await post(`/documents/${doc.id}/file`, { patient_id: patient.id, doc_type: docType, title, document_date: docDate || null, summary, identity_confirmed: confirmed });
      toast.success(`Filed to ${patient.name}'s chart`, { action: { label: "Open chart", onClick: () => navigate(`/patients/${patient.id}/documents`) } });
      refresh();
      const next = await get<{ items: { id: string }[] }>("/documents", { status: "needs_review", page_size: 1 });
      if (next.items[0]) navigate(`/documents/${next.items[0].id}`);
    } catch (e) { toastError(e); } finally { setBusy(null); }
  };

  return (
    <>
      {dialog}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold tracking-tight">{doc.title ?? doc.filename}</h1>
        <DocStatusBadge status={doc.status} />
        <Badge variant="outline">{sourceLabel(doc.source)}</Badge>
        <span className="text-[13px] text-muted-foreground">Received {fmtDateTime(doc.created_at)}{doc.uploaded_by_name ? ` · by ${doc.uploaded_by_name}` : ""}{doc.sender ? ` · from ${doc.sender}` : ""}</span>
      </div>
      {doc.duplicate_of && (
        <div role="alert" className="mb-4 flex items-center gap-2 rounded-lg border border-warning/40 bg-warning-soft px-3 py-2 text-[13px]">
          <AlertTriangle className="size-4 text-warning" />An identical file was already received. <Link className="font-medium text-primary underline" to={`/documents/${doc.duplicate_of}`}>Open the other copy</Link>
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <Preview doc={doc} />
        <div className="space-y-4">
          {doc.status === "processing" ? (
            <Card><CardContent className="flex items-center gap-3 py-10 text-[13.5px]"><Loader2 className="size-5 animate-spin text-ai" />Extracting text, classifying and matching to a patient…</CardContent></Card>
          ) : doc.status === "failed" ? (
            <Card className="border-destructive/30">
              <CardContent className="space-y-3 pt-5">
                <p className="flex items-center gap-2 font-medium text-destructive"><XCircle className="size-4" />Processing failed</p>
                <p className="text-[13px]">{doc.processing_error}</p>
                {can("documents:write") && <Button size="sm" variant="outline" loading={busy === "re"} onClick={async () => { setBusy("re"); try { await post(`/documents/${doc.id}/reprocess`); refresh(); } catch (e) { toastError(e); } finally { setBusy(null); } }}><RefreshCw />Reprocess</Button>}
              </CardContent>
            </Card>
          ) : (
            <>
              {ai && (
                <Card className="border-ai/25">
                  <CardHeader className="pb-2">
                    <div className="flex flex-wrap items-center gap-2"><CardTitle>AI extraction</CardTitle><AIBadge label="AI draft — verify" />{doc.ai_provider === "simulated" && <SimulatedBadge label="Rule-based simulation" />}</div>
                    <ConfidenceMeter value={doc.ai_confidence} />
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {ai.uncertainties.length > 0 && (
                      <ul className="space-y-1 rounded-lg bg-warning-soft px-3 py-2 text-[12.5px]">
                        {ai.uncertainties.map((u, i) => <li key={i} className="flex gap-1.5"><AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" />{u}</li>)}
                      </ul>
                    )}
                    {ai.key_findings.length > 0 && (
                      <div>
                        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Results on document</p>
                        <table className="w-full text-[13px]">
                          <tbody>
                            {ai.key_findings.map((f, i) => (
                              <tr key={i} className="border-b last:border-0">
                                <td className="py-1 pr-2">{f.label}</td>
                                <td className={cn("py-1 pr-2 font-medium tabular", f.flag === "abnormal" && "text-destructive")}>{f.value}{f.flag === "abnormal" && " ⚑"}</td>
                                <td className="py-1 text-xs text-muted-foreground">{f.reference_range ? `ref ${f.reference_range}` : ""}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {(ai.medications.length > 0 || ai.diagnoses_stated.length > 0) && (
                      <dl className="grid gap-3 sm:grid-cols-2">
                        {ai.medications.length > 0 && <KeyValue label="Medications mentioned" value={<ul className="whitespace-normal">{ai.medications.map((m) => <li key={m}>{m}</li>)}</ul>} />}
                        {ai.diagnoses_stated.length > 0 && <KeyValue label="Diagnoses stated" value={<ul className="whitespace-normal">{ai.diagnoses_stated.map((m) => <li key={m}>{m}</li>)}</ul>} />}
                      </dl>
                    )}
                    <p className="text-[11.5px] text-muted-foreground">Extracted values are not added to structured chart data automatically.</p>
                  </CardContent>
                </Card>
              )}

              <Card>
                <CardHeader className="pb-2"><CardTitle>Document details</CardTitle></CardHeader>
                <CardContent className="grid gap-3 sm:grid-cols-2">
                  <Field label="Type"><NativeSelect value={docType} onChange={(e) => setDocType(e.target.value)} disabled={!reviewable}>{DOC_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</NativeSelect></Field>
                  <Field label="Document date"><Input type="date" value={docDate} onChange={(e) => setDocDate(e.target.value)} readOnly={!reviewable} /></Field>
                  <Field label="Title" className="sm:col-span-2"><Input value={title} onChange={(e) => setTitle(e.target.value)} readOnly={!reviewable} /></Field>
                  <Field label="Summary" className="sm:col-span-2" hint={reviewable ? "Edit as needed — this is what clinicians see in the chart." : undefined}>
                    <Textarea rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} readOnly={!reviewable} />
                  </Field>
                </CardContent>
              </Card>

              {doc.status === "filed" ? (
                <Card className="border-success/30">
                  <CardContent className="flex flex-wrap items-center gap-3 pt-5 text-[13.5px]">
                    <FileCheck2 className="size-5 text-success" />Filed to <Link to={`/patients/${doc.patient_id}/documents`} className="font-medium text-primary hover:underline">{doc.patient_name}</Link>
                    <span className="text-muted-foreground">· {fmtDateTime(doc.reviewed_at)}</span>
                  </CardContent>
                </Card>
              ) : doc.status === "rejected" ? (
                <Card><CardContent className="pt-5 text-[13.5px]">Rejected: {doc.reject_reason}</CardContent></Card>
              ) : (
                <Card>
                  <CardHeader className="pb-2"><CardTitle>Patient</CardTitle>
                    {reviewable && <Button size="xs" variant="ghost" onClick={() => setSearching((s) => !s)}><UserSearch />{searching ? "Cancel search" : "Search other patient"}</Button>}
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {!doc.suggested_patient_id && !patient && (
                      <p className="flex items-start gap-1.5 text-[13px] text-warning"><AlertTriangle className="mt-0.5 size-4 shrink-0" />No confident match. Choose a candidate or search — don't guess.</p>
                    )}
                    {!!doc.match_candidates?.length && (
                      <ul className="space-y-1.5" aria-label="Match candidates">
                        {doc.match_candidates.map((c) => (
                          <li key={c.patient_id}>
                            <button disabled={!reviewable} onClick={() => pickCandidate(c)}
                              className={cn("flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left hover:bg-muted/50 disabled:cursor-default", patient?.id === c.patient_id && "border-primary bg-accent/40")}>
                              <span className={cn("size-3.5 shrink-0 rounded-full border-2", patient?.id === c.patient_id ? "border-primary bg-primary" : "border-input")} aria-hidden />
                              <span className="min-w-0 flex-1">
                                <span className="block text-[13.5px] font-medium">{c.name}{doc.suggested_patient_id === c.patient_id && <Badge variant="info" className="ml-2">Suggested</Badge>}</span>
                                <span className="block text-xs text-muted-foreground tabular">DOB {fmtDob(c.date_of_birth)} · MRN {c.mrn}</span>
                                <span className="block text-[11.5px] text-muted-foreground">{c.reasons.join(" · ")}</span>
                              </span>
                              <ConfidenceMeter value={c.score} label={false} />
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                    {searching && <PatientPicker value={null} onChange={(p) => { if (p) { setPatient(p); setConfirmed(false); setSearching(false); } }} />}
                    {patient && patient.date_of_birth && (
                      <div className="rounded-lg border p-3">
                        <IdentityCompare doc={doc} patient={patient} />
                      </div>
                    )}
                    {reviewable && patient && (
                      <label className="flex items-start gap-2 rounded-lg border border-primary/30 bg-accent/30 p-3 text-[13px]">
                        <Checkbox checked={confirmed} onCheckedChange={(c) => setConfirmed(!!c)} className="mt-0.5" />
                        <span>I verified the name and date of birth on the document belong to <strong>{patient.name}</strong>.</span>
                      </label>
                    )}
                    {reviewable && (
                      <div className="flex flex-wrap gap-2 pt-1">
                        <Button onClick={fileIt} loading={busy === "file"} disabled={!patient || !confirmed || !title.trim()}><FileCheck2 />File to chart</Button>
                        <Button variant="outline" onClick={async () => {
                          const reason = await confirm({ title: "Reject this document?", description: "It won't be filed to any chart. The file is kept for audit.", requireReason: true, reasonLabel: "Reason (e.g. wrong practice, duplicate, blank)", destructive: true, confirmLabel: "Reject" });
                          if (!reason) return;
                          try { await post(`/documents/${doc.id}/reject`, { reason }); toast.success("Document rejected"); refresh(); } catch (e) { toastError(e); }
                        }}><XCircle />Reject</Button>
                        <Button variant="ghost" loading={busy === "re"} onClick={async () => { setBusy("re"); try { await post(`/documents/${doc.id}/reprocess`); refresh(); } catch (e) { toastError(e); } finally { setBusy(null); } }}><RefreshCw />Reprocess</Button>
                      </div>
                    )}
                    {!can("documents:review") && <p className="text-xs text-muted-foreground">A nurse or clinician must confirm and file this document.</p>}
                  </CardContent>
                </Card>
              )}
              {doc.extracted_text && (
                <details className="rounded-xl border bg-card p-3">
                  <summary className="cursor-pointer text-[13px] font-medium">Extracted text ({doc.text_source === "pdf_text" ? "PDF text layer" : doc.text_source})</summary>
                  <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap font-mono text-xs text-muted-foreground">{doc.extracted_text}</pre>
                </details>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}

export function PatientDocumentsTab({ patientId }: { patientId: string }) {
  const navigate = useNavigate();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["patient-docs", patientId], queryFn: () => get<DocumentRow[]>(`/patients/${patientId}/documents`) });
  return (
    <div className="space-y-4">
      {can("documents:write") && <UploadZone patientId={patientId} compact />}
      <Card className="overflow-hidden">
        {q.isLoading ? <LoadingRows rows={3} /> : !q.data?.length ? (
          <p className="p-6 text-center text-[13px] text-muted-foreground">No filed documents. Uploads from here still go through review before they appear.</p>
        ) : (
          <ul className="divide-y">
            {q.data.map((d) => (
              <li key={d.id}>
                <button onClick={() => navigate(`/documents/${d.id}`)} className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-muted/40">
                  <FileCheck2 className="mt-0.5 size-4 text-muted-foreground" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13.5px] font-medium">{d.title}</span>
                    <span className="block text-xs text-muted-foreground">{docTypeLabel(d.doc_type)} · {fmtDate(d.document_date ?? d.created_at)} · {sourceLabel(d.source)}</span>
                    {d.summary && <span className="mt-0.5 block text-[12.5px] text-muted-foreground">{d.summary}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
