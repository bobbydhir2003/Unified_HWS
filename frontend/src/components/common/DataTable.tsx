/**
 * Enterprise data table: search, filters (toolbar slot), sortable columns (aria-sort), pagination, row selection with
 * bulk actions, keyboard-operable rows, sticky header, and the shared loading / empty / error states.
 * Client-side by default (worklists are bounded by the API); `total`/`page` props allow server paging later.
 */
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, type LucideIcon, Search } from "lucide-react";
import * as React from "react";
import { EmptyState, ErrorState, LoadingRows } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { cn } from "@/lib/utils";

export type Column<T> = {
  key: string;
  header: React.ReactNode;
  cell: (row: T) => React.ReactNode;
  /** Value used for sorting; omit to make the column unsortable. */
  sort?: (row: T) => string | number | null | undefined;
  align?: "left" | "right" | "center";
  className?: string;
  /** Hide on narrow screens. */
  hideBelow?: "sm" | "md" | "lg";
};

type Props<T> = {
  rows: T[] | undefined;
  columns: Column<T>[];
  rowKey: (row: T) => string;
  label: string;
  isLoading?: boolean;
  error?: unknown;
  retry?: () => void;
  /** Text used by the search box; omit to hide search. */
  searchText?: (row: T) => string;
  searchPlaceholder?: string;
  toolbar?: React.ReactNode;
  onRowClick?: (row: T) => void;
  selectedKey?: string | null;
  selectable?: boolean;
  bulkActions?: (selected: T[], clear: () => void) => React.ReactNode;
  defaultSort?: { key: string; dir: "asc" | "desc" };
  pageSize?: number;
  empty?: { icon?: LucideIcon; title: string; description?: string };
  rowClassName?: (row: T) => string | undefined;
  dense?: boolean;
  className?: string;
};

const HIDE = { sm: "hidden sm:table-cell", md: "hidden md:table-cell", lg: "hidden lg:table-cell" } as const;

export function DataTable<T>({
  rows, columns, rowKey, label, isLoading, error, retry, searchText, searchPlaceholder = "Search…", toolbar, onRowClick, selectedKey,
  selectable, bulkActions, defaultSort, pageSize = 25, empty, rowClassName, dense, className,
}: Props<T>) {
  const [q, setQ] = React.useState("");
  const [sort, setSort] = React.useState(defaultSort ?? null);
  const [page, setPage] = React.useState(0);
  const [sel, setSel] = React.useState<Set<string>>(new Set());

  const filtered = React.useMemo(() => {
    let out = rows ?? [];
    const needle = q.trim().toLowerCase();
    if (needle && searchText) out = out.filter((r) => searchText(r).toLowerCase().includes(needle));
    if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      if (col?.sort) {
        const f = col.sort;
        out = [...out].sort((a, b) => {
          const x = f(a), y = f(b);
          if (x == null && y == null) return 0;
          if (x == null) return 1;
          if (y == null) return -1;
          const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true });
          return sort.dir === "asc" ? c : -c;
        });
      }
    }
    return out;
  }, [rows, q, sort, columns, searchText]);

  React.useEffect(() => setPage(0), [q, sort, rows]);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const visible = filtered.slice(page * pageSize, page * pageSize + pageSize);
  const selected = (rows ?? []).filter((r) => sel.has(rowKey(r)));
  const allOnPage = visible.length > 0 && visible.every((r) => sel.has(rowKey(r)));
  const toggle = (k: string) => setSel((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const clear = () => setSel(new Set());

  const header = (searchText || toolbar || (selectable && selected.length > 0)) && (
    <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
      {searchText && (
        <div className="relative w-full sm:w-64">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={searchPlaceholder} className="h-8 pl-8" aria-label={`Search ${label}`} />
        </div>
      )}
      {toolbar}
      {selectable && selected.length > 0 && bulkActions && (
        <div className="ml-auto flex items-center gap-2" role="region" aria-label="Bulk actions">
          <span className="text-table text-muted-foreground">{selected.length} selected</span>
          {bulkActions(selected, clear)}
        </div>
      )}
    </div>
  );

  if (error) return <div className={className}>{header}<ErrorState error={error} retry={retry} /></div>;
  return (
    <div className={cn("min-w-0", className)} data-testid={`table-${label.toLowerCase().replace(/\s+/g, "-")}`}>
      {header}
      {isLoading ? <LoadingRows /> : !filtered.length ? (
        <EmptyState icon={empty?.icon} title={q ? "No matches" : empty?.title ?? "Nothing here"} description={q ? "Try a different search." : empty?.description} />
      ) : (
        <Table aria-label={label} className={cn(dense && "[&_td]:py-1.5")}>
          <THead>
            <TR>
              {selectable && (
                <TH className="w-8"><Checkbox aria-label="Select all on this page" checked={allOnPage}
                  onCheckedChange={() => setSel((s) => { const n = new Set(s); visible.forEach((r) => (allOnPage ? n.delete(rowKey(r)) : n.add(rowKey(r)))); return n; })} /></TH>
              )}
              {columns.map((c) => {
                const active = sort?.key === c.key;
                const dir = active ? sort!.dir : undefined;
                return (
                  <TH key={c.key} className={cn(c.align === "right" && "text-right", c.align === "center" && "text-center", c.hideBelow && HIDE[c.hideBelow], c.className)}
                    aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : c.sort ? "none" : undefined}>
                    {c.sort ? (
                      <button type="button" className="inline-flex items-center gap-1 rounded hover:text-heading focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                        onClick={() => setSort(active && dir === "asc" ? { key: c.key, dir: "desc" } : { key: c.key, dir: "asc" })}>
                        {c.header}
                        {active ? (dir === "asc" ? <ArrowUp className="size-3" aria-hidden /> : <ArrowDown className="size-3" aria-hidden />) : <ArrowUpDown className="size-3 opacity-40" aria-hidden />}
                      </button>
                    ) : c.header}
                  </TH>
                );
              })}
            </TR>
          </THead>
          <TBody>
            {visible.map((r) => {
              const k = rowKey(r);
              return (
                <TR key={k} data-clickable={!!onRowClick} data-selected={selectedKey === k || sel.has(k)} className={rowClassName?.(r)}
                  tabIndex={onRowClick ? 0 : undefined} onClick={onRowClick ? () => onRowClick(r) : undefined}
                  onKeyDown={onRowClick ? (e) => { if (e.key === "Enter" && e.target === e.currentTarget) onRowClick(r); } : undefined}>
                  {selectable && (
                    <TD className="w-8" onClick={(e) => e.stopPropagation()}><Checkbox aria-label="Select row" checked={sel.has(k)} onCheckedChange={() => toggle(k)} /></TD>
                  )}
                  {columns.map((c) => (
                    <TD key={c.key} className={cn(c.align === "right" && "text-right tabular", c.align === "center" && "text-center", c.hideBelow && HIDE[c.hideBelow], c.className)}>
                      {c.cell(r)}
                    </TD>
                  ))}
                </TR>
              );
            })}
          </TBody>
        </Table>
      )}
      {!isLoading && filtered.length > pageSize && (
        <div className="flex items-center justify-between gap-2 border-t px-3 py-2 text-table text-muted-foreground">
          <span>{page * pageSize + 1}–{Math.min(filtered.length, (page + 1) * pageSize)} of {filtered.length}</span>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="xs" disabled={page === 0} onClick={() => setPage((p) => p - 1)} aria-label="Previous page"><ChevronLeft /></Button>
            <span className="tabular">Page {page + 1} / {pages}</span>
            <Button variant="ghost" size="xs" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)} aria-label="Next page"><ChevronRight /></Button>
          </div>
        </div>
      )}
    </div>
  );
}

/** A compact titled panel (worklists, side-by-side consoles). */
export function WorkPanel({ title, count, actions, children, className, maximized, onToggleMax, id }: {
  title: string; count?: number; actions?: React.ReactNode; children: React.ReactNode; className?: string; maximized?: boolean;
  onToggleMax?: () => void; id?: string;
}) {
  return (
    <section id={id} aria-label={title} className={cn("flex min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border bg-card", className)}>
      <header className="flex items-center gap-2 border-b bg-subtle px-3 py-2">
        <h2 className="text-section font-semibold text-heading">{title}</h2>
        {count != null && <span className="rounded-full bg-muted px-1.5 text-label font-semibold tabular text-muted-foreground">{count}</span>}
        <div className="ml-auto flex items-center gap-1">
          {actions}
          {onToggleMax && (
            <Button variant="ghost" size="xs" onClick={onToggleMax} aria-pressed={maximized} aria-label={maximized ? `Restore ${title}` : `Expand ${title}`}>
              {maximized ? "Restore" : "Expand"}
            </Button>
          )}
        </div>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">{children}</div>
    </section>
  );
}
