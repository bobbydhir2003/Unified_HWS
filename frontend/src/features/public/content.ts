/**
 * Public website content (approved strategy: docs/HMS_WORKFLOWS_PUBLIC_WEBSITE_STRATEGY.md).
 * Describes only what the application implements. Simulated integrations are named where they matter. No metrics,
 * customers, outcomes or certifications are claimed.
 */
import {
  Activity, BedDouble, Bot, CalendarDays, ClipboardCheck, FlaskConical, HeartPulse, Hospital, type LucideIcon, Mic,
  PenLine, Radar, Receipt, ShieldCheck, Siren, Stethoscope, UserPlus, UsersRound, Workflow,
} from "lucide-react";

export const DEFINITION =
  "HMS Workflows is a hospital management platform that puts every department on one shared patient record, turns problems into owned and tracked work, and gives leaders one live view of the hospital — with AI that drafts and summarizes while people decide.";

// ------------------------------------------------------------------------------------------------ product screenshots
/** Captured by e2e/capture_marketing_shots.py from the deployed site (synthetic data). */
export const SHOTS = {
  commandCenter: { src: "command-center", w: 1440, h: 1000, alt: "HMS Workflows Command Center: hospital status figures, problems grouped by area with owners and overdue times, and department detail tabs (synthetic data)" },
  doctorHome: { src: "doctor-home", w: 1440, h: 900, alt: "Doctor Home: priorities grouped by patient, today's appointments and quick actions (synthetic data)" },
  patientChart: { src: "patient-chart", w: 1440, h: 900, alt: "Patient chart with the patient banner, allergy status, latest vitals with a flagged high BMI, problems, medications and upcoming visits (synthetic data)" },
  myWork: { src: "my-work", w: 1440, h: 860, alt: "My work: cases with severity, patient, owner, time overdue and status (synthetic data)" },
  edBoard: { src: "ed-board", w: 1440, h: 900, alt: "Emergency department tracking board with acuity, time in department, provider and next actions (synthetic data)" },
  insuranceGuardian: { src: "insurance-guardian", w: 1440, h: 900, alt: "Insurance Guardian: coverage status of upcoming visits and open insurance cases, with the simulated payer labelled (synthetic data)" },
  patientPortal: { src: "patient-portal", w: 1440, h: 900, alt: "Patient portal: five sections, a single to-do list before the next visit, and upcoming appointments (synthetic data)" },
  agentStudio: { src: "agent-studio", w: 1440, h: 900, alt: "AI Agent Studio: each assistant with what it reads, what it may propose for approval, and its limits (synthetic data)" },
} as const;
export type ShotKey = keyof typeof SHOTS;

// ------------------------------------------------------------------------------------------------ problem → approach
export const PROBLEMS: { title: string; text: string }[] = [
  { title: "Patient information is scattered", text: "Registration, the ward, pharmacy and billing each keep their own version of the patient, so details are re-entered and fall out of date." },
  { title: "Coordination happens by phone", text: "A discharge can wait on a signature, a medication check and transport at the same time, and nobody sees all three." },
  { title: "Ownership of delays is unclear", text: "When a task stalls between departments, it is often unclear who is responsible for moving it forward." },
  { title: "Problems go unnoticed", text: "Expiring stock, unconfirmed insurance or a missed follow-up are found late, usually by the person they affect." },
  { title: "Leaders lack one view", text: "Capacity, emergency pressure and pending discharges live in different systems and reports, so bottlenecks surface after the fact." },
];

export const APPROACH: { title: string; text: string; icon: LucideIcon; shot: ShotKey }[] = [
  { title: "One shared patient record", text: "Every department reads and writes the same record and timeline, so information follows the patient.", icon: Stethoscope, shot: "patientChart" },
  { title: "Work with an owner", text: "Problems become cases with an owner, a deadline and escalation, and close only when the record shows they are fixed.", icon: ClipboardCheck, shot: "myWork" },
  { title: "One view of the hospital", text: "The Command Center shows capacity, delays and priorities, and every figure opens the records behind it.", icon: Radar, shot: "commandCenter" },
  { title: "Assistance with people in control", text: "Rules check for problems and AI drafts and summarizes. Anything that changes data waits for a person's approval.", icon: ShieldCheck, shot: "agentStudio" },
];

// ------------------------------------------------------------------------------------------------ five capability areas
export type Area = {
  id: string; title: string; icon: LucideIcon; short: string; what: string; teams: string; connects: string; why: string;
  includes: string[]; status?: string; shot?: ShotKey;
};

/** The ONE grouping used on Home and Platform. */
export const AREAS: Area[] = [
  {
    id: "clinical-care", title: "Clinical care", icon: Stethoscope,
    short: "Registration, scheduling, the patient record, orders and results, and the patient portal.",
    what: "Front-desk staff register patients with duplicate checks and book visits on conflict-safe calendars. Clinicians document encounters, vitals, problems, medications and allergies, place orders and review results. Signed notes are locked; corrections are added as addenda.",
    teams: "Front desk, doctors, nurses, patients",
    connects: "Orders flow to laboratory, radiology and pharmacy; results and discharge instructions return to the same chart and, once released, to the patient portal.",
    why: "Everyone works from the same history, so care decisions and hand-offs don't depend on re-entered information.",
    includes: ["Registration with duplicate detection", "Scheduling, check-in, rooming and check-out", "Encounters, notes with signing and addenda", "Problems, allergies, medications and vitals", "Orders, results and critical-result acknowledgement", "Patient portal: booking, forms, messages, results, video visits, bills"],
    status: "Email and text reminders go to an outbox (simulated sending). Portal payments are simulated; video visits are browser-to-browser.",
    shot: "patientChart",
  },
  {
    id: "hospital-operations", title: "Hospital operations", icon: Hospital,
    short: "Emergency department, admissions, nursing, bed management, discharge and staffing.",
    what: "The emergency department tracks arrivals, triage and time in department. Bed managers place and transfer patients on a live bed board. Nurses work from unit worklists with overdue-vitals flags and handoffs. A discharge checklist shows what each department still owes.",
    teams: "Emergency staff, nurses, bed managers, unit leaders",
    connects: "Admissions draw on the same record as the emergency visit; discharge steps create tasks for doctors, pharmacy and front desk; capacity feeds the Command Center.",
    why: "Patient flow is visible end to end, from arrival to bed to discharge, with responsibility for each step.",
    includes: ["ED tracking board with clinician-recorded acuity", "Admission requests, bed assignment and transfers", "Live bed board with cleaning and blocked status", "Nursing worklists, observations and handoffs", "Discharge checklist with department tasks", "Staff roster and operating-room schedule"],
    shot: "edBoard",
  },
  {
    id: "diagnostics-pharmacy", title: "Diagnostics & pharmacy", icon: FlaskConical,
    short: "Laboratory, radiology, pharmacy, inventory and procurement.",
    what: "Laboratory staff collect, receive and result specimens, and a second person verifies results before release. Radiology schedules exams and radiologists sign reports. Pharmacists verify new medication orders, track lots and expiry, and stock waste needs a second person's approval.",
    teams: "Laboratory, radiology, pharmacy and supply staff",
    connects: "Orders arrive from the chart; verified results return to it; low stock and expiring medication become pharmacy cases and purchase requests.",
    why: "Safety checks such as independent verification and two-person approval are built into the workflow, not left to memory.",
    includes: ["Specimen collection, receipt and independent verification", "Imaging worklist and signed reports", "Pharmacist order verification", "Lots, expiry and two-person waste approval", "Purchase requests with approval; equipment maintenance"],
    status: "The imaging archive (PACS) and supplier purchase orders are simulated.",
  },
  {
    id: "revenue", title: "Revenue", icon: Receipt,
    short: "Insurance Guardian, claims, prior authorizations, billing and patient statements.",
    what: "Insurance Guardian checks coverage before upcoming visits and opens cases for problems; a stored plan end date is never treated as proof of coverage. Billing turns charges into claims, reviews them before submission, and tracks prior authorizations, denials and patient balances.",
    teams: "Front desk, insurance specialists, billing staff",
    connects: "Coverage problems reach the front desk before the visit; patients can upload a new card in the portal; claims draw on the visit and discharge records.",
    why: "Coverage and claim problems are found and assigned before they turn into denials or surprises for patients.",
    includes: ["Coverage checks before visits, with cases for problems", "Insurance card review", "Claims with pre-submission review", "Prior authorizations, denials and appeals", "Patient statements and payments"],
    status: "Payer eligibility, the claims clearinghouse, payer responses and card payments are simulated. No live payer connection exists.",
    shot: "insuranceGuardian",
  },
  {
    id: "coordination", title: "Coordination & insight", icon: Radar,
    short: "My work, the automation engine, the Command Center, analytics and AI assistance.",
    what: "Monitors check records on a schedule and open one case per problem, with an owner, a deadline and escalation that keeps the owner. Each person sees their cases, tasks and approvals in My work. The Command Center shows hospital status, grouped problems and department detail. AI assistants summarize and draft within the user's permissions.",
    teams: "Administrators, department leads, every staff member",
    connects: "It sits across all other areas: monitors watch every department, and cases route work back to the team that can fix it.",
    why: "Problems stop depending on someone noticing them, and leaders can see where the hospital is waiting and who owns each delay.",
    includes: ["Configurable monitors and thresholds", "Cases with owners, deadlines and escalation", "My work: cases, tasks and approvals", "Command Center with traceable figures", "Analytics and a sourced daily briefing", "AI assistants with approval gates"],
    status: "AI features use a configured AI provider when an administrator enables one; otherwise they run in a labelled simulation.",
    shot: "commandCenter",
  },
];

// ------------------------------------------------------------------------------------------------ patient journey
export type JourneyTag = "record" | "task" | "review" | "visibility";
export const TAG_LABEL: Record<JourneyTag, string> = { record: "Shared record", task: "Task created", review: "Human review", visibility: "Hospital-wide visibility" };

export const JOURNEY: { title: string; icon: LucideIcon; happens: string; next: string; tags: JourneyTag[] }[] = [
  { title: "Registration", icon: UserPlus, happens: "The front desk registers the patient, with a duplicate check, and records insurance.", next: "Insurance Guardian checks coverage before the visit and opens a case if it can't be confirmed.", tags: ["record", "task"] },
  { title: "Appointment or emergency", icon: Siren, happens: "The patient checks in for a booked visit, or arrives in the emergency department and is triaged by a nurse.", next: "Arrival and acuity appear on the front desk and ED boards.", tags: ["record", "visibility"] },
  { title: "Clinical care", icon: Stethoscope, happens: "Doctors and nurses review history, document care and place orders. An AI scribe can draft the note with consent.", next: "Orders go to the laboratory, radiology and pharmacy; drafts wait for the clinician to sign.", tags: ["record", "review"] },
  { title: "Diagnostic services", icon: FlaskConical, happens: "Specimens are collected and results verified by a second person; imaging reports are signed; pharmacists verify medications.", next: "Results return to the chart; critical results must be acknowledged.", tags: ["review", "task"] },
  { title: "Admission", icon: BedDouble, happens: "An admission request is placed and the bed manager assigns a bed on the live bed board.", next: "Nursing worklists and the Command Center update with the new inpatient.", tags: ["visibility", "record"] },
  { title: "Discharge", icon: ClipboardCheck, happens: "A discharge checklist lists what each department still owes — summary, medications, transport, education.", next: "Missing steps become tasks for the right team; overdue ones are escalated.", tags: ["task", "review"] },
  { title: "Billing", icon: Receipt, happens: "Charges become claims that are reviewed before submission; prior authorizations and denials are tracked.", next: "Balances appear in the patient portal. Payer connections are simulated.", tags: ["record", "review"] },
  { title: "Follow-up", icon: CalendarDays, happens: "Follow-up visits, approved discharge instructions and messages continue in the portal.", next: "A monitor opens a case if a needed follow-up is never booked.", tags: ["task", "record"] },
];

// ------------------------------------------------------------------------------------------------ automation & AI
export type AiTier = { id: string; title: string; icon: LucideIcon; does: string; examples: string[]; control: string; kind: "Deterministic rules" | "AI-generated" | "AI + approval" | "Voice AI" | "People" };
export const AI_TIERS: AiTier[] = [
  { id: "rules", title: "Rules-based automation", icon: Workflow, kind: "Deterministic rules",
    does: "Checks records on a schedule and opens a case when a defined condition is true. This is not generative AI.",
    examples: ["Low or expiring stock", "Overdue tasks and missed follow-ups", "Discharge steps not completed", "Unresolved insurance issues", "Assigning and escalating work"],
    control: "Administrators set thresholds; cases go to a named team and close only when the record shows the problem is fixed." },
  { id: "assisted", title: "AI-assisted workflows", icon: PenLine, kind: "AI-generated",
    does: "Reads information the user is allowed to see and writes a summary or draft. Outputs are advisory.",
    examples: ["Draft a visit note from a consented conversation", "Summarize a patient chart with references", "Classify and extract details from a document", "Explain operational bottlenecks", "Highlight claims that need attention"],
    control: "A clinician or staff member reviews, edits and signs; nothing is saved to the chart until they do." },
  { id: "agents", title: "AI agents", icon: Bot, kind: "AI + approval",
    does: "Answer a question by retrieving authorized information through approved backend tools, then summarize the situation and, where configured, propose an action.",
    examples: ["\"What is blocking this discharge?\"", "Propose a reminder task for the owner", "Draft a patient message for staff approval"],
    control: "Agents act only under the user's permissions. Proposals wait in My work until a person approves or rejects them." },
  { id: "voice", title: "Realtime voice", icon: Mic, kind: "Voice AI",
    does: "A spoken conversation in the browser with the AI receptionist, for practising administrative calls.",
    examples: ["Practice an appointment request by voice", "Hear and read the live transcript"],
    control: "The voice session has fixed receptionist instructions and no tools: it cannot look up or change hospital records or book real appointments. It needs a configured AI provider." },
  { id: "oversight", title: "Human oversight", icon: ShieldCheck, kind: "People",
    does: "Clinicians and authorized staff remain responsible for consequential decisions and actions.",
    examples: ["Sign notes", "Approve or reject proposals", "Verify results", "Every step recorded in the audit log"],
    control: "Role-based permissions are enforced on the server; AI never signs, prescribes, changes claims or messages patients on its own." },
];

export type StatusRow = { label: string; tone: "success" | "info" | "warning" | "danger" | "neutral"; text: string };
export const PRODUCT_STATUS: StatusRow[] = [
  { label: "Implemented", tone: "success", text: "The hospital workflows described on this site — clinical records, scheduling, emergency and inpatient care, pharmacy, laboratory, radiology, insurance and billing workflows, automation, the Command Center and the patient portal — work end to end with a real database and automated tests." },
  { label: "Live AI tested", tone: "info", text: "An AI agent run has completed successfully against OpenAI (gpt-4.1-mini) in development. The medical scribe's transcription, document reading, chart assistant and realtime voice have not yet been verified end to end with a live provider." },
  { label: "Simulated", tone: "neutral", text: "Payer eligibility, the claims clearinghouse, payer decisions, card payments, supplier orders, the imaging archive (PACS) and email/text delivery are simulated and labelled in the application." },
  { label: "Synthetic data", tone: "warning", text: "This deployment uses synthetic data only. AI answers are labelled Simulated whenever no AI provider is configured." },
  { label: "Not certified", tone: "danger", text: "HMS Workflows is a demonstration build. It is not certified for clinical use and is not represented as HIPAA-compliant." },
];

// ------------------------------------------------------------------------------------------------ audiences
export const AUDIENCES: { id: string; title: string; icon: LucideIcon; need: string; points: string[]; shot: ShotKey }[] = [
  { id: "leadership", title: "For hospital leadership", icon: Radar, shot: "commandCenter",
    need: "See where the hospital is waiting and who owns each delay, without collecting reports from every department.",
    points: ["Command Center: hospital status, grouped problems and department detail", "Every figure opens the records behind it", "Approvals and escalations in one place", "Analytics and a daily briefing that lists its sources"] },
  { id: "clinical", title: "For clinical teams", icon: HeartPulse, shot: "doctorHome",
    need: "Have the whole patient in one chart and spend less time chasing tasks between departments.",
    points: ["Role Home with priorities grouped by patient", "Patient chart with allergies and abnormal vitals clearly marked", "Notes with signing, and an optional AI scribe draft with consent", "Orders, results and critical-result acknowledgement"] },
  { id: "operations", title: "For hospital operations", icon: Activity, shot: "edBoard",
    need: "Keep patients moving through emergency, beds, diagnostics and discharge, with clear hand-offs.",
    points: ["ED board and live bed board", "Nursing worklists with overdue-vitals flags", "Laboratory and pharmacy verification worklists", "Discharge checklist showing what each team still owes", "Staff roster and operating-room schedule"] },
  { id: "revenue", title: "For revenue teams", icon: Receipt, shot: "insuranceGuardian",
    need: "Catch coverage and claim problems before they become denials.",
    points: ["Coverage checks before visits, with cases for problems", "Claims reviewed before submission", "Prior authorizations, denials and appeals", "Patient statements (payments simulated)"] },
  { id: "patients", title: "For patients", icon: UsersRound, shot: "patientPortal",
    need: "Handle appointments, forms, messages and bills without phone calls.",
    points: ["Book visits and complete pre-visit forms", "Secure messages with the care team", "Released results and visit summaries", "Video visits in the browser", "Insurance updates and statements"] },
];

// ------------------------------------------------------------------------------------------------ about
export const PRINCIPLES: [string, string][] = [
  ["One record, many departments", "Clinical, operational and financial work share one database, so a change in one department is visible wherever it matters."],
  ["Every problem has an owner", "Automation turns problems into cases with an owner and a deadline. Escalation brings in a manager without taking the work away from the team doing it."],
  ["Numbers you can trace", "Operational figures open the records behind them, so leaders can act on them rather than question them."],
  ["AI that assists, people who decide", "AI drafts, summarizes and proposes within the user's permissions. People review, approve and sign."],
  ["A workspace per role", "Each person lands on the screens and actions that match their role, and the server enforces the same rules."],
];
