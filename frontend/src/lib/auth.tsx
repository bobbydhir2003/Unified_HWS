import { useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { post, refreshSession, session } from "./api";
import type { ClinicBrief, Me, Membership, Role } from "./types";

type TokenResponse = { status: "ok"; access_token: string; me: Me };
type MfaChallenge = { status: "mfa_required"; mfa_token: string };

type AuthState = {
  status: "loading" | "anonymous" | "authenticated";
  me: Me | null;
  membership: Membership | null;
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

  const membership = useMemo(() => {
    if (!me) return null;
    return me.memberships.find((m) => m.organization_id === orgId) ?? me.memberships[0] ?? null;
  }, [me, orgId]);

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
    setMeState(data.me);
    setStatus("authenticated");
  }, []);

  useEffect(() => {
    session.onUnauthorized(() => {
      session.setToken(null);
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
