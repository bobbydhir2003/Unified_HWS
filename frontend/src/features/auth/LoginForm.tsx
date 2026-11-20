import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, ArrowRight, Eye, EyeOff, Lock, Mail, ShieldCheck } from "lucide-react";
import * as React from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, inputBase } from "@/components/ui/input";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const loginSchema = z.object({ email: z.email("Enter a valid email"), password: z.string().min(1, "Enter your password") });

/* Quick role login. Local dev server: always on, every role, documented dev password.
 * Other builds: off unless VITE_DEMO_LOGIN=true (an isolated, synthetic-data demo environment). There, administrator
 * roles are never offered and a password is filled only if VITE_DEMO_PASSWORD is set for that demo. The default
 * production build (the public site) compiles it out entirely. Buttons only fill the normal sign-in form. */
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

type IconInputProps = React.ComponentProps<"input"> & { icon: React.ElementType; trailing?: React.ReactNode };

/** Input with a leading icon; forwards id/aria props from <Field> to the real input. */
function IconInput({ icon: Icon, trailing, className, ...props }: IconInputProps) {
  return (
    <div className="relative">
      <Icon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <input className={cn(inputBase, "h-11 pl-9", trailing && "pr-11", className)} {...props} />
      {trailing && <div className="absolute right-1.5 top-1/2 -translate-y-1/2">{trailing}</div>}
    </div>
  );
}

export function LoginForm({ autoFocus = false, emailId, heading }: { autoFocus?: boolean; emailId?: string; heading?: React.ReactNode }) {
  const { login, verifyMfa } = useAuth();
  const navigate = useNavigate();
  const [mfaToken, setMfaToken] = React.useState<string | null>(null);
  const [code, setCode] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [show, setShow] = React.useState(false);
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

  if (mfaToken) {
    return (
      <form onSubmit={onMfa} className="space-y-5">
        <div>
          <div className="mb-4 inline-flex rounded-xl bg-accent p-2.5 text-accent-foreground"><ShieldCheck className="size-5" /></div>
          <h2 className="text-2xl font-semibold tracking-tight">Two-factor verification</h2>
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
    );
  }

  return (
    <>
      <form onSubmit={onSubmit} className="space-y-4" noValidate aria-label="Sign in">
        {heading ?? (
          <div>
            <h2 className="text-[26px] font-semibold leading-tight tracking-tight">Sign in to <span className="text-primary">Undeclared</span></h2>
            <p className="mt-1 text-[14px] text-muted-foreground">Access your hospital workspace.</p>
          </div>
        )}
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive-soft px-3 py-2 text-[13px] text-destructive">{error}</div>}
        <Field label="Email" error={form.formState.errors.email?.message}>
          <IconInput id={emailId} icon={Mail} type="email" autoComplete="username" placeholder="you@hospital.org" autoFocus={autoFocus} {...form.register("email")} />
        </Field>
        <Field label="Password" error={form.formState.errors.password?.message}>
          <IconInput icon={Lock} type={show ? "text" : "password"} autoComplete="current-password" placeholder="Enter your password" {...form.register("password")}
            trailing={
              <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"} aria-pressed={show}
                className="grid size-8 place-items-center rounded-md text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
                {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            } />
        </Field>
        <div className="flex justify-end">
          <Link to="/forgot-password" className="text-[13px] font-medium text-primary hover:underline">Forgot password?</Link>
        </div>
        <Button type="submit" className="h-11 w-full text-[15px]" loading={busy}>Sign in<ArrowRight /></Button>
      </form>
      {DEMO_LOGIN && (
        <div className="mt-6 rounded-xl border border-dashed p-3" data-testid="demo-accounts">
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
  );
}
