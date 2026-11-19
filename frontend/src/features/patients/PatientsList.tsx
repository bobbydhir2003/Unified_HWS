import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Lock, Search, UserPlus, UsersRound } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Avatar } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDob, sexShort } from "@/lib/format";
import type { Page, PatientListItem } from "@/lib/types";

export function PatientsList() {
  const [params, setParams] = useSearchParams();
  const { can } = useAuth();
  const navigate = useNavigate();
  const [q, setQ] = React.useState(params.get("q") ?? "");
  const status = params.get("status") ?? "active";
  const page = Number(params.get("page") ?? 1);

  React.useEffect(() => {
    const t = setTimeout(() => {
      const next = new URLSearchParams(params);
      if (q) next.set("q", q); else next.delete("q");
      next.delete("page");
      if (next.toString() !== params.toString()) setParams(next, { replace: true });
    }, 250);
    return () => clearTimeout(t);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  const query = useQuery({
    queryKey: ["patients", params.get("q"), status, page],
    queryFn: () => get<Page<PatientListItem>>("/patients", { q: params.get("q"), status: status === "all" ? undefined : status, page, page_size: 25 }),
    placeholderData: keepPreviousData,
  });
  const setParam = (k: string, v: string | null) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    if (k !== "page") next.delete("page");
    setParams(next);
  };
  const data = query.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <PageHeader
        title="Patients"
        description="Search by name, MRN, date of birth or phone number."
        actions={can("patients:write") && <Button asChild><Link to="/patients/new"><UserPlus />Register patient</Link></Button>}
      />
      <Card className="overflow-hidden">
        <div className="flex flex-col gap-2 border-b p-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Moreau, UD100012, 04/12/1986" className="pl-9" aria-label="Search patients" autoFocus />
          </div>
          <NativeSelect value={status} onChange={(e) => setParam("status", e.target.value)} className="sm:w-40" aria-label="Status filter">
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="deceased">Deceased</option>
            <option value="all">All statuses</option>
          </NativeSelect>
        </div>
        {query.error ? <ErrorState error={query.error} retry={query.refetch} /> : query.isLoading ? <LoadingRows rows={8} /> : !data?.items.length ? (
          <EmptyState icon={UsersRound} title={params.get("q") ? "No matching patients" : "No patients yet"}
            description={params.get("q") ? "Check the spelling or try a date of birth or MRN." : undefined}
            action={can("patients:write") && <Button variant="outline" asChild><Link to="/patients/new"><UserPlus />Register patient</Link></Button>} />
        ) : (
          <Table>
            <THead>
              <TR><TH>Patient</TH><TH>DOB / Sex</TH><TH>MRN</TH><TH className="hidden md:table-cell">Phone</TH><TH className="hidden lg:table-cell">Primary provider</TH><TH className="hidden lg:table-cell">Last visit</TH></TR>
            </THead>
            <TBody className={query.isFetching ? "opacity-70 transition-opacity" : ""}>
              {data.items.map((p) => {
                const name = `${p.last_name}, ${p.first_name}`;
                return (
                  <TR key={p.id} data-clickable tabIndex={0} onClick={() => navigate(`/patients/${p.id}`)}
                    onKeyDown={(e) => e.key === "Enter" && navigate(`/patients/${p.id}`)}>
                    <TD>
                      <div className="flex items-center gap-3">
                        <Avatar name={`${p.first_name} ${p.last_name}`} />
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 font-medium">
                            {name}
                            {p.preferred_name && <span className="font-normal text-muted-foreground">“{p.preferred_name}”</span>}
                            {p.is_restricted && <Lock className="size-3.5 text-warning" aria-label="Restricted chart" />}
                          </div>
                          {p.status !== "active" && <Badge variant="danger" className="mt-0.5">{p.status}</Badge>}
                        </div>
                      </div>
                    </TD>
                    <TD className="tabular">{fmtDob(p.date_of_birth)} · {sexShort(p.sex_at_birth)}</TD>
                    <TD className="font-mono text-[12.5px] text-muted-foreground">{p.mrn}</TD>
                    <TD className="hidden tabular md:table-cell">{p.phone ?? "—"}</TD>
                    <TD className="hidden lg:table-cell">{p.primary_provider_name ?? "—"}</TD>
                    <TD className="hidden text-muted-foreground lg:table-cell">{fmtDate(p.last_visit_at)}</TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        )}
        {data && data.total > data.page_size && (
          <div className="flex items-center justify-between border-t px-4 py-2.5 text-[13px] text-muted-foreground">
            <span>{(page - 1) * data.page_size + 1}–{Math.min(page * data.page_size, data.total)} of {data.total}</span>
            <div className="flex gap-1">
              <Button variant="outline" size="icon-sm" disabled={page <= 1} onClick={() => setParam("page", String(page - 1))} aria-label="Previous page"><ChevronLeft /></Button>
              <Button variant="outline" size="icon-sm" disabled={page >= pages} onClick={() => setParam("page", String(page + 1))} aria-label="Next page"><ChevronRight /></Button>
            </div>
          </div>
        )}
      </Card>
    </>
  );
}
