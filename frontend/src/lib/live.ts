/**
 * Live updates: one Server-Sent Events stream per signed-in staff tab (`GET /api/v1/stream`).
 * Events carry a topic + ids only; on each event we invalidate matching TanStack queries so data is refetched
 * through the normal, permission-checked APIs. fetch() is used instead of EventSource so we can send the bearer token.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { refreshSession, session } from "./api";

type Listener = (topic: string, ids: Record<string, string>) => void;
const listeners = new Set<Listener>();
let connected = false;
const statusSubs = new Set<(c: boolean) => void>();

function setConnected(c: boolean) {
  connected = c;
  statusSubs.forEach((f) => f(c));
}

/** Topic → additional query-key roots to invalidate (the topic itself is always invalidated). */
const FANOUT: Record<string, string[]> = {
  beds: ["census", "command", "adt"],
  adt: ["beds", "census", "command", "ed"],
  ed: ["command", "adt"],
  cases: ["command", "tasks", "worklist"],
  tasks: ["worklist", "command"],
  insurance: ["cases", "command", "worklist"],
  inventory: ["command", "cases"],
  lab: ["command", "orders"],
  discharge: ["adt", "command", "worklist"],
  agents: ["ai"],
};

async function run(signal: AbortSignal) {
  let backoff = 1000;
  while (!signal.aborted) {
    try {
      const headers: Record<string, string> = {};
      if (session.token) headers.Authorization = `Bearer ${session.token}`;
      if (session.org) headers["X-Organization-Id"] = session.org;
      const res = await fetch("/api/v1/stream", { headers, signal, credentials: "include" });
      if (res.status === 401) {
        await refreshSession();
        continue;
      }
      if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
      setConnected(true);
      backoff = 1000;
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += value;
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          let topic = "";
          let data = "";
          for (const line of chunk.split("\n")) {
            if (line.startsWith("event: ")) topic = line.slice(7);
            else if (line.startsWith("data: ")) data += line.slice(6);
          }
          if (!topic) continue;
          let ids: Record<string, string> = {};
          try {
            ids = data ? JSON.parse(data) : {};
          } catch {
            /* ignore malformed */
          }
          listeners.forEach((l) => l(topic, ids));
        }
      }
    } catch {
      if (signal.aborted) return;
    }
    setConnected(false);
    await new Promise((r) => setTimeout(r, backoff));
    backoff = Math.min(backoff * 2, 15000);
  }
}

/** Mount once inside the authenticated staff shell. Re-connects when the organization changes. */
export function useLiveConnection(orgId: string | null | undefined) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!orgId) return;
    const ctrl = new AbortController();
    const onEvent: Listener = (topic) => {
      const roots = new Set([topic, ...(FANOUT[topic] ?? [])]);
      qc.invalidateQueries({ predicate: (q) => roots.has(String(q.queryKey[0])) });
    };
    listeners.add(onEvent);
    run(ctrl.signal);
    return () => {
      listeners.delete(onEvent);
      ctrl.abort();
      setConnected(false);
    };
  }, [orgId, qc]);
}

/** Subscribe to raw live events (e.g. to flash a row). */
export function useLiveEvent(fn: Listener) {
  useEffect(() => {
    listeners.add(fn);
    return () => void listeners.delete(fn);
  }, [fn]);
}

export function useLiveStatus() {
  const [c, setC] = useState(connected);
  useEffect(() => {
    statusSubs.add(setC);
    return () => void statusSubs.delete(setC);
  }, []);
  return c;
}
