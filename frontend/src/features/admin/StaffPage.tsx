import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, MailPlus, MoreHorizontal, Search, ShieldCheck, Stethoscope, UserCog, XCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState, LoadingRows, PageHeader, toastError, useConfirm } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, NativeSelect } from "@/components/ui/input";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/menu";
import { Avatar, Checkbox, Switch } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { del, get, patch, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fromNow } from "@/lib/format";
import { useClinics } from "@/lib/hooks";
import { ROLE_LABELS, type Role } from "@/lib/types";

type Staff = {
  membership_id: string; user_id: string; email: string; first_name: string; last_name: string; title: string | null; roles: Role[];
  is_active: boolean; all_clinics: boolean; clinic_ids: string[]; mfa_enabled: boolean; last_login_at: string | null;
  provider: { id: string; npi: string | null; specialty: string | null; credentials: string | null; color: string; is_active: boolean } | null;
};
type Invitation = { id: string; email: string; first_name: string; last_name: string; roles: Role[]; expires_at: string; accepted_at: string | null; revoked_at: string | null; created_at: string };

const STAFF_ROLES: Role[] = ["clinic_admin", "doctor", "nurse", "receptionist", "billing"];

function RolePicker({ value, onChange, allowSuper }: { value: Role[]; onChange: (r: Role[]) => void; allowSuper: boolean }) {
  const roles = allowSuper ? (["super_admin", ...STAFF_ROLES] as Role[]) : STAFF_ROLES;
  return (
    <div className="grid grid-cols-2 gap-2">
      {roles.map((r) => (
        <label key={r} className="flex items-center gap-2 rounded-lg border px-3 py-2 text-[13px] has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-accent/50">
          <Checkbox checked={value.includes(r)} onCheckedChange={(c) => onChange(c ? [...value, r] : value.filter((x) => x !== r))} />{ROLE_LABELS[r]}
        </label>
      ))}
    </div>
  );
}

function InviteDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const clinics = useClinics();
  const [f, setF] = React.useState({ email: "", first_name: "", last_name: "" });
  const [roles, setRoles] = React.useState<Role[]>(["receptionist"]);
  const [allClinics, setAllClinics] = React.useState(true);
  const [clinicIds, setClinicIds] = React.useState<string[]>([]);
  const [link, setLink] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (open) { setF({ email: "", first_name: "", last_name: "" }); setRoles(["receptionist"]); setLink(null); setAllClinics(true); setClinicIds([]); } }, [open]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader><DialogTitle>Invite staff member</DialogTitle><DialogDescription>They'll receive a link valid for 7 days to set a password and join.</DialogDescription></DialogHeader>
        {link ? (
          <div className="space-y-3">
            <div className="rounded-lg border bg-success-soft p-3 text-[13px] text-success">Invitation created for {f.email}.</div>
            <p className="text-[13px] text-muted-foreground">Email delivery is simulated in this environment. Share this link securely:</p>
            <div className="flex gap-2"><Input readOnly value={link} className="font-mono text-xs" /><Button variant="outline" size="icon" aria-label="Copy link" onClick={() => { navigator.clipboard.writeText(link); toast.success("Copied"); }}><Copy /></Button></div>
            <DialogFooter><Button onClick={() => onOpenChange(false)}>Done</Button></DialogFooter>
          </div>
        ) : (
          <form className="grid gap-4" onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try {
              const r = await post<{ invite_link: string }>("/invitations", { ...f, roles, clinic_ids: allClinics ? null : clinicIds });
              setLink(r.invite_link);
              qc.invalidateQueries({ queryKey: ["invitations"] });
            } catch (err) { toastError(err); } finally { setBusy(false); }
          }}>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="First name" required><Input value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} required /></Field>
              <Field label="Last name" required><Input value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} required /></Field>
              <Field label="Work email" required className="sm:col-span-2"><Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required /></Field>
            </div>
            <div><p className="mb-2 text-[13px] font-medium">Roles</p><RolePicker value={roles} onChange={setRoles} allowSuper={can("org:manage")} /></div>
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-[13px]"><Switch checked={allClinics} onCheckedChange={setAllClinics} />Access to all locations</label>
              {!allClinics && clinics.data?.map((c) => (
                <label key={c.id} className="flex items-center gap-2 pl-1 text-[13px]"><Checkbox checked={clinicIds.includes(c.id)} onCheckedChange={(v) => setClinicIds(v ? [...clinicIds, c.id] : clinicIds.filter((x) => x !== c.id))} />{c.name}</label>
              ))}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button type="submit" loading={busy} disabled={!roles.length || (!allClinics && !clinicIds.length)}><MailPlus />Send invitation</Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function EditStaffDialog({ s, onOpenChange }: { s: Staff | null; onOpenChange: (o: boolean) => void }) {
  const { can, me } = useAuth();
  const qc = useQueryClient();
  const clinics = useClinics();
  const [roles, setRoles] = React.useState<Role[]>([]);
  const [active, setActive] = React.useState(true);
  const [allClinics, setAllClinics] = React.useState(true);
  const [clinicIds, setClinicIds] = React.useState<string[]>([]);
  const [title, setTitle] = React.useState("");
  const [isProvider, setIsProvider] = React.useState(false);
  const [prov, setProv] = React.useState({ npi: "", specialty: "", credentials: "", color: "blue" });
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => {
    if (!s) return;
    setRoles(s.roles); setActive(s.is_active); setAllClinics(s.all_clinics); setClinicIds(s.clinic_ids); setTitle(s.title ?? "");
    setIsProvider(!!s.provider?.is_active);
    setProv({ npi: s.provider?.npi ?? "", specialty: s.provider?.specialty ?? "", credentials: s.provider?.credentials ?? "", color: s.provider?.color ?? "blue" });
  }, [s]);
  if (!s) return null;
  const self = s.user_id === me?.user.id;
  return (
    <Dialog open={!!s} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader><DialogTitle>{s.first_name} {s.last_name}</DialogTitle><DialogDescription>{s.email}</DialogDescription></DialogHeader>
        <form className="grid gap-5" onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await patch(`/staff/${s.membership_id}`, {
              roles, is_active: active, all_clinics: allClinics, clinic_ids: allClinics ? [] : clinicIds, title,
              provider: isProvider || s.provider ? { npi: prov.npi || null, specialty: prov.specialty || null, credentials: prov.credentials || null, color: prov.color, is_active: isProvider } : undefined,
            });
            qc.invalidateQueries({ queryKey: ["staff"] });
            qc.invalidateQueries({ queryKey: ["providers"] });
            toast.success("Staff member updated");
            onOpenChange(false);
          } catch (err) { toastError(err); } finally { setBusy(false); }
        }}>
          <div><p className="mb-2 text-[13px] font-medium">Roles</p><RolePicker value={roles} onChange={setRoles} allowSuper={can("org:manage")} /></div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Professional title" hint="Shown after their name, e.g. MD, RN"><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
            <div className="space-y-2 pt-6">
              <label className="flex items-center gap-2 text-[13px]"><Switch checked={active} onCheckedChange={setActive} disabled={self} />Account active{self && <span className="text-xs text-muted-foreground">(you)</span>}</label>
              <label className="flex items-center gap-2 text-[13px]"><Switch checked={allClinics} onCheckedChange={setAllClinics} />All locations</label>
            </div>
          </div>
          {!allClinics && (
            <div className="flex flex-wrap gap-3">{clinics.data?.map((c) => (
              <label key={c.id} className="flex items-center gap-2 text-[13px]"><Checkbox checked={clinicIds.includes(c.id)} onCheckedChange={(v) => setClinicIds(v ? [...clinicIds, c.id] : clinicIds.filter((x) => x !== c.id))} />{c.name}</label>
            ))}</div>
          )}
          <div className="rounded-lg border p-4">
            <label className="flex items-center gap-2 text-[13px] font-medium"><Switch checked={isProvider} onCheckedChange={setIsProvider} /><Stethoscope className="size-4" />Schedulable provider</label>
            {isProvider && (
              <div className="mt-3 grid gap-3 sm:grid-cols-4">
                <Field label="NPI" hint="10 digits"><Input value={prov.npi} onChange={(e) => setProv({ ...prov, npi: e.target.value.replace(/\D/g, "").slice(0, 10) })} /></Field>
                <Field label="Specialty"><Input value={prov.specialty} onChange={(e) => setProv({ ...prov, specialty: e.target.value })} /></Field>
                <Field label="Credentials"><Input value={prov.credentials} onChange={(e) => setProv({ ...prov, credentials: e.target.value })} /></Field>
                <Field label="Calendar color">
                  <NativeSelect value={prov.color} onChange={(e) => setProv({ ...prov, color: e.target.value })}>
                    {["blue", "violet", "emerald", "amber", "rose", "cyan", "slate"].map((c) => <option key={c} value={c}>{c}</option>)}
                  </NativeSelect>
                </Field>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" loading={busy} disabled={!roles.length}>Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function StaffPage() {
  const qc = useQueryClient();
  const { confirm, dialog } = useConfirm();
  const [q, setQ] = React.useState("");
  const [inviteOpen, setInviteOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<Staff | null>(null);
  const staff = useQuery({ queryKey: ["staff"], queryFn: () => get<Staff[]>("/staff") });
  const invites = useQuery({ queryKey: ["invitations"], queryFn: () => get<Invitation[]>("/invitations") });
  const pending = (invites.data ?? []).filter((i) => !i.accepted_at && !i.revoked_at && new Date(i.expires_at) > new Date());
  const rows = (staff.data ?? []).filter((s) => !q || `${s.first_name} ${s.last_name} ${s.email}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      {dialog}
      <PageHeader title="Staff & roles" description="Manage who can access this organization and what they can do."
        actions={<Button onClick={() => setInviteOpen(true)}><MailPlus />Invite staff</Button>} />
      <Card className="overflow-hidden">
        <div className="border-b p-3">
          <div className="relative max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search staff" className="pl-9" aria-label="Search staff" />
          </div>
        </div>
        {staff.error ? <ErrorState error={staff.error} /> : staff.isLoading ? <LoadingRows /> : !rows.length ? <EmptyState title="No staff found" /> : (
          <Table>
            <THead><TR><TH>Name</TH><TH>Roles</TH><TH className="hidden md:table-cell">Security</TH><TH className="hidden lg:table-cell">Last sign-in</TH><TH>Status</TH><TH className="w-10" /></TR></THead>
            <TBody>
              {rows.map((s) => (
                <TR key={s.membership_id}>
                  <TD>
                    <div className="flex items-center gap-3">
                      <Avatar name={`${s.first_name} ${s.last_name}`} />
                      <div><p className="font-medium">{s.first_name} {s.last_name}{s.title ? `, ${s.title}` : ""}</p><p className="text-xs text-muted-foreground">{s.email}</p></div>
                    </div>
                  </TD>
                  <TD><div className="flex flex-wrap gap-1">{s.roles.map((r) => <Badge key={r} variant={r === "super_admin" || r === "clinic_admin" ? "primary" : "neutral"}>{ROLE_LABELS[r]}</Badge>)}{s.provider?.is_active && <Badge variant="outline"><Stethoscope />Provider</Badge>}</div></TD>
                  <TD className="hidden md:table-cell">{s.mfa_enabled ? <Badge variant="success"><ShieldCheck />MFA</Badge> : <span className="text-xs text-muted-foreground">Password only</span>}</TD>
                  <TD className="hidden text-muted-foreground lg:table-cell">{s.last_login_at ? fromNow(s.last_login_at) : "Never"}</TD>
                  <TD>{s.is_active ? <Badge variant="success">Active</Badge> : <Badge variant="danger">Deactivated</Badge>}</TD>
                  <TD><Button variant="ghost" size="icon-sm" onClick={() => setEditing(s)} aria-label={`Edit ${s.first_name}`}><UserCog /></Button></TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
      <Card className="mt-5">
        <CardHeader><CardTitle>Pending invitations</CardTitle></CardHeader>
        <CardContent className="px-0 pb-2">
          {!pending.length ? <p className="px-5 pb-3 text-[13px] text-muted-foreground">No pending invitations.</p> : (
            <ul className="divide-y">
              {pending.map((i) => (
                <li key={i.id} className="flex items-center gap-3 px-5 py-2.5">
                  <div className="min-w-0 flex-1"><p className="text-[13.5px] font-medium">{i.first_name} {i.last_name} <span className="font-normal text-muted-foreground">· {i.email}</span></p>
                    <p className="text-xs text-muted-foreground">{i.roles.map((r) => ROLE_LABELS[r]).join(", ")} · expires {fmtDate(i.expires_at)}</p></div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="Invitation actions"><MoreHorizontal /></Button></DropdownMenuTrigger>
                    <DropdownMenuContent>
                      <DropdownMenuItem destructive onSelect={async () => {
                        if (!(await confirm({ title: `Revoke invitation for ${i.email}?`, destructive: true, confirmLabel: "Revoke" }))) return;
                        try { await del(`/invitations/${i.id}`); qc.invalidateQueries({ queryKey: ["invitations"] }); toast.success("Invitation revoked"); } catch (e) { toastError(e); }
                      }}><XCircle />Revoke</DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <InviteDialog open={inviteOpen} onOpenChange={setInviteOpen} />
      <EditStaffDialog s={editing} onOpenChange={(o) => !o && setEditing(null)} />
    </>
  );
}
