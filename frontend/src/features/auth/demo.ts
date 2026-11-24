import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** Server demo mode (DEMO_MODE on a synthetic-data deployment): allowlisted accounts, one-click sign-in through
 *  POST /auth/demo-login. Shared by the /login page and the public "Explore the demo" section — one implementation. */
export type DemoAccount = { key: string; label: string; role: string; featured?: boolean };

export function useDemoAccounts() {
  const q = useQuery({
    queryKey: ["auth", "demo"], queryFn: () => get<{ enabled: boolean; accounts: DemoAccount[] }>("/auth/demo"),
    staleTime: 5 * 60_000, retry: false,
  });
  const accounts = q.data?.enabled && q.data.accounts.length ? q.data.accounts : null;
  return { accounts, isLoading: q.isLoading };
}

export function useDemoLogin() {
  const { acceptTokens } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const signIn = React.useCallback(async (key: string) => {
    setError(null);
    setBusy(key);
    try {
      acceptTokens(await post<Parameters<typeof acceptTokens>[0]>("/auth/demo-login", { key }));
      navigate("/", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Demo sign-in failed. Please try again.");
    } finally {
      setBusy(null);
    }
  }, [acceptTokens, navigate]);
  return { signIn, busy, error };
}
