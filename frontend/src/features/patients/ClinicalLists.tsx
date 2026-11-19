import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState, LoadingRows, toastError, useConfirm } from "@/components/common";
import { type FieldSpec, FormDialog } from "@/components/common/FormDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/menu";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { del, get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import type { Allergy, HistoryEntry, Medication, Problem } from "@/lib/types";
import { titleCase } from "@/lib/utils";

type Row = { id: string; status?: string } & Record<string, unknown>;

type ListConfig<T extends Row> = {
  path: "problems" | "medications" | "allergies" | "history";
  noun: string;
  fields: FieldSpec[];
  columns: { header: string; cell: (r: T) => React.ReactNode; className?: string }[];
  toForm?: (r: T) => Record<string, string | boolean | null>;
  emptyText: string;
};

export const SEVERITY_VARIANT = { mild: "neutral", moderate: "warning", severe: "danger", life_threatening: "danger" } as const;

function ClinicalList<T extends Row>({ patientId, cfg }: { patientId: string; cfg: ListConfig<T> }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const { confirm, dialog } = useConfirm();
  const [editing, setEditing] = React.useState<T | "new" | null>(null);
  const [showInactive, setShowInactive] = React.useState(false);
  const q = useQuery({ queryKey: [cfg.path, patientId], queryFn: () => get<T[]>(`/patients/${patientId}/${cfg.path}`) });
  const rows = (q.data ?? []).filter((r) => showInactive || !r.status || r.status === "active");
  const inactiveCount = (q.data ?? []).filter((r) => r.status && r.status !== "active").length;
  const writable = can("clinical:write");
  const refresh = () => {
    qc.invalidateQueries({ queryKey: [cfg.path, patientId] });
    qc.invalidateQueries({ queryKey: ["summary", patientId] });
    qc.invalidateQueries({ queryKey: ["timeline", patientId] });
  };

  const markError = async (r: T) => {
    const ok = await confirm({ title: `Mark this ${cfg.noun} as entered in error?`, description: "It will be hidden from the chart but kept in the audit history.", confirmLabel: "Mark as error", destructive: true });
    if (!ok) return;
    try {
      await put(`/${cfg.path}/${r.id}`, { ...(cfg.toForm ? cfg.toForm(r) : r), status: "entered_in_error" });
      refresh();
      toast.success("Marked as entered in error");
    } catch (e) { toastError(e); }
  };

  return (
    <>
      {dialog}
      <div className="mb-3 flex items-center justify-between gap-2">
        {inactiveCount > 0 ? (
          <Button variant="ghost" size="sm" onClick={() => setShowInactive((s) => !s)}>
            {showInactive ? "Hide" : "Show"} inactive ({inactiveCount})
          </Button>
        ) : <span />}
        {writable && <Button size="sm" onClick={() => setEditing("new")}><Plus />Add {cfg.noun}</Button>}
      </div>
      <Card className="overflow-hidden">
        {q.error ? <ErrorState error={q.error} retry={q.refetch} /> : q.isLoading ? <LoadingRows rows={3} /> : !rows.length ? (
          <EmptyState title={cfg.emptyText} action={writable && <Button variant="outline" size="sm" onClick={() => setEditing("new")}><Plus />Add {cfg.noun}</Button>} />
        ) : (
          <Table>
            <THead><TR>{cfg.columns.map((c) => <TH key={c.header} className={c.className}>{c.header}</TH>)}{writable && <TH className="w-10" />}</TR></THead>
            <TBody>
              {rows.map((r) => (
                <TR key={r.id} className={r.status && r.status !== "active" ? "opacity-60" : ""}>
                  {cfg.columns.map((c) => <TD key={c.header} className={c.className}>{c.cell(r)}</TD>)}
                  {writable && (
                    <TD>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="Actions"><MoreHorizontal /></Button></DropdownMenuTrigger>
                        <DropdownMenuContent>
                          <DropdownMenuItem onSelect={() => setEditing(r)}><Pencil />Edit</DropdownMenuItem>
                          {cfg.path === "history" ? (
                            <DropdownMenuItem destructive onSelect={async () => {
                              if (await confirm({ title: "Remove this history entry?", confirmLabel: "Remove", destructive: true })) {
                                try { await del(`/history/${r.id}`); refresh(); } catch (e) { toastError(e); }
                              }
                            }}><Trash2 />Remove</DropdownMenuItem>
                          ) : (
                            <DropdownMenuItem destructive onSelect={() => markError(r)}><Trash2 />Entered in error</DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TD>
                  )}
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
      <FormDialog
        open={!!editing} onOpenChange={(o) => !o && setEditing(null)}
        title={editing === "new" ? `Add ${cfg.noun}` : `Edit ${cfg.noun}`}
        fields={cfg.fields}
        initial={editing && editing !== "new" ? (cfg.toForm ? cfg.toForm(editing) : (editing as Record<string, string>)) : undefined}
        onSubmit={async (v) => {
          if (editing === "new") await post(`/patients/${patientId}/${cfg.path}`, v);
          else if (editing) await put(`/${cfg.path}/${editing.id}`, v);
          refresh();
          toast.success(`${titleCase(cfg.noun)} saved`);
        }}
      />
    </>
  );
}

const statusOpts = (...s: string[]): [string, string][] => s.map((x) => [x, titleCase(x)]);

export function ProblemsTab({ patientId }: { patientId: string }) {
  return <ClinicalList<Problem & Row> patientId={patientId} cfg={{
    path: "problems", noun: "problem", emptyText: "No problems recorded",
    fields: [
      { name: "code", label: "ICD-10 code", type: "icd10", hint: "Pick a code to fill the description" },
      { name: "description", label: "Description", required: true },
      { name: "status", label: "Status", type: "select", options: statusOpts("active", "resolved", "inactive"), span: 1 },
      { name: "onset_date", label: "Onset date", type: "date", span: 1 },
      { name: "is_chronic", label: "Chronic condition", type: "checkbox" },
    ],
    toForm: (r) => ({ code: r.code, description: r.description, status: r.status, onset_date: r.onset_date, is_chronic: r.is_chronic, resolved_date: r.resolved_date }),
    columns: [
      { header: "Problem", cell: (r) => <span className="font-medium">{r.description}</span> },
      { header: "ICD-10", cell: (r) => <span className="font-mono text-xs">{r.code ?? "—"}</span> },
      { header: "Status", cell: (r) => <div className="flex gap-1"><Badge variant={r.status === "active" ? "primary" : "neutral"}>{titleCase(r.status)}</Badge>{r.is_chronic && <Badge variant="outline">Chronic</Badge>}</div> },
      { header: "Onset", cell: (r) => fmtDate(r.onset_date), className: "hidden sm:table-cell text-muted-foreground" },
    ],
  }} />;
}

export function MedicationsTab({ patientId }: { patientId: string }) {
  return (
    <>
      <p className="mb-3 text-[13px] text-muted-foreground">Medication list (what the patient reports taking). Prescribing arrives with clinical orders.</p>
      <ClinicalList<Medication & Row> patientId={patientId} cfg={{
        path: "medications", noun: "medication", emptyText: "No medications recorded",
        fields: [
          { name: "name", label: "Medication", required: true, placeholder: "e.g. Lisinopril" },
          { name: "dose", label: "Dose", span: 1, placeholder: "10 mg" },
          { name: "route", label: "Route", span: 1, placeholder: "oral" },
          { name: "frequency", label: "Frequency", span: 1, placeholder: "once daily" },
          { name: "indication", label: "Indication", span: 1 },
          { name: "status", label: "Status", type: "select", options: statusOpts("active", "completed", "discontinued"), span: 1 },
          { name: "start_date", label: "Start date", type: "date", span: 1 },
        ],
        toForm: (r) => ({ name: r.name, dose: r.dose, route: r.route, frequency: r.frequency, indication: r.indication, status: r.status, start_date: r.start_date, end_date: r.end_date }),
        columns: [
          { header: "Medication", cell: (r) => <div><span className="font-medium">{r.name}</span> <span className="text-muted-foreground">{r.dose}</span></div> },
          { header: "Sig", cell: (r) => [r.route, r.frequency].filter(Boolean).join(", ") || "—" },
          { header: "Indication", cell: (r) => r.indication ?? "—", className: "hidden md:table-cell" },
          { header: "Status", cell: (r) => <Badge variant={r.status === "active" ? "success" : "neutral"}>{titleCase(r.status)}</Badge> },
        ],
      }} />
    </>
  );
}

export function AllergiesTab({ patientId }: { patientId: string }) {
  return <ClinicalList<Allergy & Row> patientId={patientId} cfg={{
    path: "allergies", noun: "allergy", emptyText: "No known allergies recorded",
    fields: [
      { name: "substance", label: "Substance", required: true },
      { name: "category", label: "Category", type: "select", options: statusOpts("medication", "food", "environmental", "other"), span: 1 },
      { name: "severity", label: "Severity", type: "select", options: [["moderate", "Moderate"], ["mild", "Mild"], ["severe", "Severe"], ["life_threatening", "Life-threatening"]], span: 1 },
      { name: "reaction", label: "Reaction" },
      { name: "status", label: "Status", type: "select", options: statusOpts("active", "inactive"), span: 1 },
      { name: "onset_date", label: "Onset", type: "date", span: 1 },
    ],
    toForm: (r) => ({ substance: r.substance, category: r.category, severity: r.severity, reaction: r.reaction, status: r.status, onset_date: r.onset_date }),
    columns: [
      { header: "Substance", cell: (r) => <span className="font-medium">{r.substance}</span> },
      { header: "Reaction", cell: (r) => r.reaction ?? "—" },
      { header: "Severity", cell: (r) => <Badge variant={SEVERITY_VARIANT[r.severity]}>{titleCase(r.severity)}</Badge> },
      { header: "Category", cell: (r) => titleCase(r.category), className: "hidden sm:table-cell text-muted-foreground" },
    ],
  }} />;
}

export function HistoryTab({ patientId }: { patientId: string }) {
  return <ClinicalList<HistoryEntry & Row> patientId={patientId} cfg={{
    path: "history", noun: "history entry", emptyText: "No history recorded",
    fields: [
      { name: "category", label: "Type", type: "select", options: statusOpts("medical", "surgical", "family", "social"), span: 1 },
      { name: "relation", label: "Relation (family only)", span: 1 },
      { name: "condition", label: "Condition / description", required: true },
      { name: "occurred_on", label: "When", placeholder: "e.g. 2015, childhood", span: 1 },
      { name: "details", label: "Details", type: "textarea" },
    ],
    toForm: (r) => ({ category: r.category, relation: r.relation, condition: r.condition, occurred_on: r.occurred_on, details: r.details }),
    columns: [
      { header: "Type", cell: (r) => <Badge variant="outline">{titleCase(r.category)}</Badge> },
      { header: "Condition", cell: (r) => <div><span className="font-medium">{r.condition}</span>{r.relation && <span className="text-muted-foreground"> · {r.relation}</span>}</div> },
      { header: "Details", cell: (r) => <span className="text-muted-foreground">{[r.occurred_on, r.details].filter(Boolean).join(" · ") || "—"}</span>, className: "hidden md:table-cell" },
    ],
  }} />;
}
