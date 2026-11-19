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
      { to: "/encounters", label: "My visits", icon: Stethoscope, perm: "clinical:read", providerOnly: true },
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
      { to: "/revenue", label: "Revenue integrity", icon: FileCheck2, any: ["billing:read", "insurance:write"] },
      { to: "/analytics", label: "Analytics", icon: BarChart3, perm: "analytics:read" },
    ],
  },
  {
    title: "AI & automation",
    items: [
      { to: "/ai", label: "AI workspace", icon: Sparkles, perm: "ai:use" },
      { to: "/insights", label: "Insights", icon: Lightbulb, perm: "analytics:read" },
      { to: "/agents", label: "Agent Studio", icon: Bot, perm: "ai:use" },
      { to: "/admin/ai-governance", label: "AI governance", icon: ShieldCheck, perm: "ai:manage" },
      { to: "/automation/monitors", label: "Monitors & rules", icon: Activity, any: ["automation:manage", "command:view"] },
      { to: "/automation", label: "Automation studio", icon: Workflow, perm: "automation:manage" },
      { to: "/receptionist", label: "AI receptionist", icon: PhoneCall, perm: "schedule:write" },
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
