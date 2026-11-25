/**
 * Public website content — "One Patient. One Connected Hospital. Every Task Accounted For."
 *
 * Accuracy rules (see docs/HMS_WORKFLOWS_PUBLIC_WEBSITE_VISION.md):
 *  - Describe only what the application implements. Simulated integrations are named where they matter.
 *  - No metrics, customers, outcomes, certifications or compliance claims.
 *  - MONITORS mirrors backend/app/monitors (22 registered monitors) and ASSISTANTS mirrors
 *    backend/app/agents/runner.py DEFAULTS (10 agents); e2e/public_site_content_check.py keeps them in sync.
 *  - No Demo Mode dependencies: the public site offers sign-in only.
 */
import {
  Activity, BedDouble, Bot, CalendarDays, ClipboardCheck, ClipboardList, FileSearch, FlaskConical, HeartPulse, Hospital,
  Landmark, type LucideIcon, MessageSquare, Microscope, Pill, Radar, Receipt, ScanLine, ShieldCheck, Siren, Stethoscope,
  UserCheck, UserPlus, UsersRound, Workflow, Wrench,
} from "lucide-react";

export const DEFINITION =
  "HMS Workflows brings patient records, clinical care, hospital operations and administrative workflows together. From registration to discharge, teams coordinate work, see what needs attention, and use automation and AI to support the next step.";

export const PHILOSOPHY = "One connected patient journey. One coordinated hospital. Clear responsibility for every task.";

// ------------------------------------------------------------------------------------------------ product screenshots
/** Real screenshots of the application with synthetic data (e2e/capture_marketing_shots.py). Never mocked. */
export const SHOTS = {
  commandCenter: { src: "command-center", w: 1440, h: 1000, alt: "HMS Workflows Command Center: hospital status figures, problems grouped by area with owners and overdue times, and department detail tabs (synthetic data)" },
  doctorHome: { src: "doctor-home", w: 1440, h: 900, alt: "Doctor Home: priorities grouped by patient, today's appointments and quick actions (synthetic data)" },
  patientChart: { src: "patient-chart", w: 1440, h: 900, alt: "Patient chart with the patient banner, allergy status, latest vitals with a flagged high BMI, problems, medications and upcoming visits (synthetic data)" },
  myWork: { src: "my-work", w: 1440, h: 860, alt: "My work: cases with severity, patient, owner, time overdue and status (synthetic data)" },
  edBoard: { src: "ed-board", w: 1440, h: 900, alt: "Emergency department tracking board with acuity, time in department, provider and next actions (synthetic data)" },
  insuranceGuardian: { src: "insurance-guardian", w: 1440, h: 900, alt: "Insurance Guardian: coverage status of upcoming visits and open insurance cases, with the simulated payer labelled (synthetic data)" },
  patientPortal: { src: "patient-portal", w: 1440, h: 900, alt: "Patient portal: five sections, a single to-do list before the next visit, and upcoming appointments (synthetic data)" },
  agentStudio: { src: "agent-studio", w: 1440, h: 900, alt: "Agent Studio: the ten HMS Intelligence agents with their department, tools, connected monitors and limits (synthetic data)" },
  assistCoverage: { src: "assist-coverage", w: 1440, h: 900, alt: "Aurelia, the insurance and coverage agent, in an insurance case: a grounded answer, a follow-up task proposal approved by a different person, and the created task (synthetic data)" },
  assistChart: { src: "assist-chart", w: 1440, h: 900, alt: "Aster, the patient chart agent: a cited summary of one patient's chart and a refused prescribing question (synthetic data)" },
  monitors: { src: "monitors", w: 1440, h: 900, alt: "Monitors and rules: rule-based checks with per-monitor AI assistance switches (synthetic data)" },
} as const;
export type ShotKey = keyof typeof SHOTS;

// ------------------------------------------------------------------------------------------------ Home: the problem
export const PROBLEMS: { title: string; problem: string; helps: string; icon: LucideIcon }[] = [
  { title: "Information is scattered across teams", icon: FileSearch,
    problem: "Registration, the ward, pharmacy and billing each need the same patient details. When they work in separate places, information is re-entered and drifts out of date.",
    helps: "Every department reads and writes one patient record — identity, visits, orders, results and timeline — with access decided by role." },
  { title: "Work waits without clear ownership", icon: UserCheck,
    problem: "A discharge can wait on a signature, a medication check and transport at once. When nobody owns the follow-up, it waits.",
    helps: "Problems become cases with an owning team, a deadline and a timeline. Escalation brings in a manager without taking the work away from its owner." },
  { title: "Delays become visible too late", icon: Siren,
    problem: "An unconfirmed insurance plan, an unread scan or a bed waiting for cleaning is often noticed only when a patient is already affected.",
    helps: "22 automation monitors check hospital records on a schedule and open a case as soon as a defined condition is true." },
  { title: "Staff spend time chasing routine follow-ups", icon: MessageSquare,
    problem: "Reminders, status checks and hand-off calls take time away from clinical and administrative work.",
    helps: "Monitors create the routine tasks and reminders, and each department's AI agent can explain a case and prepare the next step for a person to confirm or approve." },
];

// ------------------------------------------------------------------------------------------------ Home: four pillars
export type Pillar = { id: string; title: string; icon: LucideIcon; text: string; includes: string[]; to: string };
export const PILLARS: Pillar[] = [
  { id: "connected-care", title: "Connected Care", icon: Stethoscope, to: "/platform#records",
    text: "One patient identity that registration, scheduling and every clinical team work from.",
    includes: ["Registration with duplicate checks", "Appointments and check-in", "Encounters and signed documentation", "Orders and results"] },
  { id: "hospital-operations", title: "Hospital Operations", icon: Hospital, to: "/platform#workspaces",
    text: "The departments that keep patients moving through the hospital, on the same record.",
    includes: ["Emergency, nursing and inpatient care", "Live bed board and transfers", "Pharmacy, laboratory and radiology", "Staff roster and Command Center"] },
  { id: "coordinated-work", title: "Coordinated Work", icon: ClipboardCheck, to: "/platform#workflows",
    text: "Work between departments is recorded, owned and followed through to a verified outcome.",
    includes: ["Cases with owners and deadlines", "Tasks and department hand-offs", "Approvals before sensitive actions", "Outcomes checked against the record"] },
  { id: "ai-automation", title: "HMS Intelligence", icon: Bot, to: "/ai-automation",
    text: "Rules watch for known problems; ten department AI agents help people understand them and prepare the next step.",
    includes: ["22 predefined automation monitors", "10 conversational AI agents in their departments", "Confirmation or independent approval before changes", "Every AI run and conversation logged"] },
];

// ------------------------------------------------------------------------------------------------ Home: patient journeys
/** Illustrative pathways (a fictional patient). Not every patient follows every step. `monitor` names a real monitor. */
export type JourneyStep = { title: string; team: string; icon: LucideIcon; happens: string; platform: string; monitor?: string };
export type Pathway = { id: string; label: string; icon: LucideIcon; scenario: string; steps: JourneyStep[] };

export const PATHWAYS: Pathway[] = [
  {
    id: "outpatient", label: "Outpatient visit", icon: CalendarDays,
    scenario: "A fictional patient books a clinic visit for a persistent cough.",
    steps: [
      { title: "Registration", team: "Front desk", icon: UserPlus, happens: "The patient is registered with a duplicate check, and insurance is recorded.", platform: "One patient record is created for every team.", monitor: "Insurance visit readiness" },
      { title: "Appointment", team: "Front desk · patient", icon: CalendarDays, happens: "A visit is booked on a conflict-checked calendar; the patient completes the pre-visit questionnaire in the portal.", platform: "Coverage is checked before the visit.", monitor: "Pre-visit questionnaire missing" },
      { title: "Check-in", team: "Front desk", icon: ClipboardList, happens: "The patient arrives and is checked in.", platform: "Arrival appears on the clinic's front-desk board." },
      { title: "Nursing", team: "Nurse", icon: HeartPulse, happens: "The patient is roomed and vitals are recorded; abnormal values are flagged.", platform: "Vitals appear on the chart the doctor opens next." },
      { title: "Doctor", team: "Doctor", icon: Stethoscope, happens: "The doctor reviews history, documents the encounter and places orders. Sonara, the scribe agent, can draft the note with consent.", platform: "The draft waits for the doctor to review and sign." },
      { title: "Laboratory & pharmacy", team: "Lab · pharmacy", icon: FlaskConical, happens: "The lab collects and results the specimen; a second person verifies it. Pharmacists verify new medication orders.", platform: "Verified results return to the same chart.", monitor: "Lab turnaround / specimen delays" },
      { title: "Billing", team: "Billing", icon: Receipt, happens: "Charges become a claim that is reviewed before submission.", platform: "Held claims become cases for the billing team.", monitor: "Claims on hold" },
      { title: "Follow-up", team: "Front desk · patient", icon: CalendarDays, happens: "Released results and visit instructions reach the patient portal.", platform: "A case opens if a planned follow-up is never booked.", monitor: "Follow-up planned but not booked" },
    ],
  },
  {
    id: "emergency", label: "Emergency visit", icon: Siren,
    scenario: "A fictional patient arrives at the emergency department with chest pain.",
    steps: [
      { title: "Arrival", team: "Front desk · ED", icon: UserPlus, happens: "The patient is registered or found by the duplicate check and placed on the ED tracking board.", platform: "The same record is used as in any earlier visit." },
      { title: "Triage", team: "Nurse", icon: HeartPulse, happens: "A nurse records the acuity level (ESI); the system never assigns acuity itself.", platform: "Time in department is shown on the board." },
      { title: "Doctor", team: "Doctor", icon: Stethoscope, happens: "The doctor assesses the patient, documents care and places orders.", platform: "Waiting beyond the target for the acuity level opens a case.", monitor: "ED door-to-provider" },
      { title: "Diagnostics", team: "Lab · radiology", icon: Microscope, happens: "Specimens and imaging are processed; radiologists sign reports.", platform: "Critical results must be acknowledged by the responsible clinician.", monitor: "Critical lab result not acknowledged" },
      { title: "Decision", team: "Doctor", icon: ClipboardCheck, happens: "The doctor decides to discharge the patient home or request admission.", platform: "An admitted patient still in the ED is tracked as boarding.", monitor: "ED boarding" },
      { title: "Billing", team: "Billing", icon: Receipt, happens: "The visit's charges become a claim reviewed before submission.", platform: "Payer connections are simulated." },
    ],
  },
  {
    id: "inpatient", label: "Inpatient stay", icon: BedDouble,
    scenario: "A fictional patient is admitted for treatment after an emergency visit.",
    steps: [
      { title: "Admission request", team: "Doctor", icon: ClipboardList, happens: "An admission is requested from the same record as the emergency visit.", platform: "A request without a bed after the target time opens a case.", monitor: "Admission waiting for a bed" },
      { title: "Bed assignment", team: "Bed manager", icon: BedDouble, happens: "The bed manager assigns a bed on the live bed board.", platform: "Occupancy updates on the Command Center." },
      { title: "Nursing care", team: "Nurse", icon: HeartPulse, happens: "Nurses work from unit worklists with overdue-vitals flags and shift handoffs.", platform: "Each patient's care tasks are visible to the unit." },
      { title: "Treatment", team: "Doctor · pharmacy · lab", icon: Pill, happens: "Doctors place orders; pharmacists verify medications; results return to the chart.", platform: "Every department works on the same stay." },
      { title: "Discharge", team: "Doctor · nurse · pharmacy", icon: ClipboardCheck, happens: "A discharge checklist shows what each department still owes — summary, medications, education, transport.", platform: "A patient still in bed long after the discharge order opens a case.", monitor: "Discharge ordered, patient not departed" },
      { title: "Bed turnover", team: "Bed manager", icon: Wrench, happens: "The bed is cleaned and returned to service.", platform: "A bed waiting too long for cleaning opens a case.", monitor: "Bed turnover delay" },
      { title: "Billing & follow-up", team: "Billing · front desk", icon: Receipt, happens: "Claims are reviewed before submission; follow-up visits are booked.", platform: "Missing follow-ups and held claims become cases.", monitor: "Follow-up planned but not booked" },
    ],
  },
];

// ------------------------------------------------------------------------------------------------ Home: Insurance Guardian example
export const GUARDIAN_STEPS: { title: string; text: string; who: "Automation" | "System" | "AI (optional)" | "Person" }[] = [
  { who: "Automation", title: "A monitor detects a coverage problem", text: "The insurance visit-readiness monitor checks coverage for upcoming visits and finds one that still can't be verified." },
  { who: "System", title: "HMS Workflows opens a case", text: "One case per visit, owned by the insurance team, with a deadline before the visit and a timeline of everything that happens." },
  { who: "AI (optional)", title: "Aurelia reviews the case", text: "If an administrator has enabled AI, Aurelia — the insurance and coverage agent — reads the case and the patient's coverage, only information it is permitted to see." },
  { who: "AI (optional)", title: "It proposes a follow-up", text: "For example, a task for the insurance specialist to contact the patient. It never claims a payer confirmed anything." },
  { who: "Person", title: "An authorized employee approves", text: "The proposal waits in My work. Someone with the required permission approves, edits or rejects it." },
  { who: "System", title: "The backend creates the task", text: "The approved task is created on the case and assigned. The proposal, approval and task are all recorded." },
  { who: "Person", title: "Staff follow up and the case closes", text: "Staff contact the patient and update the coverage. When the monitor no longer detects the problem, the case is resolved." },
];

// ------------------------------------------------------------------------------------------------ teams (Home F + Solutions)
export type Team = {
  id: string; title: string; icon: LucideIcon; short: string; struggle: string; support: string[];
  receives: string; handsOff: string; shot?: ShotKey; shotCaption?: string; example?: { title: string; steps: string[] };
};
export const TEAMS: Team[] = [
  {
    id: "front-desk", title: "Front Desk & Administration", icon: UserPlus,
    short: "Register patients, book and check in visits, and keep coverage ready.",
    struggle: "Front-desk teams juggle arrivals, phone calls, forms and insurance questions, and often learn about a problem when the patient is already at the desk.",
    support: ["Registration with duplicate detection", "Conflict-checked scheduling, check-in and check-out", "Pre-visit questionnaires and reminders through the patient portal", "Insurance cases opened before the visit, not at the desk", "Liora drafts administrative replies in a message thread; staff approve before anything is posted"],
    receives: "Insurance cases, missing-questionnaire reminders and follow-ups that still need booking.",
    handsOff: "A registered, checked-in patient whose record every clinical team uses.",
    shot: "patientPortal", shotCaption: "The patient portal: one to-do list before the next visit. Synthetic data.",
  },
  {
    id: "clinical", title: "Doctors & Clinical Teams", icon: Stethoscope,
    short: "Work from one chart: history, documentation, orders and results.",
    struggle: "Clinicians need the full picture quickly, and too much of their time goes to documentation and chasing results across departments.",
    support: ["A role Home with priorities grouped by patient", "One chart with allergies and abnormal vitals clearly marked", "Encounters with signing and addenda; an optional AI scribe draft with consent", "ICD-10-CM diagnosis search and validation; versioned order sets that create draft orders to review and sign", "Orders, results and critical-result acknowledgement", "Aster, the chart agent: answers drawn from that patient's record, with citations"],
    receives: "Vitals from nursing, verified results from the lab and radiology, and critical results that need acknowledgement.",
    handsOff: "Signed orders to the lab, radiology and pharmacy; admission requests; discharge decisions.",
    shot: "doctorHome",
  },
  {
    id: "nursing", title: "Nursing & Inpatient Teams", icon: HeartPulse,
    short: "Triage, vitals, care tasks, beds, transfers and discharge.",
    struggle: "Nurses and bed managers coordinate many patients at once, and a single missing step can hold up a bed or a discharge.",
    support: ["ED tracking board with nurse-recorded acuity", "Medication administration record: only pharmacist-verified orders can be given, with (simulated) wristband and dose-label checks", "Flowsheets with intake/output totals, signed nursing assessments and care plans", "Admission requests, live bed board and transfers", "A discharge checklist showing what each department still owes", "Elara shows what each discharge still waits on and prepares coordination tasks"],
    receives: "Admission requests, discharge orders, and cases for boarding, bed turnover and delayed departures.",
    handsOff: "Vitals and observations to the chart; freed beds back to the bed board.",
    shot: "edBoard",
  },
  {
    id: "diagnostics-pharmacy", title: "Diagnostics & Pharmacy", icon: FlaskConical,
    short: "Laboratory, radiology, medication verification and stock.",
    struggle: "Diagnostic and pharmacy teams receive work from every ward and must keep safety checks intact while working quickly.",
    support: ["Specimen collection, receipt and independent result verification", "Imaging worklist with signed radiology reports", "Pharmacist verification required before an inpatient medication can be dispensed or given", "Dispensing labels linked to the verified order", "Lots, expiry and stock levels, with two-person approval for waste", "Purchase requests when stock runs low", "Veyra explains stock alerts with on-hand, usage and reorder figures; Lucent explains document extractions"],
    receives: "Signed orders from clinicians, and cases for expiring stock, low stock, unusual usage and slow turnaround.",
    handsOff: "Verified results and signed reports back to the ordering clinician's chart.",
    example: { title: "Example: a lab result", steps: ["Doctor signs the order", "Lab collects and receives the specimen", "A second person verifies the result", "Result returns to the chart", "A critical value must be acknowledged"] },
  },
  {
    id: "revenue", title: "Insurance & Revenue Teams", icon: Receipt,
    short: "Coverage readiness, prior authorizations, claims and balances.",
    struggle: "Coverage and claim problems found after the visit turn into rework, denials and surprise bills.",
    support: ["Insurance Guardian: coverage checks before visits, with cases for problems", "Prior authorizations drafted when a signed order needs one", "Claims reviewed before submission; denials and appeals tracked", "Patient statements and balances in the portal", "Aurelia and Valora explain coverage and claim problems and prepare follow-ups for approval"],
    receives: "Upcoming visits needing coverage, signed orders needing authorization, and claims on hold.",
    handsOff: "Ready coverage to the front desk; questions to patients through approved messages.",
    shot: "insuranceGuardian",
  },
  {
    id: "leadership", title: "Hospital Leadership", icon: Radar,
    short: "Hospital-wide visibility, operational cases and accountability.",
    struggle: "Leaders need to know where the hospital is waiting and who owns each delay, without collecting reports from every department.",
    support: ["Command Center: hospital status, grouped problems and department detail", "Every figure opens the records behind it", "Staffing gaps with eligible staff suggested; managers decide", "Approvals, escalations and an audit log of user actions", "Orion and Nexa explain bottlenecks and staffing gaps from the Command Center and roster"],
    receives: "Escalated cases, staffing gaps and approvals that need a manager.",
    handsOff: "Decisions and re-assigned work back to the departments that own it.",
    shot: "commandCenter",
  },
];

// ------------------------------------------------------------------------------------------------ Home G: why
export const WHY: { title: string; text: string; icon: LucideIcon }[] = [
  { title: "Connected patient information", icon: Stethoscope, text: "Each team sees the same record, so hand-offs don't depend on re-entering details." },
  { title: "Clear task ownership", icon: UserCheck, text: "Every case and task has an owning team or person, a deadline and a history." },
  { title: "Visibility into pending work", icon: Radar, text: "My work shows each person what is theirs; the Command Center shows what the hospital is waiting on." },
  { title: "Repeatable workflows", icon: Workflow, text: "Checklists, verification steps and monitors run the same way every time." },
  { title: "Human-controlled AI", icon: ShieldCheck, text: "AI summarizes and proposes; authorized people approve, sign and decide." },
  { title: "One coordinated hospital", icon: Landmark, text: "Clinical, operational and financial work share one environment with role-based access." },
];

// ------------------------------------------------------------------------------------------------ Platform: five layers
export type Layer = {
  id: string; n: number; title: string; icon: LucideIcon; summary: string; body: string; points: string[];
  example: string; shot?: ShotKey; shotCaption?: string; status?: string;
};
export const LAYERS: Layer[] = [
  {
    id: "records", n: 1, title: "Shared patient records", icon: Stethoscope,
    summary: "One patient identity connects registration, appointments, encounters, orders and results.",
    body: "Every patient has one record. Registration checks for duplicates before creating a new one. Appointments, emergency visits, inpatient stays, notes, orders, results and documents all attach to that record, so any team with permission sees the same history.",
    points: ["Registration with duplicate detection", "Problems, allergies, medications and vitals", "Encounters with signed notes; corrections added as addenda", "Results, documents and a patient timeline"],
    example: "The nurse records vitals at rooming; minutes later the doctor sees them flagged on the same chart.",
    shot: "patientChart",
  },
  {
    id: "workspaces", n: 2, title: "Department workspaces", icon: UsersRound,
    summary: "Each role works on screens built for its responsibilities.",
    body: "Doctors, nurses, pharmacists, laboratory staff, insurance specialists, bed managers and administrators each land on a role Home with their priorities and the tools they use most. The server enforces the same role-based permissions the screens show.",
    points: ["Role Home with priorities and quick actions", "Department boards: ED, beds, lab, radiology, pharmacy, insurance, billing", "Patient portal for patients", "Permissions enforced on the server, not only in the browser"],
    example: "A pharmacist opens a verification queue; an insurance specialist opens upcoming visits with coverage problems.",
    shot: "doctorHome",
  },
  {
    id: "workflows", n: 3, title: "Operational workflows", icon: Workflow,
    summary: "Orders, admissions, approvals, tasks and cases carry work between departments.",
    body: "When work crosses a department boundary, the platform records it: a signed order reaches the lab, an admission request reaches the bed manager, a discharge checklist shows what each team still owes. Sensitive steps — result verification, stock waste, AI proposals — require a second person or an approval.",
    points: ["Orders routed to laboratory, radiology and pharmacy", "Closed-loop medications: sign → pharmacist verifies → dispense → administer", "Admission, transfer and discharge with department tasks", "Cases and tasks with owners, deadlines and escalation", "Two-person checks and approvals where safety matters"],
    example: "A discharge checklist turns a missing medication reconciliation into a task for pharmacy.",
    shot: "myWork", shotCaption: "My work: cases with severity, owner and time overdue. Synthetic data.",
  },
  {
    id: "automation", n: 4, title: "Automation and AI", icon: Bot,
    summary: "Monitors detect predefined problems; HMS Intelligence agents help staff with permitted follow-ups.",
    body: "22 rule-based monitors check hospital records on a schedule and open a case when a defined condition is true — and close it when the record shows the problem is gone. Ten HMS Intelligence agents work inside their departments: staff talk to them from the record they are working on, and they explain, draft and propose actions within the user's permissions. Changes wait for the employee's confirmation or a different person's approval.",
    points: ["Monitors with administrator-set thresholds", "AI assistance on selected cases, once per case, within daily and monthly limits", "Conversations bound to one record, re-checked every message", "Every AI run logged with its tools, model and estimated cost"],
    example: "Low stock opens a case and a purchase request; Veyra, the pharmacy agent, may propose adjusting the quantity for a procurement approver.",
    shot: "agentStudio",
    status: "AI uses a provider an administrator configures. Without one, agents return a clearly labelled rule-based answer.",
  },
  {
    id: "visibility", n: 5, title: "Hospital-wide visibility", icon: Radar,
    summary: "My work shows each person their responsibilities; the Command Center shows the whole hospital.",
    body: "My work collects each person's cases, tasks and approvals in one list. The Command Center shows occupancy, emergency activity, discharges, staffing gaps and open problems grouped by area — and every figure opens the records behind it.",
    points: ["My work: cases, tasks and approvals", "Command Center with traceable figures", "Problems grouped by area, clinical risk first", "Analytics and a daily briefing that lists its sources"],
    example: "A department lead sees three overdue bed-turnover cases on the Command Center and opens the one at the top.",
    shot: "commandCenter",
  },
];

// ------------------------------------------------------------------------------------------------ AI & Automation: building blocks
export const BLOCKS: { id: string; title: string; icon: LucideIcon; kind: string; text: string }[] = [
  { id: "monitors", title: "Automation monitors", icon: Activity, kind: "Rule-based", text: "Predefined checks that run on a schedule and open a case when a defined condition is true. They are not AI." },
  { id: "assistants", title: "AI agents", icon: Bot, kind: "AI", text: "Ten department agents that read permitted information, explain it in conversation, and prepare or propose allowed actions." },
  { id: "cases", title: "Cases and tasks", icon: ClipboardList, kind: "Records", text: "Persistent records that organize each problem, assign an owner, set a deadline and keep a timeline." },
  { id: "approvals", title: "Human approvals", icon: UserCheck, kind: "People", text: "Proposed actions wait until an employee with the required permission approves or rejects them." },
  { id: "command", title: "Command Center", icon: Radar, kind: "Visibility", text: "Hospital-wide view of capacity, activity and open problems, with every figure traceable." },
];

export const FLOW: { title: string; optional?: boolean }[] = [
  { title: "Monitor detects issue" }, { title: "Case tracked" }, { title: "AI assists", optional: true },
  { title: "Action proposed", optional: true }, { title: "Human approval" }, { title: "Task executed" }, { title: "Outcome monitored" },
];

// ------------------------------------------------------------------------------------------------ Home: platform capabilities
/** Implemented capabilities only (verified by backend tests and browser flows). External integrations are simulated. */
export const CLINICAL: { title: string; text: string }[] = [
  { title: "Patient chart", text: "One record with allergies, problems, medications, vitals, results, documents and a timeline." },
  { title: "Encounters & documentation", text: "Visit notes signed by the clinician; corrections added as addenda. Optional AI scribe draft with recorded consent." },
  { title: "Orders & results", text: "Laboratory, imaging, procedure and nursing orders; ICD-10-CM diagnoses; versioned order sets that create draft orders to sign." },
  { title: "Closed-loop medications", text: "Doctor signs → pharmacist verifies → dispense → nurse documents on the eMAR with simulated barcode checks." },
  { title: "Nursing documentation", text: "Flowsheets, structured assessments that freeze when signed, care plans, unit worklists and shift handoffs." },
  { title: "Patient portal & telehealth", text: "Messages, results, pre-visit questionnaires, insurance updates and video visits for patients." },
];
export const OPERATIONS: { title: string; text: string }[] = [
  { title: "Emergency department", text: "Tracking board, nurse-assigned triage (ESI), time in department and boarding." },
  { title: "Inpatient & beds", text: "Admissions, live bed board, transfers, bed turnover and discharge checklists by department." },
  { title: "Operating rooms", text: "OR schedule with case status." },
  { title: "Pharmacy & inventory", text: "Stock by location and lot, expiry, purchase requests with approval, verification queue." },
  { title: "Laboratory & radiology", text: "Specimens with second-person verification, imaging worklists, signed reports, critical-result acknowledgement." },
  { title: "Staffing & Command Center", text: "Roster with eligibility rules and coverage gaps; one hospital-wide view where every figure opens its records." },
];
export const REVENUE: { title: string; text: string }[] = [
  { title: "Insurance verification", text: "Every upcoming visit checked with the payer before arrival (payer connection simulated)." },
  { title: "Prior authorizations", text: "Requests with checklists and expiry tracking." },
  { title: "Charges & claims", text: "Charge capture, claim scrubbing, review findings and submission (clearinghouse simulated)." },
  { title: "Denials & patient billing", text: "Denial work queues, appeals and patient invoices in the portal." },
];
export const SECURITY: { title: string; text: string; icon: LucideIcon }[] = [
  { title: "Role-based access, enforced on the server", icon: ShieldCheck, text: "Every request is checked against the person's role, facility and department — not only the screen." },
  { title: "Organization isolation", icon: Landmark, text: "Each hospital's data is separated in the database itself (row-level security)." },
  { title: "Restricted charts", icon: UserCheck, text: "Sensitive charts are hidden from worklists and require a documented break-the-glass reason." },
  { title: "Independent approvals", icon: ClipboardCheck, text: "Sensitive actions need a second person; nobody — and no workspace switch — can approve their own AI-assisted request." },
  { title: "Audit trail", icon: Activity, text: "Sign-ins, record access, approvals, AI runs and conversation reviews are recorded." },
  { title: "AI limits and switches", icon: Bot, text: "Per-user, per-agent and organization limits; a monthly budget reserved before each call; switches per agent, monitor and platform." },
];

// ------------------------------------------------------------------------------------------------ the 22 monitors
/** Mirrors backend/app/monitors — `key` is the registry key (checked by e2e/public_site_content_check.py). */
export type MonitorInfo = { key: string; name: string; checks: string; owner: string; aiAssist?: boolean };
export type MonitorGroup = { id: string; title: string; icon: LucideIcon; monitors: MonitorInfo[] };
export const MONITOR_GROUPS: MonitorGroup[] = [
  { id: "pharmacy", title: "Pharmacy & stock", icon: Pill, monitors: [
    { key: "pharmacy.expiring", name: "Expiring stock", checks: "Medication lots that expire soon, or already have, at any location.", owner: "Pharmacy", aiAssist: true },
    { key: "inventory.low_stock", name: "Low stock", checks: "Items at or below their reorder point; a purchase request is drafted.", owner: "Pharmacy", aiAssist: true },
    { key: "pharmacy.unusual_usage", name: "Unusual consumption", checks: "Dispensing or waste in the last day far above the usual daily average.", owner: "Pharmacy" },
    { key: "inventory.below_par", name: "Unit stock below par", checks: "A unit holds less than its par level and needs restocking from the main store.", owner: "Pharmacy" },
  ] },
  { id: "insurance", title: "Insurance", icon: ShieldCheck, monitors: [
    { key: "insurance.visit_readiness", name: "Visit readiness", checks: "Coverage for upcoming visits that still can't be verified (payer checks are simulated).", owner: "Insurance team", aiAssist: true },
    { key: "insurance.stored_end_date", name: "Renewal reminders", checks: "A plan's stored end date is approaching; the patient is asked to confirm or upload a new card.", owner: "Insurance team" },
  ] },
  { id: "beds", title: "Beds & discharge", icon: BedDouble, monitors: [
    { key: "beds.cleaning_delay", name: "Bed turnover delay", checks: "A bed waiting for cleaning longer than the target.", owner: "Bed management" },
    { key: "adt.pending_admission", name: "Admission waiting for a bed", checks: "An admission requested with no bed assigned within the target time.", owner: "Bed management" },
    { key: "discharge.not_departed", name: "Discharge ordered, patient not departed", checks: "A discharge order older than the target while the patient still occupies the bed.", owner: "Nursing", aiAssist: true },
  ] },
  { id: "emergency", title: "Emergency", icon: Siren, monitors: [
    { key: "ed.boarding", name: "ED boarding", checks: "An admitted patient waiting in the emergency department for an inpatient bed.", owner: "Bed management" },
    { key: "ed.door_to_provider", name: "Door-to-provider", checks: "A patient not yet seen by a provider within the target for their nurse-assigned acuity.", owner: "ED clinicians" },
  ] },
  { id: "lab", title: "Laboratory", icon: FlaskConical, monitors: [
    { key: "lab.critical_unacknowledged", name: "Critical result not acknowledged", checks: "A verified critical lab value the responsible clinician hasn't acknowledged.", owner: "Responsible clinician" },
    { key: "lab.turnaround", name: "Turnaround and specimen delays", checks: "Specimens collected but not received, or received but not verified, beyond the target.", owner: "Laboratory" },
  ] },
  { id: "radiology", title: "Radiology", icon: ScanLine, monitors: [
    { key: "radiology.unread", name: "Studies awaiting a report", checks: "Completed imaging studies not yet signed by a radiologist beyond the target.", owner: "Radiology" },
    { key: "radiology.critical_unacknowledged", name: "Critical finding not acknowledged", checks: "A report flagged critical that the ordering clinician hasn't acknowledged.", owner: "Ordering clinician" },
  ] },
  { id: "revenue", title: "Revenue", icon: Receipt, monitors: [
    { key: "billing.prior_auth_required", name: "Prior authorization needed", checks: "A signed order the payer requires authorization for, with none approved; the request is drafted.", owner: "Insurance team" },
    { key: "billing.prior_auth_expiring", name: "Prior authorization expiring", checks: "An approved authorization expiring before the service is performed.", owner: "Insurance team" },
    { key: "billing.claims_on_hold", name: "Claims on hold", checks: "Claims stuck in draft or denied without an appeal beyond the target.", owner: "Billing", aiAssist: true },
  ] },
  { id: "staffing", title: "Staffing", icon: UsersRound, monitors: [
    { key: "staffing.coverage_gap", name: "Coverage gap", checks: "A shift in the next 48 hours with fewer staff than its minimum; eligible staff are suggested.", owner: "Hospital administration", aiAssist: true },
  ] },
  { id: "equipment", title: "Equipment", icon: Wrench, monitors: [
    { key: "equipment.maintenance_due", name: "Maintenance due", checks: "Preventive maintenance due soon or overdue for equipment in service.", owner: "Hospital administration" },
  ] },
  { id: "journey", title: "Patient journey", icon: CalendarDays, monitors: [
    { key: "journey.follow_up_not_booked", name: "Follow-up not booked", checks: "A visit documented a follow-up plan, but no future appointment exists.", owner: "Front desk" },
    { key: "journey.intake_missing", name: "Pre-visit questionnaire missing", checks: "Upcoming visits whose questionnaire isn't submitted; one portal reminder is sent.", owner: "Front desk" },
  ] },
];
export const MONITOR_COUNT = MONITOR_GROUPS.reduce((n, g) => n + g.monitors.length, 0);

// ------------------------------------------------------------------------------------------------ the 10 assistants
/** Mirrors backend/app/agents/runner.py DEFAULTS. `start`: how a person reaches it; `auto`: case kinds it may assist automatically. */
export type AssistantInfo = {
  key: string; name: string; brand?: string; icon: LucideIcon; does: string; start: "Launched by staff" | "Runs inside a workflow";
  where: string; proposes: string; auto?: string; never: string;
};
export const ASSISTANTS: AssistantInfo[] = [
  { brand: "Aurelia", key: "insurance_guardian", name: "Insurance Guardian", icon: ShieldCheck, start: "Launched by staff", where: "Chat panel in each insurance case and the Insurance workspace",
    does: "Reviews coverage problems before visits and explains what is blocking each one.", proposes: "Staff tasks, patient messages, insurance update requests",
    auto: "New visit-readiness cases", never: "Never claims a payer confirmed coverage." },
  { brand: "Aster", key: "doctor_assistant", name: "Doctor Assistant", icon: Stethoscope, start: "Runs inside a workflow", where: "The patient chart's Ask AI conversation",
    does: "Answers questions about one patient's chart, citing the records it used.", proposes: "Nothing — answers only",
    never: "Never diagnoses, prescribes or writes to the chart." },
  { brand: "Sonara", key: "medical_scribe", name: "Medical Scribe", icon: ClipboardList, start: "Runs inside a workflow", where: "The visit's Scribe panel, with patient consent; ask questions about the draft",
    does: "Drafts a structured visit note from a consented conversation.", proposes: "A draft note for the clinician",
    never: "Never signs; nothing is saved to the chart until the clinician signs." },
  { brand: "Lucent", key: "document_intelligence", name: "Document Intelligence", icon: FileSearch, start: "Runs inside a workflow", where: "When a document is uploaded; ask questions in document review",
    does: "Classifies incoming documents and extracts key details.", proposes: "A classification and extracted details for staff review",
    never: "Its output is reviewed by staff before it is relied on." },
  { brand: "Veyra", key: "pharmacy_watchdog", name: "Pharmacy Watchdog", icon: Pill, start: "Launched by staff", where: "Pharmacy cases, item details and the Pharmacy workspace",
    does: "Explains stock alerts — low, expiring or unusual usage — and prepares staff actions.", proposes: "Staff tasks; adjusting a drafted purchase quantity",
    auto: "New low-stock and expiring-stock cases", never: "Never prescribes, dispenses or wastes stock." },
  { brand: "Elara", key: "discharge_coordination", name: "Discharge Coordination", icon: ClipboardCheck, start: "Launched by staff", where: "Each stay's discharge checklist and discharge cases",
    does: "Summarizes what is still outstanding for a discharge and who owns it.", proposes: "Coordination tasks",
    auto: "New discharge-not-departed cases", never: "Never decides clinical readiness for discharge." },
  { brand: "Orion", key: "hospital_operations", name: "Hospital Operations", icon: Hospital, start: "Launched by staff", where: "Command Center and operational case drawers",
    does: "Explains operational issues using current figures, open cases and staffing gaps.", proposes: "Administrative tasks",
    never: "Never changes operational records directly." },
  { brand: "Valora", key: "claims_review", name: "Claims Review", icon: Receipt, start: "Launched by staff", where: "Each claim, billing cases and the Revenue workspace",
    does: "Identifies possibly missing billing information on claims.", proposes: "Review tasks for the billing team",
    auto: "New claims-on-hold cases", never: "Never edits, codes or submits claims." },
  { brand: "Liora", key: "patient_communication", name: "Patient Communication", icon: MessageSquare, start: "Launched by staff", where: "Each message thread and the Messages workspace",
    does: "Drafts routine administrative messages to patients.", proposes: "Patient messages for staff approval",
    never: "Never sends a message without approval; never gives clinical advice." },
  { brand: "Nexa", key: "staff_scheduling", name: "Staff Scheduling", icon: UsersRound, start: "Launched by staff", where: "Staffing cases and the Roster workspace",
    does: "Explains staffing gaps and the eligible alternatives the scheduler found.", proposes: "Tasks for a manager",
    auto: "Escalated coverage-gap cases", never: "Never changes assignments — managers decide." },
];

// ------------------------------------------------------------------------------------------------ responsible AI
export const RESPONSIBLE: { title: string; text: string; icon: LucideIcon }[] = [
  { title: "Conversations inside the work", icon: MessageSquare, text: "Staff open the department assistant from the case, claim, stay, thread or chart they are working on, ask follow-up questions, and pick up the same conversation later. The record is checked against their access on every message." },
  { title: "Authorized tool access", icon: ShieldCheck, text: "Each agent has its own list of allowed tools, and every tool call is checked again on the server against the user's permissions." },
  { title: "Human approval", icon: UserCheck, text: "Anything that would change data — a task, a patient message, a purchase quantity — waits for a different person with permission, and the conversation shows the real outcome. Small internal steps, like a case note, run only after the employee confirms." },
  { title: "Execution logging", icon: ClipboardList, text: "Every AI run records its trigger, the tools it used, the model, tokens and estimated cost, and appears in the audit log." },
  { title: "Model configuration", icon: Wrench, text: "Administrators choose the AI provider and models, set per-run and organization limits, and can disable any agent per facility." },
  { title: "Live or simulated, always labelled", icon: Activity, text: "Each answer shows whether a live AI provider produced it or a rule-based simulation did." },
  { title: "Clinical decisions stay with clinicians", icon: Stethoscope, text: "AI does not diagnose, prescribe, sign notes, change claims or message patients on its own." },
];

// ------------------------------------------------------------------------------------------------ status (About, AI page)
export type StatusRow = { label: string; tone: "success" | "info" | "warning" | "danger" | "neutral"; text: string };
export const PRODUCT_STATUS: StatusRow[] = [
  { label: "Implemented", tone: "success", text: "The workflows described on this site — patient records, scheduling, emergency and inpatient care, closed-loop inpatient medication management with an eMAR, nursing flowsheets, assessments and care plans, ICD-10-CM diagnosis coding, versioned order sets, pharmacy, laboratory, radiology, insurance and billing workflows, the 22 monitors, cases and approvals, the Command Center and the patient portal — run end to end on a real database with automated tests." },
  { label: "Synthetic data", tone: "info", text: "All testing and every screenshot on this site use synthetic patients. No real patient information is used." },
  { label: "AI verification", tone: "info", text: "Conversations, tools, approvals and limits are verified by automated tests with the rule-based mode and a mocked model; an earlier agent run completed against a live provider (OpenAI) in development. Live-provider answer quality for every agent, scribe transcription, document reading and realtime voice is not yet verified end to end." },
  { label: "Simulated", tone: "neutral", text: "Payer eligibility, the claims clearinghouse, payer decisions, card payments, supplier orders, the imaging archive (PACS), e-prescribing transmission, email/text delivery and barcode scanning on the medication administration record are simulated and labelled in the application." },
  { label: "Not licensed", tone: "warning", text: "CPT procedure codes, SNOMED CT and a commercial drug-interaction knowledge base are not included. Interaction screening is shown as unavailable — never as \"no interactions\" — and pharmacists confirm a manual review." },
  { label: "In development", tone: "warning", text: "HMS Workflows is a developing healthcare software system. It has not been deployed in a hospital." },
  { label: "Not certified", tone: "danger", text: "It is not certified for clinical use and is not represented as HIPAA-compliant or ONC-certified." },
];

// ------------------------------------------------------------------------------------------------ About
export const APPROACH: [string, string][] = [
  ["One connected hospital environment", "Clinical, operational and financial work share one platform, so a change in one department is visible wherever it matters."],
  ["Shared information, role-based access", "Everyone works from the same record, and each role sees and does what its permissions allow — enforced on the server."],
  ["Workflow-first design", "Screens are built around the work each role performs and the hand-offs between teams, not around database tables."],
  ["Operational visibility", "Each person sees their own work; leaders see where the hospital is waiting, and every figure can be traced to its records."],
  ["Automation for repeatable checks", "Rules handle the checks that should happen every time, the same way, and turn problems into owned cases."],
  ["AI assistance with human oversight", "AI summarizes, drafts and proposes within permissions. People review, approve and sign."],
];
