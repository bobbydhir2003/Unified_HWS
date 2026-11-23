import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Plus, Video } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorState, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/misc";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/menu";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Appointment, Provider } from "@/lib/types";
import { addDays, fromZoned, hhmm, minutesOfDay, todayIn, weekday, ymd, zoned } from "@/lib/tz";
import { cn } from "@/lib/utils";
import { AppointmentDrawer } from "./AppointmentActions";
import { AppointmentDialog } from "./AppointmentDialog";

type View = "day" | "week" | "month";
const DAY_START = 7 * 60;
const DAY_END = 19 * 60;
const PX = 1.15; // px per minute
const PALETTE: Record<string, string> = {
  blue: "#3b82f6", violet: "#8b5cf6", emerald: "#10b981", amber: "#f59e0b", rose: "#f43f5e", cyan: "#06b6d4", slate: "#64748b",
};
const color = (c?: string | null) => PALETTE[c ?? "blue"] ?? PALETTE.blue;
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function prettyDate(d: string, opts: Intl.DateTimeFormatOptions) {
  const [y, m, dd] = d.split("-").map(Number);
  return new Intl.DateTimeFormat("en-US", { ...opts, timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, dd)));
}

/** Assign overlapping events to side-by-side lanes. */
function layout(events: Appointment[], tz: string) {
  const sorted = [...events].sort((a, b) => a.start_at.localeCompare(b.start_at));
  const out: { a: Appointment; lane: number; lanes: number }[] = [];
  let cluster: typeof out = [];
  let clusterEnd = -1;
  const flush = () => { const n = Math.max(1, ...cluster.map((c) => c.lane + 1)); cluster.forEach((c) => (c.lanes = n)); out.push(...cluster); cluster = []; };
  for (const a of sorted) {
    const s = minutesOfDay(a.start_at, tz), e = s + (new Date(a.end_at).getTime() - new Date(a.start_at).getTime()) / 60000;
    if (s >= clusterEnd && cluster.length) flush();
    const used = new Set(cluster.filter((c) => minutesOfDay(c.a.start_at, tz) + (new Date(c.a.end_at).getTime() - new Date(c.a.start_at).getTime()) / 60000 > s).map((c) => c.lane));
    let lane = 0;
    while (used.has(lane)) lane++;
    cluster.push({ a, lane, lanes: 1 });
    clusterEnd = Math.max(clusterEnd, e);
  }
  if (cluster.length) flush();
  return out;
}

function EventBlock({ a, tz, lane, lanes, onClick, showProvider }: { a: Appointment; tz: string; lane: number; lanes: number; onClick: () => void; showProvider?: boolean }) {
  const s = minutesOfDay(a.start_at, tz);
  const dur = (new Date(a.end_at).getTime() - new Date(a.start_at).getTime()) / 60000;
  const top = Math.max(0, (s - DAY_START) * PX);
  const h = Math.max(18, dur * PX - 2);
  const c = color(a.appointment_type?.color);
  const dim = a.status === "cancelled" || a.status === "no_show";
  const done = a.status === "checked_out" || a.status === "completed";
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      className={cn("absolute overflow-hidden rounded-md border-l-[3px] px-1.5 py-0.5 text-left text-label leading-tight shadow-sm transition hover:z-10 hover:shadow-md focus-visible:z-10", dim && "line-through opacity-50", done && "opacity-70")}
      style={{ top, height: h, left: `calc(${(lane / lanes) * 100}% + 2px)`, width: `calc(${100 / lanes}% - 4px)`, borderLeftColor: c, background: `color-mix(in oklch, ${c} 14%, var(--card))` }}
      aria-label={`${a.patient.name}, ${hhmm(s)}, ${a.appointment_type?.name ?? ""}, ${a.status.replace("_", " ")}`}
    >
      <span className="flex items-center gap-1 font-semibold">
        {a.mode === "telehealth" && <Video className="size-3 shrink-0" />}
        <span className="truncate">{a.patient.name}</span>
        {(a.status === "checked_in" || a.status === "roomed") && <span className="ml-auto size-1.5 shrink-0 rounded-full bg-warning" title="In clinic" />}
        {a.status === "in_progress" && <span className="ml-auto size-1.5 shrink-0 animate-pulse rounded-full bg-ai" title="With provider" />}
      </span>
      {h > 30 && <span className="block truncate text-muted-foreground">{hhmm(s)} · {a.appointment_type?.name ?? a.reason}</span>}
      {h > 44 && showProvider && <span className="block truncate text-muted-foreground">{a.provider.name}</span>}
    </button>
  );
}

function TimeGutter() {
  const hours = [];
  for (let m = DAY_START; m < DAY_END; m += 60) hours.push(m);
  return (
    <div className="relative w-14 shrink-0 border-r" style={{ height: (DAY_END - DAY_START) * PX }}>
      {hours.map((m) => (
        <span key={m} className="absolute right-2 -translate-y-1/2 text-label text-muted-foreground tabular" style={{ top: (m - DAY_START) * PX }}>
          {m === DAY_START ? "" : hhmm(m).replace(":00", "")}
        </span>
      ))}
    </div>
  );
}

function Column({ date, tz, events, unavailable, onSlot, onOpen, showProvider, isToday }: {
  date: string; tz: string; events: Appointment[]; unavailable?: [number, number][]; onSlot: (start: Date) => void; onOpen: (a: Appointment) => void; showProvider?: boolean; isToday: boolean;
}) {
  const nowMin = isToday ? minutesOfDay(new Date(), tz) : -1;
  return (
    <div
      className="relative min-w-[140px] flex-1 border-r last:border-r-0"
      style={{ height: (DAY_END - DAY_START) * PX, backgroundImage: `repeating-linear-gradient(to bottom, var(--border) 0 1px, transparent 1px ${60 * PX}px)` }}
      onClick={(e) => {
        const y = e.clientY - e.currentTarget.getBoundingClientRect().top;
        const mins = DAY_START + Math.floor(y / PX / 15) * 15;
        onSlot(fromZoned(date, mins, tz));
      }}
      role="grid"
      aria-label={`Schedule for ${date}`}
    >
      {unavailable?.map(([s, e], i) => (
        <div key={i} className="pointer-events-none absolute inset-x-0 bg-[repeating-linear-gradient(135deg,var(--muted)_0_6px,transparent_6px_12px)] opacity-80"
          style={{ top: (Math.max(s, DAY_START) - DAY_START) * PX, height: (Math.min(e, DAY_END) - Math.max(s, DAY_START)) * PX }} />
      ))}
      {nowMin >= DAY_START && nowMin <= DAY_END && (
        <div className="pointer-events-none absolute inset-x-0 z-[5] border-t-2 border-destructive" style={{ top: (nowMin - DAY_START) * PX }}>
          <span className="absolute -left-1 -top-[5px] size-2 rounded-full bg-destructive" />
        </div>
      )}
      {layout(events, tz).map(({ a, lane, lanes }) => (
        <EventBlock key={a.id} a={a} tz={tz} lane={lane} lanes={lanes} onClick={() => onOpen(a)} showProvider={showProvider} />
      ))}
    </div>
  );
}

function unavailableBlocks(p: Provider | undefined, clinicId: string, date: string): [number, number][] {
  if (!p) return [];
  const wd = weekday(date);
  const avail = p.availability.filter((b) => b.clinic_id === clinicId && b.weekday === wd)
    .map((b) => [+b.start_time.slice(0, 2) * 60 + +b.start_time.slice(3, 5), +b.end_time.slice(0, 2) * 60 + +b.end_time.slice(3, 5)] as [number, number])
    .sort((a, b) => a[0] - b[0]);
  const out: [number, number][] = [];
  let cur = DAY_START;
  for (const [s, e] of avail) { if (s > cur) out.push([cur, s]); cur = Math.max(cur, e); }
  if (cur < DAY_END) out.push([cur, DAY_END]);
  return out;
}

export function SchedulePage() {
  const { clinic, membership, can } = useAuth();
  const tz = clinic?.timezone ?? "America/New_York";
  const [params, setParams] = useSearchParams();
  const view = (params.get("view") as View) || "day";
  const date = params.get("date") || todayIn(tz);
  const [selectedProviders, setSelectedProviders] = React.useState<string[] | null>(null);
  const [openId, setOpenId] = React.useState<string | null>(null);
  const [booking, setBooking] = React.useState<{ start: Date | null; providerId?: string } | null>(params.get("new") ? { start: null } : null);

  const setP = (k: string, v: string) => { const n = new URLSearchParams(params); n.set(k, v); n.delete("new"); setParams(n, { replace: true }); };
  const providers = useQuery({ queryKey: ["providers"], queryFn: () => get<Provider[]>("/providers") });
  const provList = providers.data ?? [];
  const activeIds = selectedProviders ?? (membership?.provider_id && view !== "day" ? [membership.provider_id] : provList.map((p) => p.id));

  const range = React.useMemo(() => {
    if (view === "day") return [date, addDays(date, 1)];
    if (view === "week") { const s = addDays(date, -weekday(date)); return [s, addDays(s, 7)]; }
    const first = date.slice(0, 8) + "01";
    const s = addDays(first, -weekday(first));
    return [s, addDays(s, 42)];
  }, [view, date]);

  const q = useQuery({
    queryKey: ["appointments", clinic?.id, range[0], range[1]],
    queryFn: () => get<Appointment[]>("/appointments", { start: fromZoned(range[0], 0, tz).toISOString(), end: fromZoned(range[1], 0, tz).toISOString(), clinic_id: clinic?.id, include_cancelled: true }),
    enabled: !!clinic,
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });
  const appts = (q.data ?? []).filter((a) => activeIds.includes(a.provider.id));
  const byDate = React.useMemo(() => {
    const m: Record<string, Appointment[]> = {};
    for (const a of appts) (m[ymd(zoned(a.start_at, tz))] ??= []).push(a);
    return m;
  }, [appts, tz]);
  const open = q.data?.find((a) => a.id === openId) ?? null;
  const today = todayIn(tz);
  const step = (dir: number) => {
    if (view === "day") setP("date", addDays(date, dir));
    else if (view === "week") setP("date", addDays(date, 7 * dir));
    else { const [y, m] = date.split("-").map(Number); const t = new Date(Date.UTC(y, m - 1 + dir, 1)); setP("date", ymd({ y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: 1 })); }
  };
  const title = view === "day" ? prettyDate(date, { weekday: "long", month: "long", day: "numeric", year: "numeric" })
    : view === "week" ? `Week of ${prettyDate(range[0], { month: "short", day: "numeric" })} – ${prettyDate(addDays(range[1], -1), { month: "short", day: "numeric", year: "numeric" })}`
      : `${MONTHS[+date.slice(5, 7) - 1]} ${date.slice(0, 4)}`;
  const canBook = can("schedule:write");
  const slot = (start: Date, providerId?: string) => canBook && setBooking({ start, providerId });
  const visibleProviders = provList.filter((p) => activeIds.includes(p.id));

  return (
    <>
      <PageHeader title="Schedule" description={`${clinic?.name ?? ""} · ${tz.replace("_", " ")}`}
        actions={canBook && <Button onClick={() => setBooking({ start: null })}><Plus />New appointment</Button>} />
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b p-3">
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon-sm" onClick={() => step(-1)} aria-label="Previous"><ChevronLeft /></Button>
            <Button variant="outline" size="sm" onClick={() => setP("date", today)} disabled={date === today && view === "day"}>Today</Button>
            <Button variant="outline" size="icon-sm" onClick={() => step(1)} aria-label="Next"><ChevronRight /></Button>
          </div>
          <h2 className="ml-1 text-section font-semibold">{title}</h2>
          {q.isFetching && <span className="size-3 animate-spin rounded-full border-2 border-primary border-t-transparent" aria-label="Refreshing" />}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Popover>
              <PopoverTrigger asChild><Button variant="outline" size="sm">Providers ({activeIds.length}/{provList.length})</Button></PopoverTrigger>
              <PopoverContent align="end" className="w-64 space-y-1">
                {provList.map((p) => (
                  <label key={p.id} className="flex items-center gap-2 rounded-md px-1.5 py-1 text-table hover:bg-muted">
                    <Checkbox checked={activeIds.includes(p.id)} onCheckedChange={(c) => setSelectedProviders(c ? [...activeIds, p.id] : activeIds.filter((x) => x !== p.id))} />
                    <span className="size-2.5 rounded-full" style={{ background: color(p.color) }} />{p.name}
                  </label>
                ))}
                <div className="flex gap-1 pt-1">
                  <Button size="xs" variant="ghost" onClick={() => setSelectedProviders(provList.map((p) => p.id))}>All</Button>
                  {membership?.provider_id && <Button size="xs" variant="ghost" onClick={() => setSelectedProviders([membership.provider_id!])}>Just me</Button>}
                </div>
              </PopoverContent>
            </Popover>
            <div className="inline-flex rounded-lg bg-muted p-0.5" role="tablist" aria-label="Calendar view">
              {(["day", "week", "month"] as View[]).map((v) => (
                <button key={v} role="tab" aria-selected={view === v} onClick={() => setP("view", v)}
                  className={cn("rounded-md px-3 py-1 text-table font-medium capitalize text-muted-foreground", view === v && "bg-card text-foreground shadow-sm")}>{v}</button>
              ))}
            </div>
          </div>
        </div>

        {q.error ? <ErrorState error={q.error} retry={q.refetch} /> : view === "month" ? (
          <div className="grid grid-cols-7">
            {WEEKDAYS.map((w) => <div key={w} className="border-b border-r px-2 py-1.5 text-label font-semibold uppercase tracking-wide text-muted-foreground last:border-r-0">{w}</div>)}
            {Array.from({ length: 42 }).map((_, i) => {
              const d = addDays(range[0], i);
              const list = byDate[d] ?? [];
              const inMonth = d.slice(0, 7) === date.slice(0, 7);
              const active = list.filter((a) => a.status !== "cancelled" && a.status !== "no_show");
              return (
                <button key={d} onClick={() => { const n = new URLSearchParams(params); n.set("view", "day"); n.set("date", d); setParams(n); }}
                  className={cn("min-h-24 border-b border-r p-1.5 text-left align-top transition-colors hover:bg-muted/40 [&:nth-child(7n)]:border-r-0", !inMonth && "bg-muted/30 text-muted-foreground")}>
                  <span className={cn("inline-grid size-6 place-items-center rounded-full text-xs font-medium", d === today && "bg-primary text-primary-foreground")}>{+d.slice(8)}</span>
                  <div className="mt-1 space-y-0.5">
                    {active.slice(0, 3).map((a) => (
                      <div key={a.id} className="truncate rounded px-1 text-label" style={{ background: `color-mix(in oklch, ${color(a.appointment_type?.color)} 14%, transparent)` }}>
                        {hhmm(minutesOfDay(a.start_at, tz)).replace(" ", "").toLowerCase()} {a.patient.name.split(" ").slice(-1)[0]}
                      </div>
                    ))}
                    {active.length > 3 && <div className="px-1 text-label font-medium text-muted-foreground">+{active.length - 3} more</div>}
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="max-h-[calc(100dvh-230px)] overflow-auto scrollbar-thin">
            <div className="sticky top-0 z-10 flex border-b bg-card">
              <div className="w-14 shrink-0 border-r" />
              {view === "day" ? visibleProviders.map((p) => (
                <div key={p.id} className="flex min-w-[140px] flex-1 items-center gap-2 border-r px-2 py-2 last:border-r-0">
                  <span className="size-2.5 rounded-full" style={{ background: color(p.color) }} />
                  <span className="truncate text-table font-medium">{p.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground tabular">{(byDate[date] ?? []).filter((a) => a.provider.id === p.id && a.status !== "cancelled").length}</span>
                </div>
              )) : Array.from({ length: 7 }).map((_, i) => {
                const d = addDays(range[0], i);
                return (
                  <button key={d} onClick={() => { const n = new URLSearchParams(params); n.set("view", "day"); n.set("date", d); setParams(n); }}
                    className="min-w-[140px] flex-1 border-r px-2 py-1.5 text-left last:border-r-0 hover:bg-muted/40">
                    <span className="block text-label font-semibold uppercase text-muted-foreground">{WEEKDAYS[i]}</span>
                    <span className={cn("inline-grid size-7 place-items-center rounded-full text-section font-semibold", d === today && "bg-primary text-primary-foreground")}>{+d.slice(8)}</span>
                  </button>
                );
              })}
            </div>
            <div className="flex">
              <TimeGutter />
              {view === "day" ? (
                visibleProviders.length ? visibleProviders.map((p) => (
                  <Column key={p.id} date={date} tz={tz} isToday={date === today}
                    events={(byDate[date] ?? []).filter((a) => a.provider.id === p.id)}
                    unavailable={clinic ? unavailableBlocks(p, clinic.id, date) : []}
                    onSlot={(s) => slot(s, p.id)} onOpen={(a) => setOpenId(a.id)} />
                )) : <p className="p-6 text-table text-muted-foreground">Select at least one provider.</p>
              ) : Array.from({ length: 7 }).map((_, i) => {
                const d = addDays(range[0], i);
                return (
                  <Column key={d} date={d} tz={tz} isToday={d === today} events={byDate[d] ?? []} showProvider={activeIds.length > 1}
                    unavailable={activeIds.length === 1 && clinic ? unavailableBlocks(provList.find((p) => p.id === activeIds[0]), clinic.id, d) : []}
                    onSlot={(s) => slot(s, activeIds.length === 1 ? activeIds[0] : undefined)} onOpen={(a) => setOpenId(a.id)} />
                );
              })}
            </div>
          </div>
        )}
      </Card>
      <p className="mt-2 text-xs text-muted-foreground">Hatched areas are outside the provider's scheduled hours. {canBook && "Click an open time to book."}</p>
      <AppointmentDrawer appt={open} onOpenChange={(o) => !o && setOpenId(null)} />
      <AppointmentDialog open={!!booking} onOpenChange={(o) => !o && setBooking(null)} initialStart={booking?.start} initialProviderId={booking?.providerId} />
    </>
  );
}
