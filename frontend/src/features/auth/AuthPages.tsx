import { zodResolver } from "@hookform/resolvers/zod";
import { LegalFooter } from "@/components/common/LegalFooter";
import { LogoMark } from "@/components/common/Logo";
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
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ROLE_LABELS, type Role } from "@/lib/types";

function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative isolate hidden overflow-hidden bg-sidebar p-12 text-white lg:flex lg:flex-col">
        <img src="/images/hospital-hero.webp" alt="" aria-hidden className="absolute inset-0 -z-10 h-full w-full object-cover object-[70%_center]" />
        <div className="absolute inset-0 -z-10 bg-gradient-to-br from-[#071a44]/95 via-[#0b2a66]/85 to-[#0b2a66]/50" aria-hidden />
        <div className="pointer-events-none absolute -right-40 -top-40 size-[34rem] rounded-full bg-blue-500/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-48 -left-24 size-[30rem] rounded-full bg-indigo-400/10 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <LogoMark size={40} />
          <span className="text-lg font-semibold tracking-tight">HMS Workflows</span>
        </div>
        <div className="relative mt-auto max-w-md">
          <h2 className="text-3xl font-semibold leading-tight tracking-tight">Clinical work, without the clutter.</h2>
          <p className="mt-3 text-section leading-relaxed text-sidebar-foreground">
            Scheduling, charting and AI-assisted documentation in one calm, fast workspace — with clinicians always in control.
          </p>
          <ul className="mt-8 space-y-3 text-body text-sidebar-foreground">
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
        <p className="relative mt-12 text-xs text-sidebar-muted">Demonstration build · synthetic data only · not certified for clinical use</p>
      </aside>
      <main className="flex items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-sm">{children}<LegalFooter className="mt-8 px-0" /></div>
      </main>
    </div>
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
          <p className="mt-1 text-body text-muted-foreground">We'll email you a link to choose a new password.</p>
        </div>
        {sent ? (
          <div className="rounded-lg border bg-success-soft px-3 py-3 text-table text-success">
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
        <Link to="/login" className="inline-flex items-center gap-1 text-table font-medium text-primary hover:underline"><ArrowLeft className="size-3.5" />Back to sign in</Link>
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
          <p className="mt-1 text-body text-muted-foreground">Use 10+ characters with a mix of letters, numbers and symbols.</p>
        </div>
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive-soft px-3 py-2 text-table text-destructive">{error}</div>}
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
            <p className="mt-1 text-body text-muted-foreground">
              Hi {inv.data.first_name} — you've been invited as {inv.data.roles.map((r) => ROLE_LABELS[r]).join(", ")}.
            </p>
          </div>
          {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive-soft px-3 py-2 text-table text-destructive">{error}</div>}
          <Field label="Email"><Input value={inv.data.email} disabled /></Field>
          <Field label={inv.data.existing_account ? "Your existing password" : "Create a password"}
            hint={inv.data.existing_account ? "You already have an HMS Workflows account." : "10+ characters, mixing letters, numbers and symbols."}>
            <Input type="password" autoComplete={inv.data.existing_account ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Button type="submit" className="w-full" size="lg" loading={busy} disabled={!password}>Accept invitation</Button>
        </form>
      )}
    </AuthLayout>
  );
}
