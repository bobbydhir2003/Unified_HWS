import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Laptop, ShieldAlert, ShieldCheck } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { KeyValue, PageHeader, toastError } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { del, get, patch, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, fromNow } from "@/lib/format";
import { type Me, ROLE_LABELS } from "@/lib/types";

function MfaCard() {
  const { me, setMe } = useAuth();
  const [setup, setSetup] = React.useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = React.useState("");
  const [pw, setPw] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const enabled = me?.user.mfa_enabled;
  return (
    <Card>
      <CardHeader>
        <div><CardTitle>Two-factor authentication</CardTitle><CardDescription>Use an authenticator app (TOTP) as a second sign-in step.</CardDescription></div>
        {enabled ? <Badge variant="success"><ShieldCheck />On</Badge> : <Badge variant="warning"><ShieldAlert />Off</Badge>}
      </CardHeader>
      <CardContent className="space-y-4">
        {!enabled && !setup && (
          <Button loading={busy} onClick={async () => { setBusy(true); try { setSetup(await post("/auth/mfa/setup")); } catch (e) { toastError(e); } finally { setBusy(false); } }}>
            <ShieldCheck />Set up two-factor
          </Button>
        )}
        {!enabled && setup && (
          <form className="grid gap-4 sm:grid-cols-[auto_1fr]" onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try { setMe(await post<Me>("/auth/mfa/enable", { code })); setSetup(null); setCode(""); toast.success("Two-factor authentication enabled"); }
            catch (err) { toastError(err); } finally { setBusy(false); }
          }}>
            <div className="rounded-lg border bg-white p-3"><QRCodeSVG value={setup.otpauth_uri} size={148} /></div>
            <div className="space-y-3">
              <p className="text-[13px]">1. Scan the QR code with your authenticator app, or enter this key manually:</p>
              <code className="block break-all rounded bg-muted px-2 py-1.5 font-mono text-xs">{setup.secret}</code>
              <Field label="2. Enter the 6-digit code">
                <Input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" className="max-w-40 tracking-widest tabular" />
              </Field>
              <div className="flex gap-2"><Button type="submit" loading={busy} disabled={code.length !== 6}>Verify & enable</Button><Button type="button" variant="ghost" onClick={() => setSetup(null)}>Cancel</Button></div>
            </div>
          </form>
        )}
        {enabled && (
          <form className="flex flex-wrap items-end gap-2" onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try { setMe(await post<Me>("/auth/mfa/disable", { password: pw, code })); setPw(""); setCode(""); toast.success("Two-factor disabled"); }
            catch (err) { toastError(err); } finally { setBusy(false); }
          }}>
            <Field label="Password"><Input type="password" value={pw} onChange={(e) => setPw(e.target.value)} className="w-48" /></Field>
            <Field label="Current code"><Input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} className="w-32 tabular" /></Field>
            <Button type="submit" variant="outline" loading={busy} disabled={!pw || code.length !== 6}>Turn off</Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

function PasswordCard() {
  const [cur, setCur] = React.useState("");
  const [next, setNext] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const mismatch = !!confirm && next !== confirm;
  return (
    <Card>
      <CardHeader><div><CardTitle>Password</CardTitle><CardDescription>Changing your password signs out your other sessions.</CardDescription></div></CardHeader>
      <CardContent>
        <form className="grid gap-3 sm:grid-cols-3" onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try { const r = await post<{ message: string }>("/auth/password/change", { current_password: cur, new_password: next }); toast.success(r.message); setCur(""); setNext(""); setConfirm(""); }
          catch (err) { toastError(err); } finally { setBusy(false); }
        }}>
          <Field label="Current password"><Input type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
          <Field label="New password" hint="10+ chars, 3 character types"><Input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} /></Field>
          <Field label="Confirm" error={mismatch ? "Doesn't match" : undefined}><Input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} /></Field>
          <div className="sm:col-span-3"><Button type="submit" loading={busy} disabled={!cur || next.length < 10 || next !== confirm}><KeyRound />Change password</Button></div>
        </form>
      </CardContent>
    </Card>
  );
}

type Sess = { id: string; user_agent: string | null; ip_address: string | null; created_at: string; last_used_at: string; current: boolean };

function SessionsCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["sessions"], queryFn: () => get<Sess[]>("/auth/sessions") });
  const browser = (ua: string | null) => {
    if (!ua) return "Unknown device";
    const b = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "Browser";
    const os = /Mac OS/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /iPhone|iPad/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Linux/.test(ua) ? "Linux" : "";
    return `${b}${os ? ` on ${os}` : ""}`;
  };
  return (
    <Card>
      <CardHeader><div><CardTitle>Active sessions</CardTitle><CardDescription>Sign out devices you don't recognize.</CardDescription></div></CardHeader>
      <CardContent className="px-0 pb-2">
        <ul className="divide-y">
          {q.data?.map((s) => (
            <li key={s.id} className="flex items-center gap-3 px-5 py-3">
              <Laptop className="size-5 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="text-[13.5px] font-medium">{browser(s.user_agent)} {s.current && <Badge variant="success" className="ml-1">This device</Badge>}</p>
                <p className="text-xs text-muted-foreground">{s.ip_address ?? "—"} · signed in {fmtDateTime(s.created_at)} · active {fromNow(s.last_used_at)}</p>
              </div>
              {!s.current && <Button size="xs" variant="outline" onClick={async () => { try { await del(`/auth/sessions/${s.id}`); qc.invalidateQueries({ queryKey: ["sessions"] }); toast.success("Session signed out"); } catch (e) { toastError(e); } }}>Sign out</Button>}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function AccountPage() {
  const { me, membership, setMe } = useAuth();
  const [params] = useSearchParams();
  const [first, setFirst] = React.useState(me?.user.first_name ?? "");
  const [last, setLast] = React.useState(me?.user.last_name ?? "");
  const [phone, setPhone] = React.useState(me?.user.phone ?? "");
  const [busy, setBusy] = React.useState(false);
  if (!me) return null;
  return (
    <>
      <PageHeader title="Account & security" description={me.user.email} />
      {(params.get("mfa") === "required" || me.mfa_enrollment_required) && (
        <div role="alert" className="mb-4 flex items-center gap-2 rounded-lg border border-warning/40 bg-warning-soft px-4 py-3 text-[13px]">
          <ShieldAlert className="size-4 text-warning" />Your role requires two-factor authentication. Set it up below to continue using Undeclared.
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><div><CardTitle>Profile</CardTitle></div></CardHeader>
          <CardContent>
            <form className="grid gap-3 sm:grid-cols-2" onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try { setMe(await patch<Me>("/auth/me", { first_name: first, last_name: last, phone: phone || null })); toast.success("Profile updated"); }
              catch (err) { toastError(err); } finally { setBusy(false); }
            }}>
              <Field label="First name"><Input value={first} onChange={(e) => setFirst(e.target.value)} /></Field>
              <Field label="Last name"><Input value={last} onChange={(e) => setLast(e.target.value)} /></Field>
              <Field label="Phone"><Input value={phone} onChange={(e) => setPhone(e.target.value)} /></Field>
              <div className="flex items-end"><Button type="submit" loading={busy}>Save profile</Button></div>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><div><CardTitle>Organization access</CardTitle></div></CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-4">
              <KeyValue label="Organization" value={membership?.organization_name} />
              <KeyValue label="Roles" value={membership?.roles.map((r) => ROLE_LABELS[r]).join(", ")} />
              <KeyValue label="Locations" value={membership?.clinics.map((c) => c.name).join(", ")} className="col-span-2" />
              <KeyValue label="Last sign-in" value={fmtDateTime(me.user.last_login_at)} />
            </dl>
          </CardContent>
        </Card>
        <MfaCard />
        <PasswordCard />
        <div className="lg:col-span-2"><SessionsCard /></div>
      </div>
    </>
  );
}
