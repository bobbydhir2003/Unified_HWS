import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { api, post } from "@/lib/api";
import { cn, titleCase } from "@/lib/utils";

export type DocStatus = "processing" | "needs_review" | "filed" | "rejected" | "failed";

export type DocumentRow = {
  id: string; source: string; status: DocStatus; filename: string; content_type: string; size_bytes: number;
  page_count: number | null; sender: string | null; patient_id: string | null; patient_name: string | null;
  doc_type: string | null; title: string | null; document_date: string | null; summary: string | null;
  ai_confidence: number | null; suggested_patient_id: string | null; processing_error: string | null;
  uploaded_by_name: string | null; reviewed_at: string | null; reject_reason: string | null; created_at: string;
};

export type Candidate = { patient_id: string; name: string; mrn: string; date_of_birth: string; score: number; reasons: string[] };

export type DocumentDetail = DocumentRow & {
  ai_output: null | {
    doc_type: string; title: string; document_date: string | null; sender: string | null; summary: string;
    patient: { first_name: string | null; last_name: string | null; date_of_birth: string | null; mrn: string | null };
    key_findings: { label: string; value: string; flag: "normal" | "abnormal" | "unknown"; reference_range: string | null }[];
    medications: string[]; diagnoses_stated: string[]; confidence: number; uncertainties: string[];
  };
  match_candidates: Candidate[] | null;
  text_source: string | null;
  extracted_text: string | null;
  ai_provider: string | null;
  ai_model: string | null;
  duplicate_of: string | null;
};

export const DOC_TYPES: [string, string][] = [
  ["lab_result", "Lab result"], ["imaging_report", "Imaging report"], ["referral", "Referral"], ["consult_note", "Consult note"],
  ["discharge_summary", "Discharge summary"], ["insurance_card", "Insurance card"], ["id_card", "ID card"],
  ["prescription", "Prescription"], ["intake_form", "Intake form"], ["correspondence", "Correspondence"], ["other", "Other"],
];
export const docTypeLabel = (t: string | null) => DOC_TYPES.find(([k]) => k === t)?.[1] ?? "Unclassified";

const STATUS: Record<DocStatus, { label: string; variant: React.ComponentProps<typeof Badge>["variant"] }> = {
  processing: { label: "Processing", variant: "info" },
  needs_review: { label: "Needs review", variant: "warning" },
  filed: { label: "Filed", variant: "success" },
  rejected: { label: "Rejected", variant: "neutral" },
  failed: { label: "Failed", variant: "danger" },
};

export function DocStatusBadge({ status }: { status: DocStatus }) {
  const s = STATUS[status];
  return <Badge variant={s.variant}>{status === "processing" && <Loader2 className="animate-spin" />}{s.label}</Badge>;
}

export function ConfidenceMeter({ value, className, label = true }: { value: number | null | undefined; className?: string; label?: boolean }) {
  if (value === null || value === undefined) return <span className="text-xs text-muted-foreground">—</span>;
  const pct = Math.round(value * 100);
  const tone = value >= 0.85 ? "bg-success" : value >= 0.6 ? "bg-warning" : "bg-destructive";
  const word = value >= 0.85 ? "High" : value >= 0.6 ? "Medium" : "Low";
  return (
    <span className={cn("inline-flex items-center gap-2", className)} title={`${pct}% confidence`}>
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-muted" aria-hidden><span className={cn("block h-full rounded-full", tone)} style={{ width: `${pct}%` }} /></span>
      {label && <span className="text-xs tabular text-muted-foreground">{word} · {pct}%</span>}
    </span>
  );
}

export function sourceLabel(s: string) {
  return { upload: "Upload", scan: "Scan", fax: "Fax", portal: "Portal", sample: "Synthetic sample" }[s] ?? titleCase(s);
}

/** Fetch a protected file with auth headers and expose it as an object URL. */
export function useDocumentBlob(id: string | undefined, enabled = true) {
  const q = useQuery({
    queryKey: ["doc-blob", id],
    queryFn: async () => {
      const res = await api<Response>(`/documents/${id}/file`, { raw: true });
      if (!res.ok) throw new Error("Couldn't load the file");
      return URL.createObjectURL(await res.blob());
    },
    enabled: !!id && enabled,
    staleTime: Infinity,
    gcTime: 60_000,
  });
  React.useEffect(() => () => { if (q.data) URL.revokeObjectURL(q.data); }, [q.data]);
  return q;
}

export async function uploadDocuments(files: File[], patientId?: string) {
  const results: { ok: number; failed: string[] } = { ok: 0, failed: [] };
  for (const f of files) {
    const fd = new FormData();
    fd.append("file", f);
    if (patientId) fd.append("patient_id", patientId);
    try { await api("/documents", { method: "POST", body: fd }); results.ok++; }
    catch (e) { results.failed.push(`${f.name}: ${e instanceof Error ? e.message : "failed"}`); }
  }
  return results;
}

export const createSample = (body: { kind: string; fidelity: string; source: "sample" | "fax"; patient_id?: string }) =>
  post<DocumentDetail>("/documents/samples", body);
