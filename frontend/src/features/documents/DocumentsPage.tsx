import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, FileStack, FlaskConical, Printer, Search, Upload } from "lucide-react";
import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { EmptyState, ErrorState, LoadingRows, PageHeader, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/menu";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime } from "@/lib/format";
import type { Page } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ConfidenceMeter, createSample, DocStatusBadge, type DocumentRow, docTypeLabel, sourceLabel, uploadDocuments } from "./shared";

const TABS: [string, string][] = [["needs_review", "Needs review"], ["processing", "Processing"], ["failed", "Failed"], ["filed", "Filed"], ["rejected", "Rejected"], ["", "All"]];

export function UploadZone({ patientId, onDone, compact }: { patientId?: string; onDone?: () => void; compact?: boolean }) {
  const qc = useQueryClient();
  const input = React.useRef<HTMLInputElement>(null);
  const [drag, setDrag] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const handle = async (files: File[]) => {
    if (!files.length) return;
    setBusy(true);
    const r = await uploadDocuments(files, patientId);
    setBusy(false);
    if (r.ok) toast.success(`${r.ok} document${r.ok > 1 ? "s" : ""} uploaded — processing for review`);
    r.failed.forEach((f) => toast.error(f));
    qc.invalidateQueries({ queryKey: ["documents"] });
    qc.invalidateQueries({ queryKey: ["doc-counts"] });
    onDone?.();
  };
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); handle(Array.from(e.dataTransfer.files)); }}
      className={cn("flex items-center gap-3 rounded-xl border-2 border-dashed bg-card px-4 transition-colors", compact ? "py-3" : "py-5", drag && "border-primary bg-accent/40")}
    >
      <span className="rounded-lg bg-accent p-2 text-accent-foreground"><Upload className="size-4" /></span>
      <div className="min-w-0 flex-1">
        <p className="text-[13.5px] font-medium">Drop PDFs or images here</p>
        <p className="text-xs text-muted-foreground">PDF, PNG, JPEG, TIFF, WebP · up to 25 MB · every document is reviewed before it's filed</p>
      </div>
      <input ref={input} type="file" multiple hidden accept="application/pdf,image/png,image/jpeg,image/tiff,image/webp"
        onChange={(e) => { handle(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
      <Button variant="outline" size="sm" loading={busy} onClick={() => input.current?.click()}>Choose files</Button>
    </div>
  );
}

export function DocumentsPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { can } = useAuth();
  const status = params.get("status") ?? "needs_review";
  const page = Number(params.get("page") ?? 1);
  const [q, setQ] = React.useState("");
  const [dq, setDq] = React.useState("");
  React.useEffect(() => { const t = setTimeout(() => setDq(q), 250); return () => clearTimeout(t); }, [q]);
  const counts = useQuery({ queryKey: ["doc-counts"], queryFn: () => get<Record<string, number>>("/documents/counts"), refetchInterval: 10_000 });
  const list = useQuery({
    queryKey: ["documents", status, dq, page],
    queryFn: () => get<Page<DocumentRow>>("/documents", { status, q: dq, page, page_size: 25 }),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (query.state.data?.items.some((d) => d.status === "processing") ? 2500 : 15_000),
  });
  const set = (k: string, v: string | null) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); if (k !== "page") n.delete("page"); setParams(n); };
  const sample = async (kind: string, fidelity: string, source: "sample" | "fax") => {
    try {
      const d = await createSample({ kind, fidelity, source });
      toast.success(source === "fax" ? "Simulated fax received" : "Synthetic sample created", { action: { label: "Review", onClick: () => navigate(`/documents/${d.id}`) } });
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["doc-counts"] });
    } catch (e) { toastError(e); }
  };
  const data = list.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <PageHeader title="Document center" description="Incoming faxes, scans and uploads. AI drafts the classification and patient match; staff confirm before anything reaches a chart."
        actions={can("documents:write") && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="outline"><FlaskConical />Synthetic test data</Button></DropdownMenuTrigger>
            <DropdownMenuContent className="w-64">
              <DropdownMenuLabel>Simulate inbound fax</DropdownMenuLabel>
              <DropdownMenuItem onSelect={() => sample("referral", "exact", "fax")}><Printer />Referral (clear match)</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => sample("discharge_summary", "ambiguous", "fax")}><Printer />Discharge summary (ambiguous ID)</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>Generate sample document</DropdownMenuLabel>
              <DropdownMenuItem onSelect={() => sample("lab_result", "exact", "sample")}><FileStack />Lab report (clear match)</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => sample("imaging_report", "ambiguous", "sample")}><FileStack />Imaging report (ambiguous ID)</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => sample("lab_result", "unknown", "sample")}><FileStack />Lab report (unknown patient)</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )} />
      {can("documents:write") && <div className="mb-4"><UploadZone /></div>}
      <Card className="overflow-hidden">
        <div className="flex flex-col gap-2 border-b p-3 lg:flex-row lg:items-center">
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="Document status">
            {TABS.map(([k, label]) => {
              const n = k ? counts.data?.[k] : undefined;
              return (
                <button key={k || "all"} role="tab" aria-selected={status === k} onClick={() => set("status", k || "")}
                  className={cn("flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium text-muted-foreground hover:bg-muted", status === k && "bg-accent text-accent-foreground")}>
                  {label}{!!n && <span className={cn("rounded-full px-1.5 text-[11px] tabular", k === "needs_review" ? "bg-warning text-white" : k === "failed" ? "bg-destructive text-white" : "bg-muted")}>{n}</span>}
                </button>
              );
            })}
          </div>
          <div className="relative lg:ml-auto lg:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, summary, patient" className="pl-9" aria-label="Search documents" />
          </div>
        </div>
        {list.error ? <ErrorState error={list.error} retry={list.refetch} /> : list.isLoading ? <LoadingRows rows={6} /> : !data?.items.length ? (
          <EmptyState icon={FileStack} title={status === "needs_review" ? "Review queue is empty" : "No documents"} description={status === "needs_review" ? "New uploads and faxes will appear here after processing." : undefined} />
        ) : (
          <Table>
            <THead><TR><TH>Received</TH><TH>Document</TH><TH className="hidden md:table-cell">Source</TH><TH>Patient</TH><TH className="hidden lg:table-cell">AI confidence</TH><TH>Status</TH></TR></THead>
            <TBody>
              {data.items.map((d) => (
                <TR key={d.id} data-clickable tabIndex={0} onClick={() => navigate(`/documents/${d.id}`)} onKeyDown={(e) => e.key === "Enter" && navigate(`/documents/${d.id}`)}>
                  <TD className="whitespace-nowrap text-muted-foreground">{fmtDateTime(d.created_at)}</TD>
                  <TD>
                    <span className="font-medium">{d.title ?? d.filename}</span>
                    <span className="block text-xs text-muted-foreground">{docTypeLabel(d.doc_type)}{d.document_date ? ` · ${fmtDate(d.document_date)}` : ""}{d.page_count ? ` · ${d.page_count} p` : ""}</span>
                  </TD>
                  <TD className="hidden md:table-cell"><Badge variant="outline">{sourceLabel(d.source)}</Badge>{d.sender && <span className="block max-w-48 truncate text-xs text-muted-foreground">{d.sender}</span>}</TD>
                  <TD>
                    {d.patient_name ? <span className="font-medium">{d.patient_name}</span>
                      : d.status === "needs_review" ? (d.suggested_patient_id ? <Badge variant="info">Suggested match</Badge> : <Badge variant="warning">Needs patient</Badge>)
                        : <span className="text-muted-foreground">—</span>}
                  </TD>
                  <TD className="hidden lg:table-cell"><ConfidenceMeter value={d.ai_confidence} /></TD>
                  <TD><DocStatusBadge status={d.status} />{d.processing_error && <span className="block max-w-56 truncate text-xs text-destructive">{d.processing_error}</span>}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
        {data && data.total > data.page_size && (
          <div className="flex items-center justify-between border-t px-4 py-2.5 text-[13px] text-muted-foreground">
            <span>{data.total} documents</span>
            <div className="flex gap-1">
              <Button variant="outline" size="icon-sm" disabled={page <= 1} onClick={() => set("page", String(page - 1))} aria-label="Previous page"><ChevronLeft /></Button>
              <Button variant="outline" size="icon-sm" disabled={page >= pages} onClick={() => set("page", String(page + 1))} aria-label="Next page"><ChevronRight /></Button>
            </div>
          </div>
        )}
      </Card>
    </>
  );
}
