/**
 * Public website content. Describes only what the application implements; integrations that are simulated in this build
 * are labeled as such. No performance or outcome claims.
 */
import {
  Activity, BarChart3, BedDouble, Bot, CalendarDays, ClipboardList, FlaskConical, HeartPulse, Hospital, type LucideIcon,
  MonitorSmartphone, Package, Pill, Radar, Receipt, ScanLine, ShieldCheck, Siren, Stethoscope, UserCog, UsersRound,
} from "lucide-react";

export type PublicModule = {
  id: string;
  title: string;
  icon: LucideIcon;
  short: string;
  description: string;
  capabilities: string[];
  note?: string;
};

/** The twelve homepage modules (in order), plus the patient portal which only appears on /modules. */
export const MODULES: PublicModule[] = [
  {
    id: "patients", title: "Patient Management", icon: UsersRound,
    short: "One record per patient, with duplicate checks and fast search.",
    description: "Front-desk and clinical teams register patients, find them quickly by name, date of birth or record number, and keep demographics and insurance details up to date. Registration checks for possible duplicates before a new record is created.",
    capabilities: ["Registration with duplicate detection", "Global patient search", "Demographics, contacts and insurance on one profile", "A unified journey timeline across departments"],
  },
  {
    id: "scheduling", title: "Scheduling & Appointments", icon: CalendarDays,
    short: "Clinician calendars, check-in, rooming and visit completion.",
    description: "Staff book visits on clinician calendars that prevent double-booking, then move each visit through confirmation, check-in, rooming and check-out from the front desk. Patients can book and prepare for visits through the portal.",
    capabilities: ["Conflict-safe calendars", "Front desk and waiting room", "Pre-visit forms", "Reminders and no-show tracking"],
    note: "Appointment reminders by email and text are simulated in this build.",
  },
  {
    id: "ehr", title: "Electronic Health Records", icon: Stethoscope,
    short: "Encounters, vitals, problems, medications, notes and results.",
    description: "Clinicians can review patient histories, document encounters, record vital signs, manage clinical notes, and follow patient activity through a connected timeline. Signed notes are locked; corrections are added as addenda.",
    capabilities: ["Structured visit notes with signing", "Problems, allergies and medications", "Orders and results review", "Document intake with staff review"],
  },
  {
    id: "acute", title: "Inpatient & Emergency Care", icon: Siren,
    short: "ED tracking, admissions, nursing and coordinated discharge.",
    description: "Hospital teams can manage emergency department arrivals and triage, inpatient admissions, transfers, nursing observations and handoffs, and discharge preparation. A discharge checklist gives each department its part before a patient leaves.",
    capabilities: ["ED tracking board with acuity and timers", "Admission requests and transfers", "Nursing worklists, vitals and handoffs", "Discharge checklists with department tasks"],
  },
  {
    id: "pharmacy", title: "Pharmacy & Medications", icon: Pill,
    short: "Medication verification, lots, expiry and stock movements.",
    description: "Pharmacy staff can monitor medication stock, inventory lots, expiration dates, and replenishment tasks. New medication orders are verified by a pharmacist, and stock waste requires a second person's approval.",
    capabilities: ["Pharmacist order verification", "Lot and expiry tracking", "Two-person approval for waste", "Expiring and low-stock alerts"],
  },
  {
    id: "diagnostics", title: "Laboratory & Radiology", icon: FlaskConical,
    short: "Specimens, verified results, imaging worklists and reports.",
    description: "Laboratory staff collect, receive and result specimens, with a second person verifying results before release. Radiology schedules and performs exams, and radiologists sign final reports. Critical results raise alerts that must be acknowledged.",
    capabilities: ["Specimen collection and receipt", "Independent result verification", "Imaging worklist and signed reports", "Critical-result acknowledgement"],
    note: "The image archive (PACS) connection is simulated in this build.",
  },
  {
    id: "revenue", title: "Insurance & Billing", icon: Receipt,
    short: "Insurance Guardian, claims, authorizations and payments.",
    description: "Insurance teams can track verification needs, review upcoming coverage dates, and coordinate follow-up tasks before appointments. Billing turns charges into claims, checks them before submission, tracks prior authorizations and denials, and shows patient balances in the portal.",
    capabilities: ["Insurance Guardian coverage checks", "Claims with pre-submission review", "Prior authorizations and denials", "Patient statements and payments"],
    note: "Payer, clearinghouse and card-payment connections are simulated in this build.",
  },
  {
    id: "ai", title: "AI Assistants & Voice", icon: Bot,
    short: "Summaries, note drafts, document reading and voice practice.",
    description: "Authorized users can access AI-assisted summaries, document processing, clinical note drafts, and administrative support. Sensitive actions remain subject to applicable permissions and human review. AI Agent Studio lets administrators configure each assistant's job, tools and limits.",
    capabilities: ["Chart assistant with cited answers", "AI medical scribe with consent", "Document classification and matching", "Configurable agents with approval gates", "Realtime voice for the receptionist"],
    note: "External AI features need an administrator to configure a provider key; until then they run in a clearly labeled simulation mode.",
  },
  {
    id: "beds", title: "Bed & Ward Management", icon: BedDouble,
    short: "A live bed board for placement, transfers and cleaning.",
    description: "Bed managers see every inpatient bed and every patient waiting for one. They place patients, move them between units, and track cleaning and blocked beds, while emergency bays stay separate from inpatient capacity.",
    capabilities: ["Live bed board by unit", "Bed assignment and transfers", "Cleaning and blocked-bed status", "Waiting-for-bed visibility"],
  },
  {
    id: "command", title: "Hospital Command Center", icon: Radar,
    short: "Live hospital status, alerts and shift handoff in one view.",
    description: "Administrators see inpatient census, available beds, emergency activity, discharges, alerts and staffing gaps in one live view. Every number shows where it comes from and opens the cases or patients behind it.",
    capabilities: ["Live operational tiles with sources", "Occupancy by department", "Alerts routed to the right team", "Shift handoff summaries"],
  },
  {
    id: "inventory", title: "Inventory & Procurement", icon: Package,
    short: "Stock levels, purchase requests and equipment maintenance.",
    description: "Teams track supplies by location, receive purchase requests when stock runs low, and approve them before ordering. An equipment register records maintenance and flags items that are due for service.",
    capabilities: ["Par levels by location", "Purchase requests with approval", "Equipment register and service log", "Maintenance-due alerts"],
    note: "Purchase orders to suppliers are simulated in this build.",
  },
  {
    id: "analytics", title: "Analytics & Reporting", icon: BarChart3,
    short: "Dashboards, a sourced daily briefing and planning forecasts.",
    description: "Leaders review visit volumes, no-shows and revenue, and read a daily briefing in which every figure lists its source. Simple forecasts are provided for planning discussions and are clearly marked as not validated.",
    capabilities: ["Operational and financial dashboards", "Daily briefing with sources", "Baseline forecasts (not validated)", "AI usage and cost reporting"],
  },
  {
    id: "portal", title: "Patient Portal & Telehealth", icon: MonitorSmartphone,
    short: "Self-service for patients, on any device.",
    description: "Patients book appointments, complete pre-visit forms, message their care team, see visit summaries and released results, update insurance, join browser-based video visits, and review and pay statements.",
    capabilities: ["Online booking and pre-visit forms", "Secure messaging", "Results and visit summaries", "Video visits in the browser", "Insurance updates and bill pay"],
    note: "Payments are simulated in this build; no card is charged.",
  },
];

export const HOME_MODULES = MODULES.filter((m) => m.id !== "portal");

export type Solution = { id: string; title: string; icon: LucideIcon; intro: string; points: string[]; modules: string[] };

export const SOLUTIONS: Solution[] = [
  { id: "doctors", title: "Doctors", icon: Stethoscope, intro: "Everything about a patient in one chart, with documentation help that never acts on its own.",
    points: ["Today's patients and visit list", "Patient charts with allergies always in view", "Clinical notes, with an optional AI scribe (with consent)", "Orders, results and critical-result alerts", "Admission, discharge and follow-up workflows"], modules: ["ehr", "acute", "ai"] },
  { id: "nurses", title: "Nurses", icon: HeartPulse, intro: "Your patients, their vitals and your tasks, with clear handoffs between shifts.",
    points: ["Patient assignments by unit", "Observations and overdue-vitals flags", "Nursing documentation and handoffs", "Emergency triage", "Coordinated discharge tasks"], modules: ["acute", "beds"] },
  { id: "front-desk", title: "Reception & Front Desk", icon: ClipboardList, intro: "Smooth arrivals, from registration to the waiting room.",
    points: ["Patient registration with duplicate checks", "Appointment booking and rescheduling", "Check-in and rooming", "Insurance readiness before the visit"], modules: ["patients", "scheduling", "revenue"] },
  { id: "administrators", title: "Hospital Administrators", icon: Hospital, intro: "A clear view of the whole hospital and the work that needs attention.",
    points: ["Command Center with live operational status", "Capacity and discharge monitoring", "Approvals and assigned work", "Reports, briefings and analytics"], modules: ["command", "analytics", "inventory"] },
  { id: "billing", title: "Insurance & Billing Teams", icon: ShieldCheck, intro: "Catch coverage and claim problems before they become denials.",
    points: ["Eligibility checks and follow-ups", "Claims with pre-submission review", "Prior authorizations", "Denials and appeals", "Patient balances and payments"], modules: ["revenue"] },
  { id: "pharmacists", title: "Pharmacists", icon: Pill, intro: "Safe medication handling, with stock you can trust.",
    points: ["Medication verification worklist", "Stock movements and lot tracking", "Expiry and low-stock monitoring", "Two-person approval for waste", "Discharge medication reconciliation"], modules: ["pharmacy", "inventory"] },
  { id: "diagnostics", title: "Laboratory & Radiology Staff", icon: ScanLine, intro: "Orders in, verified results out, with nothing lost in between.",
    points: ["Order and specimen worklists", "Independent result verification", "Imaging scheduling and signed reports", "Critical-result alerts"], modules: ["diagnostics"] },
  { id: "patients", title: "Patients", icon: UsersRound, intro: "Simple self-service for appointments, messages and bills.",
    points: ["Book appointments and complete forms", "Secure messages with the care team", "Visit summaries and released results", "Video visits", "Insurance updates and online statements"], modules: ["portal"] },
];

export const ADMIN_SOLUTION = {
  title: "Super Admin & AI Agent Studio", icon: UserCog,
  points: [
    "Manage organizations, facilities, staff and role-based access.",
    "Choose an AI provider and models. Provider keys are stored encrypted on the server and never shown in the browser.",
    "Configure each AI agent's purpose, allowed tools and limits, with every change versioned.",
    "Anything an agent proposes waits for a person to approve it, and every action is recorded in an audit log.",
  ],
};

export const HIGHLIGHTS = [
  { icon: Activity, title: "Connected Hospital Operations", text: "Bring departments, patients, and operational workflows together." },
  { icon: Bot, title: "AI-Assisted Healthcare Workflows", text: "Support documentation, information review, and administrative coordination." },
  { icon: BarChart3, title: "Clearer Operational Visibility", text: "Track appointments, admissions, tasks, inventory, and hospital activity." },
];

export const DIFFERENTIATORS = [
  ["Connected clinical and operational workflows", "Clinical, operational and financial work share one database, so a change in one department is visible wherever it matters."],
  ["One patient journey across departments", "Registration, visits, emergency care, admissions, results, billing and follow-up appear on a single timeline."],
  ["Proactive administrative automation", "Background checks spot problems such as missing discharge steps, expiring stock or coverage issues, and assign them to the right team."],
  ["Human-controlled AI assistance", "AI drafts, summarizes and suggests. People review, approve and sign."],
  ["Role-specific workspaces", "Each person sees the screens and actions that match their role, enforced again on the server."],
  ["Hospital-wide operational visibility", "Live status for beds, emergency, discharges, alerts and staffing, with the source of every number."],
  ["A consistent, modern experience", "One design system across every department, in light and dark mode, on desktop and mobile."],
] as const;
