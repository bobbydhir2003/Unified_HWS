/**
 * Order sets: clinicians apply a PUBLISHED set (each item can be unticked; nothing is signed — draft orders are created
 * for review and individual signature). Administrators (clinic:manage) edit drafts, publish, and create new versions.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ClipboardList, Copy, ListPlus, Plus, Send, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { PageHeader, toastError } from "@/components/common";
import { DataTable } from "@/components/common/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/misc";
import { get, post, put } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { titleCase } from "@/lib/utils";

type Item = { id?: string; order_type: string; details: Record<string, unknown>; priority: string; default_selected: boolean; note: string | null; title?: string };
export type OrderSetT = { id: string; key: string; version: number; name: string; category: string | null; description: string | null; status: string;
  is_demonstration: boolean; published_at: string | null; published_by: string | null; created_by: string | null; created_at: string; items: Item[] };

const STATUS_VARIANT: Record<string, React.ComponentProps<typeof Badge>["variant"]> = { draft: "warning", published: "success", retired: "neutral" };

export function ApplyOrderSetDialog({ open, onOpenChange, patientId, encounterId, indications = [] }: {
  open: boolean; onOpenChange: (o: boolean) => void; patientId: string; encounterId?: string; indications?: string[];
}) {
  const qc = useQueryClient();
  const sets = useQuery({ queryKey: ["order-sets", "published"], queryFn: () => get<OrderSetT[]>("/order-sets"), enabled: open });
  const [setId, setSetId] = React.useState("");
  const [picked, setPicked] = React.useState<Set<string>>(new Set());
  const [busy, setBusy] = React.useState(false);
  const chosen = sets.data?.find((s) => s.id === setId);
  React.useEffect(() => { if (chosen) setPicked(new Set(chosen.items.filter((i) => i.default_selected).map((i) => i.id!))); }, [chosen]);
  React.useEffect(() => { if (!open) setSetId(""); }, [open]);
  const apply = async () => {
    if (!chosen) return;
    setBusy(true);
    try {
      const r = await post<{ message: string }>(`/order-sets/${chosen.id}/apply`, { patient_id: patientId, encounter_id: encounterId ?? null,
        indication_codes: indications, items: chosen.items.filter((i) => picked.has(i.id!)).map((i) => ({ item_id: i.id })) });
      toast.success(r.message);
      ["orders", "orders-counts"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      onOpenChange(false);
    } catch (e) { toastError(e); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>Use an order set</DialogTitle>
          <DialogDescription>Selected items become draft orders for this patient. Nothing is signed — review and sign each order.</DialogDescription>
        </DialogHeader>
        <Field label="Order set"><NativeSelect value={setId} onChange={(e) => setSetId(e.target.value)}>
          <option value="">Choose…</option>
          {sets.data?.map((s) => <option key={s.id} value={s.id}>{s.name} · v{s.version}</option>)}
        </NativeSelect></Field>
        {chosen && (
          <div className="space-y-2">
            {chosen.description && <p className="rounded-md border border-warning/35 bg-warning-soft px-3 py-2 text-table text-warning-foreground">{chosen.description}</p>}
            <ul className="divide-y rounded-lg border" data-testid="orderset-items">
              {chosen.items.map((i) => (
                <li key={i.id} className="flex items-start gap-3 px-3 py-2">
                  <Checkbox checked={picked.has(i.id!)} onCheckedChange={() => setPicked((s) => { const n = new Set(s); if (n.has(i.id!)) n.delete(i.id!); else n.add(i.id!); return n; })}
                    aria-label={`Include ${i.title}`} className="mt-0.5" />
                  <span className="min-w-0 flex-1 text-table"><span className="font-medium text-heading">{i.title}</span> <Badge variant="neutral">{titleCase(i.order_type)}</Badge>
                    {i.note && <span className="block text-label text-muted-foreground">{i.note}</span>}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={apply} loading={busy} disabled={!chosen || !picked.size}><ListPlus />Create {picked.size || ""} draft order{picked.size === 1 ? "" : "s"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------------------------- administration

type LabCat = { code: string; name: string };

export function OrderSetsAdminPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["order-sets", "all"], queryFn: () => get<OrderSetT[]>("/order-sets", { status: "all" }) });
  const [edit, setEdit] = React.useState<OrderSetT | "new" | null>(null);
  const act = async (s: OrderSetT, a: "publish" | "new-version") => {
    try { const r = await post<OrderSetT>(`/order-sets/${s.id}/${a}`); toast.success(a === "publish" ? `Published v${r.version}` : `Draft v${r.version} created`);
      qc.invalidateQueries({ queryKey: ["order-sets"] }); if (a === "new-version") setEdit(r); } catch (e) { toastError(e); }
  };
  return (
    <>
      <PageHeader title="Order sets" description="Versioned groups of orders. Drafts are editable; publishing makes a version available to clinicians and retires the previous one. Templates here are demonstrations, not clinical protocols."
        actions={<Button onClick={() => setEdit("new")}><Plus />New order set</Button>} />
      <Card className="overflow-hidden">
        <DataTable<OrderSetT> label="Order sets" rows={q.data} isLoading={q.isLoading} error={q.error} retry={q.refetch} rowKey={(s) => s.id}
          searchText={(s) => `${s.name} ${s.category ?? ""}`} defaultSort={{ key: "name", dir: "asc" }} empty={{ icon: ClipboardList, title: "No order sets yet" }}
          columns={[
            { key: "name", header: "Name", sort: (s) => s.name, cell: (s) => <span className="font-medium text-heading">{s.name}</span> },
            { key: "version", header: "Version", align: "right", sort: (s) => s.version, cell: (s) => `v${s.version}` },
            { key: "status", header: "Status", sort: (s) => s.status, cell: (s) => <Badge variant={STATUS_VARIANT[s.status]}>{titleCase(s.status)}</Badge> },
            { key: "items", header: "Items", align: "right", cell: (s) => s.items.length },
            { key: "pub", header: "Published", hideBelow: "md", cell: (s) => s.published_at ? `${fmtDateTime(s.published_at)} · ${s.published_by ?? ""}` : "—" },
            { key: "act", header: "", align: "right", cell: (s) => (
              <span className="inline-flex gap-1">
                {s.status === "draft" && <><Button size="xs" variant="outline" onClick={() => setEdit(s)}>Edit</Button><Button size="xs" onClick={() => act(s, "publish")}><Send />Publish</Button></>}
                {s.status === "published" && <Button size="xs" variant="outline" onClick={() => act(s, "new-version")}><Copy />New version</Button>}
              </span>) },
          ]} />
      </Card>
      {edit && <OrderSetEditor set={edit === "new" ? null : edit} onClose={() => setEdit(null)} />}
    </>
  );
}

function OrderSetEditor({ set, onClose }: { set: OrderSetT | null; onClose: () => void }) {
  const qc = useQueryClient();
  const labs = useQuery({ queryKey: ["catalog", "/catalog/labs", ""], queryFn: () => get<LabCat[]>("/catalog/labs", { q: "" }) });
  const [name, setName] = React.useState(set?.name ?? "");
  const [category, setCategory] = React.useState(set?.category ?? "");
  const [description, setDescription] = React.useState(set?.description ?? "Demonstration template only. Not a clinical protocol: review and adapt through your clinical governance before use.");
  const [items, setItems] = React.useState<Item[]>(set?.items.map(({ order_type, details, priority, default_selected, note }) => ({ order_type, details, priority, default_selected, note })) ?? []);
  const [busy, setBusy] = React.useState(false);
  const upd = (i: number, patch: Partial<Item>) => setItems((xs) => xs.map((x, n) => (n === i ? { ...x, ...patch } : x)));
  const save = async () => {
    setBusy(true);
    try {
      const body = { name, category: category || null, description: description || null, items };
      if (set) await put(`/order-sets/${set.id}`, body); else await post("/order-sets", body);
      toast.success("Draft saved"); qc.invalidateQueries({ queryKey: ["order-sets"] }); onClose();
    } catch (e) { toastError(e); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="lg">
        <DialogHeader><DialogTitle>{set ? `Edit draft · v${set.version}` : "New order set"}</DialogTitle><DialogDescription>Each item is validated like a hand-entered order when you save.</DialogDescription></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name" required><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Category"><Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. Admission" /></Field>
          <Field label="Description" className="sm:col-span-2"><Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        </div>
        <ul className="divide-y rounded-lg border">
          {items.map((it, i) => (
            <li key={i} className="grid gap-2 p-3 sm:grid-cols-[8rem_minmax(0,1fr)_auto] sm:items-end">
              <Field label="Type"><NativeSelect value={it.order_type} onChange={(e) => upd(i, { order_type: e.target.value, details: {} })}>
                {["lab", "nursing", "imaging", "procedure"].map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}</NativeSelect></Field>
              {it.order_type === "lab" ? (
                <Field label="Test"><NativeSelect value={String(it.details.code ?? "")} onChange={(e) => upd(i, { details: { code: e.target.value } })}>
                  <option value="">Choose…</option>{labs.data?.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}</NativeSelect></Field>
              ) : it.order_type === "nursing" ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  <Field label="Instruction"><Input value={String(it.details.instruction ?? "")} onChange={(e) => upd(i, { details: { ...it.details, instruction: e.target.value } })} /></Field>
                  <Field label="Frequency"><Input value={String(it.details.frequency ?? "")} onChange={(e) => upd(i, { details: { ...it.details, frequency: e.target.value } })} /></Field>
                </div>
              ) : it.order_type === "procedure" ? (
                <Field label="Procedure"><Input value={String(it.details.name ?? "")} onChange={(e) => upd(i, { details: { name: e.target.value } })} /></Field>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  <Field label="Imaging code"><Input value={String(it.details.code ?? "")} onChange={(e) => upd(i, { details: { ...it.details, code: e.target.value } })} /></Field>
                  <Field label="Clinical question"><Input value={String(it.details.clinical_question ?? "")} onChange={(e) => upd(i, { details: { ...it.details, clinical_question: e.target.value } })} /></Field>
                </div>
              )}
              <span className="flex items-center gap-2">
                <label className="flex items-center gap-1.5 text-label"><Checkbox checked={it.default_selected} onCheckedChange={(v) => upd(i, { default_selected: v === true })} />Preselected</label>
                <Button variant="ghost" size="xs" onClick={() => setItems((xs) => xs.filter((_, n) => n !== i))} aria-label="Remove item"><Trash2 /></Button>
              </span>
            </li>
          ))}
          <li className="p-2"><Button variant="ghost" size="sm" onClick={() => setItems((xs) => [...xs, { order_type: "lab", details: {}, priority: "routine", default_selected: true, note: null }])}><Plus />Add item</Button></li>
        </ul>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={save} loading={busy} disabled={name.trim().length < 3 || !items.length}><CheckCircle2 />Save draft</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
