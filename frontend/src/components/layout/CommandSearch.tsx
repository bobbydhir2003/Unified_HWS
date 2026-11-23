import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { Lock, Search, UserRound } from "lucide-react";
import { Dialog as D } from "radix-ui";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDob, sexShort } from "@/lib/format";
import { NAV } from "./nav";

type Hit = { id: string; name: string; mrn: string; date_of_birth: string; sex_at_birth: string; status: string; is_restricted: boolean };

function useDebounced<T>(value: T, ms = 180) {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function CommandSearch({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [q, setQ] = React.useState("");
  const dq = useDebounced(q.trim());
  const navigate = useNavigate();
  const { can, membership } = useAuth();
  const { data, isFetching } = useQuery({
    queryKey: ["search", dq],
    queryFn: () => get<{ patients: Hit[] }>("/search", { q: dq }),
    enabled: open && dq.length >= 2,
    staleTime: 10_000,
  });
  React.useEffect(() => { if (!open) setQ(""); }, [open]);
  const go = (to: string) => { onOpenChange(false); navigate(to); };
  const pages = NAV.flatMap((s) => s.items).filter((i) => (!i.perm || can(i.perm)) && (!i.providerOnly || membership?.provider_id));

  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-[2px]" />
        <D.Content className="fixed left-1/2 top-[12vh] z-50 w-[calc(100vw-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-xl border bg-popover shadow-2xl data-[state=open]:animate-in" aria-describedby={undefined}>
          <D.Title className="sr-only">Search</D.Title>
          <Command shouldFilter={false} label="Search patients and pages">
            <div className="flex items-center gap-2 border-b px-4">
              <Search className="size-4 text-muted-foreground" />
              <Command.Input value={q} onValueChange={setQ} autoFocus placeholder="Name, MRN, date of birth (MM/DD/YYYY) or phone…"
                className="h-12 flex-1 bg-transparent text-body outline-none placeholder:text-muted-foreground" />
              {isFetching && <span className="size-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />}
            </div>
            <Command.List className="max-h-[60vh] overflow-y-auto p-2">
              {dq.length >= 2 && data && !data.patients.length && (
                <Command.Empty className="px-3 py-6 text-center text-table text-muted-foreground">No patients match “{dq}”.</Command.Empty>
              )}
              {!!data?.patients.length && dq.length >= 2 && (
                <Command.Group heading="Patients" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-label [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground">
                  {data.patients.map((p) => (
                    <Command.Item key={p.id} value={p.id} onSelect={() => go(`/patients/${p.id}`)}
                      className="flex cursor-default items-center gap-3 rounded-lg px-2.5 py-2 data-[selected=true]:bg-accent">
                      <span className="grid size-8 place-items-center rounded-full bg-muted text-muted-foreground"><UserRound className="size-4" /></span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5 font-medium">
                          {p.name}
                          {p.is_restricted && <Lock className="size-3 text-warning" aria-label="Restricted chart" />}
                          {p.status !== "active" && <span className="text-label font-normal text-destructive">({p.status})</span>}
                        </span>
                        {/* DOB + sex + MRN always shown together to prevent wrong-patient selection */}
                        <span className="block text-xs text-muted-foreground tabular">
                          DOB {fmtDob(p.date_of_birth)} · {sexShort(p.sex_at_birth)} · MRN {p.mrn}
                        </span>
                      </span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
              {dq.length < 2 && (
                <Command.Group heading="Go to" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-label [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground">
                  {pages.map((p) => (
                    <Command.Item key={p.to} value={p.to} onSelect={() => go(p.to)}
                      className="flex cursor-default items-center gap-3 rounded-lg px-2.5 py-2 text-body data-[selected=true]:bg-accent">
                      <p.icon className="size-4 text-muted-foreground" />{p.label}
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
            </Command.List>
            <div className="flex items-center gap-3 border-t px-4 py-2 text-label text-muted-foreground">
              <span>↑↓ navigate</span><span>↵ open</span><span>esc close</span>
            </div>
          </Command>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
