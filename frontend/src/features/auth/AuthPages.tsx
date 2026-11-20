import { zodResolver } from "@hookform/resolvers/zod";
import { LegalFooter } from "@/components/common/LegalFooter";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CalendarCheck2, FileCheck2, ShieldCheck, Sparkles } from "lucide-react";
import * as React from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";
import { ErrorState } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ApiError, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ROLE_LABELS, type Role } from "@/lib/types";

function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-sidebar p-12 text-white lg:flex lg:flex-col">
        <div className="pointer-events-none absolute -right-40 -top-40 size-[34rem] rounded-full bg-blue-500/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-48 -left-24 size-[30rem] rounded-full bg-indigo-400/10 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 shadow-lg shadow-blue-950/40">
            <svg viewBox="0 0 32 32" className="size-6" aria-hidden><path d="M10 9v8a6 6 0 0 0 12 0V9" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" /><circle cx="16" cy="24.5" r="1.8" fill="#bfdbfe" /></svg>
          </span>
          <span className="text-lg font-semibold tracking-tight">Undeclared</span>
        </div>
        <div className="relative mt-auto max-w-md">
          <h2 className="text-3xl font-semibold leading-tight tracking-tight">Clinical work, without the clutter.</h2>
          <p className="mt-3 text-[15px] leading-relaxed text-sidebar-foreground">
            Scheduling, charting and AI-assisted documentation in one calm, fast workspace — with clinicians always in control.
          </p>
          <ul className="mt-8 space-y-3 text-[14px] text-sidebar-foreground">
            {[
              [CalendarCheck2, "Conflict-safe scheduling and a live waiting room"],
              [FileCheck2, "Versioned notes that can't be silently changed once signed"],
              [Sparkles, "AI drafts that always require clinician review"],
              [ShieldCheck, "Role-based access, MFA and a tamper-evident audit trail"],
            ].map(([Icon, text], i) => {
              const I = Icon as typeof ShieldCheck;
              return <li key={i} className="flex items-center gap-3"><span className="rounded-lg bg-white/10 p-1.5"><I className="size-4" /></span>{text as string}</li>;
            })}
          </ul>
        </div>
        <p className="relative mt-12 text-xs text-sidebar-muted">Development build · synthetic data only · not certified for clinical use</p>
      </aside>
      <main className="flex items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-sm">{children}<LegalFooter className="mt-8 px-0" /></div>
      </main>
    </div>
  );
}

const loginSchema = z.object({ email: z.email("Enter a valid email"), password: z.string().min(1, "Enter your password") });


/* Quick role login. Local dev server: always on, every role, documented dev password.
 * Other builds: off unless VITE_DEMO_LOGIN=true (an isolated, synthetic-data demo environment). There, administrator
 * roles are never offered and a password is filled only if VITE_DEMO_PASSWORD is set for that demo. Buttons only fill
 * the normal sign-in form — authentication, MFA, lockout and audit are unchanged. */
const DEMO_LOGIN = import.meta.env.DEV || import.meta.env.VITE_DEMO_LOGIN === "true";
const DEMO_PASSWORD: string = import.meta.env.DEV ? "Undeclared!2026" : (import.meta.env.VITE_DEMO_PASSWORD ?? "");
// Administrator accounts exist in the list only in dev-server builds (compiled out everywhere else).
const DEMO_ACCOUNTS: [string, string][] = !DEMO_LOGIN ? [] : [
  ["dr.chen@harborview.dev", "Doctor"],
  ["nurse.rivera@harborview.dev", "Nurse"],
  ["frontdesk@harborview.dev", "Front desk"],
  ...(import.meta.env.DEV ? [["clinicadmin@harborview.dev", "Clinic admin"] as [string, string]] : []),
  ["billing@harborview.dev", "Billing"],
  ["patient@harborview.dev", "Patient"],
  ...(import.meta.env.DEV ? [["admin@undeclared.dev", "Super admin"] as [string, string]] : []),
];

export function LoginPage() {
  const { login, verifyMfa } = useAuth();
  const navigate = useNavigate();
  const [mfaToken, setMfaToken] = React.useState<string | null>(null);
  const [code, setCode] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const form = useForm({ resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "" } });

  const onSubmit = form.handleSubmit(async (v) => {
    setError(null);
    setBusy(true);
    try {
      const r = await login(v.email, v.password);
      if (r.mfaToken) setMfaToken(r.mfaToken);
      else navigate("/", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  });

  const onMfa = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await verifyMfa(mfaToken!, code);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
      if (err instanceof ApiError && err.message.includes("expired")) setMfaToken(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout>
      {mfaToken ? (
        <form onSubmit={onMfa} className="space-y-5">
          <div>
            <div className="mb-4 inline-flex rounded-xl bg-accent p-2.5 text-accent-foreground"><ShieldCheck className="size-5" /></div>
            <h1 className="text-2xl font-semibold tracking-tight">Two-factor verification</h1>
            <p className="mt-1 text-[13.5px] text-muted-foreground">Enter the 6-digit code from your authenticator app.</p>
          </div>
          <Field label="Verification code" error={error ?? undefined}>
            <Input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric"
              autoComplete="one-time-code" autoFocus className="h-11 text-center text-lg tracking-[0.5em] tabular" />
          </Field>
          <Button type="submit" className="w-full" size="lg" loading={busy} disabled={code.length !== 6}>Verify</Button>
          <Button type="button" variant="ghost" className="w-full" onClick={() => { setMfaToken(null); setCode(""); }}>
            <ArrowLeft />Back to sign in
          </Button>
        </form>
      ) : (
        <>
          <form onSubmit={onSubmit} className="space-y-5" noValidate>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
              <p className="mt-1 text-[13.5px] text-muted-foreground">Welcome back. Sign in to your workspace.</p>
            </div>
            {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive-soft px-3 py-2 text-[13px] text-destructive">{error}</div>}
            <Field label="Email" error={form.formState.errors.email?.message}>
              <Input type="email" autoComplete="username" autoFocus {...form.register("email")} />
            </Field>
            <Field label="Password" error={form.formState.errors.password?.message}>
              <Input type="password" autoComplete="current-password" {...form.register("password")} />
            </Field>
            <div className="flex justify-end -mt-2">
              <Link to="/forgot-password" className="text-[13px] font-medium text-primary hover:underline">Forgot password?</Link>
            </div>
            <Button type="submit" className="w-full" size="lg" loading={busy}>Sign in</Button>
          </form>
          {DEMO_LOGIN && (
            <div className="mt-8 rounded-xl border border-dashed p-3" data-testid="demo-accounts">
              <p className="mb-2 text-xs font-medium text-muted-foreground">
                {import.meta.env.DEV ? "Development accounts" : "Demo accounts (synthetic data)"}
                {DEMO_PASSWORD ? <> · password <code className="rounded bg-muted px-1">{DEMO_PASSWORD}</code></> : " · ask your administrator for the demo password"}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {DEMO_ACCOUNTS.map(([email, label]) => (
                  <button key={email} type="button" className="rounded-md border bg-card px-2 py-1 text-xs hover:bg-muted"
                    onClick={() => { form.setValue("email", email); if (DEMO_PASSWORD) form.setValue("password", DEMO_PASSWORD); else form.setFocus("password"); }}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </AuthLayout>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = React.useState("");
  const [sent, setSent] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  return (
    <AuthLayout>
      <div className="space-y-5">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Reset your password</h1>
          <p className="mt-1 text-[13.5px] text-muted-foreground">We'll email you a link to choose a new password.</p>
        </div>
        {sent ? (
          <div className="rounded-lg border bg-success-soft px-3 py-3 text-[13px] text-success">
            {sent}
            {import.meta.env.DEV && <p className="mt-1 text-foreground/70">Dev: email delivery is simulated — an admin can see the link in Admin › Message outbox.</p>}
          </div>
        ) : (
          <form className="space-y-4" onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try { setSent((await post<{ message: string }>("/auth/password/forgot", { email })).message); }
            catch (err) { toast.error(err instanceof Error ? err.message : "Request failed"); }
            finally { setBusy(false); }
          }}>
            <Field label="Email"><Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus /></Field>
            <Button type="submit" className="w-full" size="lg" loading={busy}>Send reset link</Button>
          </form>
        )}
        <Link to="/login" className="inline-flex items-center gap-1 text-[13px] font-medium text-primary hover:underline"><ArrowLeft className="size-3.5" />Back to sign in</Link>
      </div>
    </AuthLayout>
  );
}

const pwSchema = z.object({
  password: z.string().min(10, "At least 10 characters"),
  confirm: z.string(),
}).refine((v) => v.password === v.confirm, { message: "Passwords don't match", path: ["confirm"] });

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const form = useForm({ resolver: zodResolver(pwSchema), defaultValues: { password: "", confirm: "" } });
  const [error, setError] = React.useState<string | null>(null);
  return (
    <AuthLayout>
      <form className="space-y-5" onSubmit={form.handleSubmit(async (v) => {
        setError(null);
        try {
          const r = await post<{ message: string }>("/auth/password/reset", { token: params.get("token"), password: v.password });
          toast.success(r.message);
          navigate("/login");
        } catch (e) { setError(e instanceof Error ? e.message : "Reset failed"); }
      })}>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Choose a new password</h1>
          <p className="mt-1 text-[13.5px] text-muted-foreground">Use 10+ characters with a mix of letters, numbers and symbols.</p>
        </div>
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive-soft px-3 py-2 text-[13px] text-destructive">{error}</div>}
        <Field label="New password" error={form.formState.errors.password?.message}><Input type="password" autoComplete="new-password" {...form.register("password")} /></Field>
        <Field label="Confirm password" error={form.formState.errors.confirm?.message}><Input type="password" autoComplete="new-password" {...form.register("confirm")} /></Field>
        <Button type="submit" className="w-full" size="lg" loading={form.formState.isSubmitting}>Update password</Button>
      </form>
    </AuthLayout>
  );
}

export function AcceptInvitePage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { acceptTokens } = useAuth();
  const navigate = useNavigate();
  const inv = useQuery({
    queryKey: ["invite", token],
    queryFn: () => get<{ email: string; first_name: string; organization_name: string; roles: Role[]; existing_account: boolean }>(`/auth/invitations/${token}`),
    retry: false,
  });
  const [password, setPassword] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  return (
    <AuthLayout>
      {inv.isLoading ? <p className="text-muted-foreground">Loading invitation…</p> : inv.error ? <ErrorState error={inv.error} /> : inv.data && (
        <form className="space-y-5" onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            acceptTokens(await post("/auth/invitations/accept", { token, password }));
            navigate("/", { replace: true });
          } catch (err) { setError(err instanceof Error ? err.message : "Couldn't accept invitation"); }
          finally { setBusy(false); }
        }}>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Join {inv.data.organization_name}</h1>
            <p className="mt-1 text-[13.5px] text-muted-foreground">
              Hi {inv.data.first_name} — you've been invited as {inv.data.roles.map((r) => ROLE_LABELS[r]).join(", ")}.
            </p>
          </div>
          {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive-soft px-3 py-2 text-[13px] text-destructive">{error}</div>}
          <Field label="Email"><Input value={inv.data.email} disabled /></Field>
          <Field label={inv.data.existing_account ? "Your existing password" : "Create a password"}
            hint={inv.data.existing_account ? "You already have an Undeclared account." : "10+ characters, mixing letters, numbers and symbols."}>
            <Input type="password" autoComplete={inv.data.existing_account ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Button type="submit" className="w-full" size="lg" loading={busy} disabled={!password}>Accept invitation</Button>
        </form>
      )}
    </AuthLayout>
  );
}
