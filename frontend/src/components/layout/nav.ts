import {
  Building2, CalendarDays, ClipboardList, HeartPulse, LayoutDashboard, type LucideIcon, Mail, ScrollText,
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
      { to: "/encounters", label: "My visits", icon: Stethoscope, perm: "clinical:read", providerOnly: true },
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
