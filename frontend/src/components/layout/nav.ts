import {
  Activity, BedDouble, Wrench, CalendarClock, Scissors, FileCheck2, FlaskConical, ScanLine, KeyRound, Lightbulb, LifeBuoy, Pill, Siren, HeartHandshake, Hospital, BarChart3, Bot, Building2, CalendarDays, ClipboardList, ClipboardPen, FileStack, HeartPulse, Inbox, LayoutDashboard, ListChecks, Radar, Sparkles,
  type LucideIcon, Mail, MessageSquare, PhoneCall, Receipt, ScrollText, ServerCog, Settings2, ShieldCheck, Stethoscope, Users, UsersRound, Workflow,
} from "lucide-react";

export type NavItem = { to: string; label: string; icon: LucideIcon; perm?: string; any?: string[]; providerOnly?: boolean };
export type NavSection = { title?: string; items: NavItem[] };

/** One shell for every staff role; items appear only when the role has the permission (the server enforces it again). */
export const NAV: NavSection[] = [
  {
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard },
      { to: "/command", label: "Command Center", icon: Radar, any: ["command:view", "automation:manage"] },
      { to: "/worklist", label: "My work", icon: Inbox, perm: "cases:read" },
      { to: "/front-desk", label: "Front desk", icon: ClipboardList, perm: "schedule:write" },
      { to: "/schedule", label: "Schedule", icon: CalendarDays, perm: "schedule:read" },
      { to: "/patients", label: "Patients", icon: UsersRound, perm: "patients:read" },
      { to: "/encounters", label: "My Visits", icon: Stethoscope, perm: "clinical:read" },
      { to: "/messages", label: "Messages", icon: MessageSquare, perm: "messages:use" },
      { to: "/orders", label: "Orders", icon: ClipboardPen, perm: "clinical:read" },
      { to: "/documents", label: "Documents", icon: FileStack, perm: "documents:read" },
      { to: "/tasks", label: "Tasks", icon: ListChecks, perm: "patients:read" },
    ],
  },
  {
    title: "Hospital",
    items: [
      { to: "/ed", label: "Emergency", icon: Siren, perm: "adt:read" },
      { to: "/beds", label: "Bed board", icon: BedDouble, perm: "adt:read" },
      { to: "/inpatients", label: "Inpatients", icon: Hospital, perm: "adt:read" },
      { to: "/nursing", label: "Nursing", icon: HeartHandshake, perm: "nursing:write" },
      { to: "/pharmacy", label: "Pharmacy & inventory", icon: Pill, perm: "inventory:read" },
      { to: "/equipment", label: "Equipment", icon: Wrench, perm: "inventory:write" },
      { to: "/or", label: "Operating rooms", icon: Scissors, any: ["or:manage", "orders:sign"] },
      { to: "/roster", label: "Staff roster", icon: CalendarClock, perm: "roster:self" },
      { to: "/radiology", label: "Radiology", icon: ScanLine, perm: "radiology:work" },
      { to: "/lab", label: "Laboratory", icon: FlaskConical, any: ["lab:work", "lab:verify", "orders:sign"] },
    ],
  },
  {
    title: "Revenue & insurance",
    items: [
      { to: "/insurance", label: "Insurance Guardian", icon: ShieldCheck, any: ["insurance:write", "automation:manage"] },
      { to: "/billing", label: "Billing", icon: Receipt, perm: "billing:read" },
      { to: "/revenue", label: "Claims & authorizations", icon: FileCheck2, any: ["billing:read", "insurance:write"] },
      { to: "/analytics", label: "Analytics", icon: BarChart3, perm: "analytics:read" },
    ],
  },
  {
    title: "AI & automation",
    items: [
      { to: "/ai", label: "AI assistants", icon: Sparkles, perm: "ai:use" },
      { to: "/insights", label: "Insights", icon: Lightbulb, perm: "analytics:read" },
      { to: "/agents", label: "Agent Studio", icon: Bot, perm: "ai:use" },
      { to: "/admin/ai-governance", label: "AI governance", icon: ShieldCheck, perm: "ai:manage" },
      { to: "/automation/monitors", label: "Monitors & rules", icon: Activity, any: ["automation:manage", "command:view"] },
      { to: "/automation", label: "Automation studio", icon: Workflow, perm: "automation:manage" },
      { to: "/receptionist", label: "HMS Voice Concierge", icon: PhoneCall, perm: "schedule:write" },
      { to: "/admin/ai", label: "AI monitoring", icon: Bot, perm: "clinic:manage" },
    ],
  },
  {
    title: "Administration",
    items: [
      { to: "/admin/facilities", label: "Facilities", icon: Building2, perm: "clinic:manage" },
      { to: "/admin/staff", label: "Staff & roles", icon: Users, perm: "users:manage" },
      { to: "/admin/clinics", label: "Clinic settings", icon: Settings2, perm: "clinic:manage" },
      { to: "/admin/scheduling", label: "Scheduling setup", icon: CalendarDays, perm: "clinic:manage" },
      { to: "/admin/order-sets", label: "Order sets", icon: ListChecks, perm: "clinic:manage" },
      { to: "/admin/audit", label: "Audit log", icon: ScrollText, perm: "audit:read" },
      { to: "/admin/outbox", label: "Message outbox", icon: Mail, perm: "users:manage" },
      { to: "/admin/system", label: "System status", icon: ServerCog, perm: "clinic:manage" },
      { to: "/admin/organizations", label: "Organizations", icon: HeartPulse, perm: "org:manage" },
      { to: "/admin/ai-settings", label: "AI settings", icon: KeyRound, perm: "org:manage" },
    ],
  },
  {
    title: "Support",
    items: [{ to: "/help", label: "Help & About", icon: LifeBuoy }],
  },
];

/* ---------------------------------------------------------------------------------------------------------------------
 * Role-based primary navigation (UX simplification). Each role sees 6–9 destinations it uses daily; every other
 * permitted page stays one click away under "All tools" (and via ⌘K search). Permissions are taken from NAV above and
 * are enforced again by the server — this only decides what is shown first.
 * ------------------------------------------------------------------------------------------------------------------- */

export type HomeProfile =
  | "super_admin" | "hospital_admin" | "clinic_admin" | "doctor" | "nurse" | "pharmacist" | "lab_tech" | "radiologist"
  | "bed_manager" | "billing" | "insurance_specialist" | "receptionist" | "staff";

const PROFILE_ORDER: [string, HomeProfile][] = [
  ["super_admin", "super_admin"], ["hospital_admin", "hospital_admin"], ["clinic_admin", "clinic_admin"], ["doctor", "doctor"],
  ["nurse", "nurse"], ["pharmacist", "pharmacist"], ["lab_tech", "lab_tech"], ["radiologist", "radiologist"], ["radiology_tech", "radiologist"],
  ["bed_manager", "bed_manager"], ["billing", "billing"], ["insurance_specialist", "insurance_specialist"], ["receptionist", "receptionist"],
];

export function profileFor(roles: string[] | undefined): HomeProfile {
  for (const [role, profile] of PROFILE_ORDER) if (roles?.includes(role)) return profile;
  return "staff";
}

/** Primary links per profile: [path, label override?]. Labels default to the NAV label. */
const PRIMARY: Record<HomeProfile, [string, string?][]> = {
  super_admin: [["/"], ["/worklist"], ["/command"], ["/admin/staff"], ["/admin/facilities"], ["/admin/ai-settings"], ["/agents"], ["/admin/audit"], ["/help"]],
  hospital_admin: [["/"], ["/worklist"], ["/command"], ["/beds"], ["/ed"], ["/inpatients"], ["/analytics", "Reports"], ["/agents", "AI agents"], ["/help"]],
  clinic_admin: [["/"], ["/worklist"], ["/front-desk"], ["/schedule"], ["/patients"], ["/analytics", "Reports"], ["/admin/staff"], ["/admin/clinics"], ["/help"]],
  doctor: [["/"], ["/worklist"], ["/encounters"], ["/patients"], ["/messages"], ["/orders", "Orders & results"], ["/ed"], ["/inpatients"], ["/help"]],
  nurse: [["/"], ["/worklist"], ["/nursing"], ["/patients"], ["/ed"], ["/beds"], ["/messages"], ["/help"]],
  pharmacist: [["/"], ["/worklist"], ["/pharmacy"], ["/patients"], ["/orders"], ["/messages"], ["/help"]],
  lab_tech: [["/"], ["/worklist"], ["/lab"], ["/patients"], ["/orders"], ["/help"]],
  radiologist: [["/"], ["/worklist"], ["/radiology"], ["/patients"], ["/orders"], ["/help"]],
  bed_manager: [["/"], ["/worklist"], ["/beds"], ["/inpatients"], ["/ed"], ["/command"], ["/help"]],
  billing: [["/"], ["/worklist"], ["/billing"], ["/revenue", "Claims & authorizations"], ["/insurance"], ["/patients"], ["/analytics", "Reports"], ["/help"]],
  insurance_specialist: [["/"], ["/worklist"], ["/insurance"], ["/revenue", "Claims & authorizations"], ["/patients"], ["/documents"], ["/help"]],
  receptionist: [["/"], ["/worklist"], ["/front-desk"], ["/schedule"], ["/receptionist"], ["/patients"], ["/insurance"], ["/messages"], ["/help"]],
  staff: [["/"], ["/worklist"], ["/patients"], ["/help"]],
};

const ALL_ITEMS: NavItem[] = NAV.flatMap((s) => s.items);
const RENAME: Record<string, string> = { "/": "Home" };

export function primaryNav(profile: HomeProfile): NavItem[] {
  return PRIMARY[profile].flatMap(([to, label]) => {
    const item = ALL_ITEMS.find((i) => i.to === to);
    return item ? [{ ...item, label: label ?? RENAME[to] ?? item.label }] : [];
  });
}
