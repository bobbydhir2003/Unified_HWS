/** Fetch wrapper: bearer token (memory only), org header, one transparent refresh on 401. */

type Detail = string | { code?: string; message?: string; [k: string]: unknown } | { msg: string; loc: string[] }[];

export class ApiError extends Error {
  status: number;
  code?: string;
  detail: Detail;
  constructor(status: number, detail: Detail) {
    super(messageFrom(detail, status));
    this.status = status;
    this.detail = detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) this.code = detail.code as string | undefined;
  }
}

function messageFrom(detail: Detail, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = d.loc?.filter((l) => l !== "body").join(".");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  if (detail?.message) return String(detail.message);
  return status >= 500 ? "Something went wrong on our side. Please try again." : `Request failed (${status})`;
}

let accessToken: string | null = null;
let orgId: string | null = null;
let onUnauthorized: (() => void) | null = null;
let refreshing: Promise<unknown> | null = null;

export const session = {
  setToken(t: string | null) {
    accessToken = t;
  },
  setOrg(id: string | null) {
    orgId = id;
  },
  get org() {
    return orgId;
  },
  get token() {
    return accessToken;
  },
  onUnauthorized(fn: () => void) {
    onUnauthorized = fn;
  },
};

type Opts = {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | boolean | null | undefined | string[]>;
  signal?: AbortSignal;
  raw?: boolean;
  headers?: Record<string, string>;
};

function buildUrl(path: string, params?: Opts["params"]) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => qs.append(k, x));
    else qs.set(k, String(v));
  }
  const q = qs.toString();
  return `/api/v1${path}${q ? `?${q}` : ""}`;
}

async function doFetch(path: string, opts: Opts) {
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (orgId) headers["X-Organization-Id"] = orgId;
  let body: BodyInit | undefined;
  if (opts.body instanceof FormData) body = opts.body;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  return fetch(buildUrl(path, opts.params), {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    headers,
    body,
    credentials: "include",
    signal: opts.signal,
  });
}

export async function refreshSession<T = unknown>(): Promise<T | null> {
  if (!refreshing) {
    refreshing = fetch("/api/v1/auth/refresh", { method: "POST", credentials: "include" })
      .then(async (r) => {
        if (!r.ok) {
          // A private demo hospital that expired or was reset: tell the visitor why they were signed out.
          try {
            const j = await r.json();
            if (j?.detail?.code === "demo_expired") sessionStorage.setItem("ud-demo-ended", "1");
          } catch { /* not JSON */ }
          return null;
        }
        const data = await r.json();
        accessToken = data.access_token;
        return data;
      })
      .finally(() => {
        setTimeout(() => (refreshing = null), 0);
      });
  }
  return refreshing as Promise<T | null>;
}

export async function api<T = unknown>(path: string, opts: Opts = {}): Promise<T> {
  let res = await doFetch(path, opts);
  if (res.status === 401 && !path.startsWith("/auth/login") && !path.startsWith("/auth/mfa/verify")) {
    const ok = await refreshSession();
    if (ok) res = await doFetch(path, opts);
    if (res.status === 401) {
      onUnauthorized?.();
    }
  }
  if (opts.raw) return res as unknown as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? data);
  return data as T;
}

export const get = <T>(path: string, params?: Opts["params"]) => api<T>(path, { params });
export const post = <T>(path: string, body?: unknown, headers?: Record<string, string>) => api<T>(path, { method: "POST", body: body ?? {}, headers });
export const put = <T>(path: string, body: unknown) => api<T>(path, { method: "PUT", body });
export const patch = <T>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body });
export const del = <T>(path: string) => api<T>(path, { method: "DELETE" });

/** Generated OpenAPI types (`npm run gen:api`). `Schema<"PatientOut">` → response/request model type. */
import type { components } from "./api-schema";
export type Schema<K extends keyof components["schemas"]> = components["schemas"][K];
