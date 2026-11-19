import {
  BarChart3, Bot, Building2, CalendarDays, ClipboardList, ClipboardPen, FileStack, ListChecks, MessageSquare, PhoneCall, Receipt, Workflow, HeartPulse, LayoutDashboard, type LucideIcon, Mail, ScrollText,
  ServerCog, Settings2, Stethoscope, Users, UsersRound,
} from "lucide-react";

export type NavItem = { to: string; label: string; icon: LucideIcon; perm?: string; any?: string[]; providerOnly?: boolean };
export type NavSection = { title?: string; items: NavItem[] };

export const NAV: NavSection[] = [
  {
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard },
      { to: "/front-desk", label: "Front desk", icon: ClipboardList, perm: "schedule:read" },
      { to: "/schedule", label: "Schedule", icon: CalendarDays, perm: "schedule:read" },
      { to: "/patients", label: "Patients", icon: UsersRound, perm: "patients:read" },
      { to: "/tasks", label: "Tasks", icon: ListChecks, perm: "patients:read" },
      { to: "/messages", label: "Messages", icon: MessageSquare, perm: "messages:use" },
      { to: "/orders", label: "Orders", icon: ClipboardPen, perm: "clinical:read" },
      { to: "/documents", label: "Documents", icon: FileStack, perm: "documents:read" },
      { to: "/analytics", label: "Analytics", icon: BarChart3, perm: "analytics:read" },
      { to: "/billing", label: "Billing", icon: Receipt, perm: "billing:read" },
      { to: "/encounters", label: "My visits", icon: Stethoscope, perm: "clinical:read", providerOnly: true },
    ],
  },
  {
    title: "AI & automation",
    items: [
      { to: "/automation", label: "Automation studio", icon: Workflow, perm: "messages:use" },
      { to: "/receptionist", label: "AI receptionist", icon: PhoneCall, perm: "schedule:write" },
      { to: "/admin/ai", label: "AI monitoring", icon: Bot, perm: "clinic:manage" },
    ],
  },
  {
    title: "Administration",
    items: [
      { to: "/admin/staff", label: "Staff & roles", icon: Users, perm: "users:manage" },
      { to: "/admin/clinics", label: "Clinics", icon: Building2, perm: "clinic:manage" },
      { to: "/admin/scheduling", label: "Scheduling setup", icon: Settings2, perm: "clinic:manage" },
      { to: "/admin/audit", label: "Audit log", icon: ScrollText, perm: "audit:read" },
      { to: "/admin/outbox", label: "Message outbox", icon: Mail, perm: "users:manage" },
      { to: "/admin/system", label: "System status", icon: ServerCog, perm: "clinic:manage" },
      { to: "/admin/organizations", label: "Organizations", icon: HeartPulse, perm: "org:manage" },
    ],
  },
];
