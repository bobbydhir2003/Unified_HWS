import { useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { post, refreshSession, session } from "./api";
import type { ClinicBrief, Me, Membership, Role, Workspace } from "./types";

type TokenResponse = { status: "ok"; access_token: string; me: Me };
type MfaChallenge = { status: "mfa_required"; mfa_token: string };

type AuthState = {
  status: "loading" | "anonymous" | "authenticated";
  me: Me | null;
  /** The membership as the app should use it: narrowed to the selected workspace (role) when one is chosen. */
  membership: Membership | null;
  /** The membership exactly as granted (all of the person's roles). */
  baseMembership: Membership | null;
  /** Selected workspace role, or null for the person's own roles. */
  workspace: Role | null;
  workspaces: Workspace[];
  switchWorkspace(role: Role | null): void;
  clinic: ClinicBrief | null;
  login(email: string, password: string): Promise<{ mfaToken?: string }>;
  verifyMfa(mfaToken: string, code: string): Promise<void>;
  acceptTokens(data: TokenResponse): void;
  logout(): Promise<void>;
  setMe(me: Me): void;
  switchOrg(orgId: string): void;
  switchClinic(clinicId: string): void;
  can(perm: string): boolean;
  hasRole(...roles: Role[]): boolean;
};

const Ctx = createContext<AuthState | null>(null);
const ORG_KEY = "ud-org";
const CLINIC_KEY = "ud-clinic";
const wsKey = (userId: string) => `ud-workspace:${userId}`;

/** A stored workspace is only used if the server still lists it for this person (the server enforces it again). */
function allowedWorkspace(m: Membership | undefined, stored: string | null): Role | null {
  if (!stored || !m?.workspaces?.some((w) => w.role === stored)) return null;
  return stored as Role;
}

function store(key: string, value?: string | null) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage unavailable */
  }
  return null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [me, setMeState] = useState<Me | null>(null);
  const [orgId, setOrgId] = useState<string | null>(() => store(ORG_KEY));
  const [clinicId, setClinicId] = useState<string | null>(() => store(CLINIC_KEY));

  const [workspace, setWorkspace] = useState<Role | null>(null);

  const baseMembership = useMemo(() => {
    if (!me) return null;
    return me.memberships.find((m) => m.organization_id === orgId) ?? me.memberships[0] ?? null;
  }, [me, orgId]);

  const membership = useMemo(() => {
    if (!baseMembership) return null;
    const ws = workspace ? baseMembership.workspaces?.find((w) => w.role === workspace) : undefined;
    return ws ? { ...baseMembership, roles: [ws.role], permissions: ws.permissions } : baseMembership;
  }, [baseMembership, workspace]);

  const clinic = useMemo(() => {
    if (!membership) return null;
    return membership.clinics.find((c) => c.id === clinicId) ?? membership.clinics[0] ?? null;
  }, [membership, clinicId]);

  useEffect(() => {
    session.setOrg(membership?.organization_id ?? null);
  }, [membership]);

  const acceptTokens = useCallback((data: TokenResponse) => {
    session.setToken(data.access_token);
    const m = data.me.memberships.find((x) => x.organization_id === store(ORG_KEY)) ?? data.me.memberships[0];
    session.setOrg(m?.organization_id ?? null);
    const ws = allowedWorkspace(m, store(wsKey(data.me.user.id)));
    session.setActingRole(ws);
    setWorkspace(ws);
    setMeState(data.me);
    setStatus("authenticated");
  }, []);

  useEffect(() => {
    session.onUnauthorized(() => {
      session.setToken(null);
      session.setActingRole(null);
      setMeState(null);
      setStatus("anonymous");
      qc.clear();
    });
    refreshSession<TokenResponse>().then((data) => {
      if (data) acceptTokens(data);
      else setStatus("anonymous");
    });
  }, [acceptTokens, qc]);

  // Keep the access token fresh while the tab is open.
  useEffect(() => {
    if (status !== "authenticated") return;
    const id = setInterval(() => {
      refreshSession<TokenResponse>().then((d) => d && setMeState(d.me));
    }, 12 * 60 * 1000);
    return () => clearInterval(id);
  }, [status]);

  const value: AuthState = {
    status,
    me,
    membership,
    baseMembership,
    workspace,
    workspaces: baseMembership?.workspaces ?? [],
    switchWorkspace(role) {
      if (!me) return;
      const ws = allowedWorkspace(baseMembership ?? undefined, role);
      store(wsKey(me.user.id), ws);
      session.setActingRole(ws);
      setWorkspace(ws);
      qc.clear(); // every screen refetches with the new workspace's permissions
    },
    clinic,
    acceptTokens,
    async login(email, password) {
      const data = await post<TokenResponse | MfaChallenge>("/auth/login", { email, password });
      if (data.status === "mfa_required") return { mfaToken: data.mfa_token };
      acceptTokens(data);
      return {};
    },
    async verifyMfa(mfaToken, code) {
      acceptTokens(await post<TokenResponse>("/auth/mfa/verify", { mfa_token: mfaToken, code }));
    },
    async logout() {
      try {
        await post("/auth/logout");
      } finally {
        session.setToken(null);
        session.setActingRole(null);
        setWorkspace(null);
        setMeState(null);
        setStatus("anonymous");
        qc.clear();
      }
    },
    setMe: setMeState,
    switchOrg(id) {
      store(ORG_KEY, id);
      store(CLINIC_KEY, null);
      session.setOrg(id);
      setOrgId(id);
      setClinicId(null);
      qc.clear();
    },
    switchClinic(id) {
      store(CLINIC_KEY, id);
      setClinicId(id);
    },
    can: (perm) => !!membership?.permissions.includes(perm),
    hasRole: (...roles) => !!membership?.roles.some((r) => roles.includes(r)),
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
