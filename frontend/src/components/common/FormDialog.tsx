import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/menu";
import { Checkbox } from "@/components/ui/misc";
import { get } from "@/lib/api";
import { cn } from "@/lib/utils";

export type FieldSpec = {
  name: string;
  label: string;
  type?: "text" | "textarea" | "select" | "date" | "checkbox" | "icd10" | "number";
  options?: [string, string][];
  required?: boolean;
  placeholder?: string;
  hint?: string;
  span?: 1 | 2;
};

type Values = Record<string, string | boolean | null>;

/** Spec-driven dialog form for simple clinical list entries (problems, meds, allergies, history, insurance…). */
export function FormDialog({
  open, onOpenChange, title, description, fields, initial, onSubmit, submitLabel = "Save", extraFooter,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description?: string;
  fields: FieldSpec[];
  initial?: Values;
  onSubmit: (v: Values) => Promise<void>;
  submitLabel?: string;
  extraFooter?: React.ReactNode;
}) {
  const defaults = React.useMemo(() => {
    const d: Values = {};
    for (const f of fields) d[f.name] = initial?.[f.name] ?? (f.type === "checkbox" ? false : f.type === "select" ? f.options?.[0]?.[0] ?? "" : "");
    return d;
  }, [fields, initial]);
  const form = useForm<Values>({ values: defaults });
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => { if (open) setError(null); }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <form noValidate className="grid gap-4" onSubmit={form.handleSubmit(async (v) => {
          setError(null);
          const out: Values = {};
          for (const f of fields) {
            const val = v[f.name];
            out[f.name] = typeof val === "string" ? (val.trim() === "" ? null : val.trim()) : val;
          }
          try { await onSubmit(out); onOpenChange(false); } catch (e) { setError(e instanceof Error ? e.message : "Save failed"); }
        })}>
          {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive-soft px-3 py-2 text-[13px] text-destructive">{error}</div>}
          <div className="grid gap-4 sm:grid-cols-2">
            {fields.map((f, i) => {
              const err = form.formState.errors[f.name]?.message as string | undefined;
              const reg = form.register(f.name, { required: f.required ? `${f.label} is required` : false });
              const span = f.span === 1 ? "" : "sm:col-span-2";
              if (f.type === "checkbox") {
                return (
                  <Controller key={f.name} control={form.control} name={f.name} render={({ field }) => (
                    <label className={cn("flex items-center gap-2 text-[13px]", span)}>
                      <Checkbox checked={!!field.value} onCheckedChange={(c) => field.onChange(!!c)} />{f.label}
                    </label>
                  )} />
                );
              }
              if (f.type === "icd10") {
                return (
                  <Controller key={f.name} control={form.control} name={f.name} render={({ field }) => (
                    <Field label={f.label} hint={f.hint} className={span}>
                      <Icd10Picker
                        value={(field.value as string) ?? ""}
                        onPick={(code, desc) => { field.onChange(code); if (!form.getValues("description")) form.setValue("description", desc, { shouldDirty: true }); }}
                      />
                    </Field>
                  )} />
                );
              }
              return (
                <Field key={f.name} label={f.label} required={f.required} error={err} hint={f.hint} className={span}>
                  {f.type === "textarea" ? <Textarea rows={3} placeholder={f.placeholder} autoFocus={i === 0} {...reg} />
                    : f.type === "select" ? <NativeSelect {...reg}>{f.options?.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</NativeSelect>
                      : <Input type={f.type === "date" ? "date" : f.type === "number" ? "number" : "text"} placeholder={f.placeholder} autoFocus={i === 0} {...reg} />}
                </Field>
              );
            })}
          </div>
          <DialogFooter>
            {extraFooter}
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" loading={form.formState.isSubmitting}>{submitLabel}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

type Code = { code: string; description: string };

/** Type-ahead over the ICD-10-CM subset served by /codes/icd10. */
export function Icd10Picker({ value, onPick, placeholder = "Search ICD-10 by code or description", autoFocus, clearOnPick }: {
  value?: string; onPick: (code: string, description: string) => void; placeholder?: string; autoFocus?: boolean; clearOnPick?: boolean;
}) {
  const [q, setQ] = React.useState(value ?? "");
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(0);
  React.useEffect(() => setQ(value ?? ""), [value]);
  const { data } = useQuery({
    queryKey: ["icd10", q], queryFn: () => get<Code[]>("/codes/icd10", { q }), enabled: q.trim().length >= 2, staleTime: 60_000,
  });
  const items = data ?? [];
  const pick = (c: Code) => { onPick(c.code, c.description); setQ(clearOnPick ? "" : c.code); setOpen(false); };
  return (
    <Popover open={open && items.length > 0} onOpenChange={setOpen}>
      <PopoverAnchor asChild>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q} autoFocus={autoFocus} placeholder={placeholder} className="pl-9" role="combobox" aria-expanded={open} aria-autocomplete="list"
            onChange={(e) => { setQ(e.target.value); setOpen(true); setActive(0); }}
            onFocus={() => setOpen(true)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
              if (e.key === "Enter" && open && items[active]) { e.preventDefault(); pick(items[active]); }
              if (e.key === "Escape") setOpen(false);
            }}
          />
        </div>
      </PopoverAnchor>
      <PopoverContent className="w-[var(--radix-popover-trigger-width)] min-w-80 p-1" onOpenAutoFocus={(e) => e.preventDefault()}>
        <ul role="listbox" className="max-h-64 overflow-y-auto">
          {items.map((c, i) => (
            <li key={c.code} role="option" aria-selected={i === active}>
              <button type="button" onMouseEnter={() => setActive(i)} onClick={() => pick(c)}
                className={cn("flex w-full gap-3 rounded-md px-2 py-1.5 text-left text-[13px]", i === active && "bg-muted")}>
                <span className="w-16 shrink-0 font-mono text-xs font-semibold text-primary">{c.code}</span>
                <span className="min-w-0">{c.description}</span>
              </button>
            </li>
          ))}
        </ul>
        <p className="border-t px-2 pt-1.5 text-[11px] text-muted-foreground">Common-code subset · full ICD-10-CM import pending</p>
      </PopoverContent>
    </Popover>
  );
}
