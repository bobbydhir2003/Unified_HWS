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
  agentStudio: { src: "agent-studio", w: 1440, h: 900, alt: "AI Agent Studio: each assistant with what it reads, what it may propose for approval, and its limits (synthetic data)" },
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
    helps: "Monitors create the routine tasks and reminders, and AI assistants can summarize a case and propose the next step for a person to approve." },
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
  { id: "ai-automation", title: "AI-Assisted Automation", icon: Bot, to: "/ai-automation",
    text: "Rules watch for known problems; AI assistants help people understand them and prepare the next step.",
    includes: ["22 predefined automation monitors", "10 specialized AI assistants", "Proposed actions wait for approval", "Every AI run is logged"] },
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
      { title: "Doctor", team: "Doctor", icon: Stethoscope, happens: "The doctor reviews history, documents the encounter and places orders. An AI scribe can draft the note with consent.", platform: "The draft waits for the doctor to review and sign." },
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
  { who: "AI (optional)", title: "Insurance Guardian reviews the case", text: "If an administrator has enabled AI, the assistant reads the case and the patient's coverage — only information it is permitted to see." },
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
    support: ["Registration with duplicate detection", "Conflict-checked scheduling, check-in and check-out", "Pre-visit questionnaires and reminders through the patient portal", "Insurance cases opened before the visit, not at the desk"],
    receives: "Insurance cases, missing-questionnaire reminders and follow-ups that still need booking.",
    handsOff: "A registered, checked-in patient whose record every clinical team uses.",
    shot: "patientPortal", shotCaption: "The patient portal: one to-do list before the next visit. Synthetic data.",
  },
  {
    id: "clinical", title: "Doctors & Clinical Teams", icon: Stethoscope,
    short: "Work from one chart: history, documentation, orders and results.",
    struggle: "Clinicians need the full picture quickly, and too much of their time goes to documentation and chasing results across departments.",
    support: ["A role Home with priorities grouped by patient", "One chart with allergies and abnormal vitals clearly marked", "Encounters with signing and addenda; an optional AI scribe draft with consent", "Orders, results and critical-result acknowledgement", "Ask AI on the chart: answers drawn from that patient's record, with citations"],
    receives: "Vitals from nursing, verified results from the lab and radiology, and critical results that need acknowledgement.",
    handsOff: "Signed orders to the lab, radiology and pharmacy; admission requests; discharge decisions.",
    shot: "doctorHome",
  },
  {
    id: "nursing", title: "Nursing & Inpatient Teams", icon: HeartPulse,
    short: "Triage, vitals, care tasks, beds, transfers and discharge.",
    struggle: "Nurses and bed managers coordinate many patients at once, and a single missing step can hold up a bed or a discharge.",
    support: ["ED tracking board with nurse-recorded acuity", "Unit worklists with overdue-vitals flags and handoffs", "Admission requests, live bed board and transfers", "A discharge checklist showing what each department still owes"],
    receives: "Admission requests, discharge orders, and cases for boarding, bed turnover and delayed departures.",
    handsOff: "Vitals and observations to the chart; freed beds back to the bed board.",
    shot: "edBoard",
  },
  {
    id: "diagnostics-pharmacy", title: "Diagnostics & Pharmacy", icon: FlaskConical,
    short: "Laboratory, radiology, medication verification and stock.",
    struggle: "Diagnostic and pharmacy teams receive work from every ward and must keep safety checks intact while working quickly.",
    support: ["Specimen collection, receipt and independent result verification", "Imaging worklist with signed radiology reports", "Pharmacist verification of new medication orders", "Lots, expiry and stock levels, with two-person approval for waste", "Purchase requests when stock runs low"],
    receives: "Signed orders from clinicians, and cases for expiring stock, low stock, unusual usage and slow turnaround.",
    handsOff: "Verified results and signed reports back to the ordering clinician's chart.",
    example: { title: "Example: a lab result", steps: ["Doctor signs the order", "Lab collects and receives the specimen", "A second person verifies the result", "Result returns to the chart", "A critical value must be acknowledged"] },
  },
  {
    id: "revenue", title: "Insurance & Revenue Teams", icon: Receipt,
    short: "Coverage readiness, prior authorizations, claims and balances.",
    struggle: "Coverage and claim problems found after the visit turn into rework, denials and surprise bills.",
    support: ["Insurance Guardian: coverage checks before visits, with cases for problems", "Prior authorizations drafted when a signed order needs one", "Claims reviewed before submission; denials and appeals tracked", "Patient statements and balances in the portal"],
    receives: "Upcoming visits needing coverage, signed orders needing authorization, and claims on hold.",
    handsOff: "Ready coverage to the front desk; questions to patients through approved messages.",
    shot: "insuranceGuardian",
  },
  {
    id: "leadership", title: "Hospital Leadership", icon: Radar,
    short: "Hospital-wide visibility, operational cases and accountability.",
    struggle: "Leaders need to know where the hospital is waiting and who owns each delay, without collecting reports from every department.",
    support: ["Command Center: hospital status, grouped problems and department detail", "Every figure opens the records behind it", "Staffing gaps with eligible staff suggested; managers decide", "Approvals, escalations and an audit log of user actions"],
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
    points: ["Orders routed to laboratory, radiology and pharmacy", "Admission, transfer and discharge with department tasks", "Cases and tasks with owners, deadlines and escalation", "Two-person checks and approvals where safety matters"],
    example: "A discharge checklist turns a missing medication reconciliation into a task for pharmacy.",
    shot: "myWork", shotCaption: "My work: cases with severity, owner and time overdue. Synthetic data.",
  },
  {
    id: "automation", n: 4, title: "Automation and AI", icon: Bot,
    summary: "Monitors detect predefined problems; AI assistants help with permitted follow-ups.",
    body: "22 rule-based monitors check hospital records on a schedule and open a case when a defined condition is true — and close it when the record shows the problem is gone. Ten specialized AI assistants can summarize, draft and propose actions within the user's permissions. Proposals wait for a person to approve.",
    points: ["Monitors with administrator-set thresholds", "AI assistance on selected new cases, within daily limits", "Proposals approved by people with permission", "Every AI run logged with its tools, model and cost"],
    example: "Low stock opens a case and a purchase request; Pharmacy Watchdog may propose adjusting the quantity for a pharmacist to approve.",
    shot: "agentStudio",
    status: "AI uses a provider an administrator configures. Without one, assistants return a clearly labelled rule-based summary.",
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
  { id: "assistants", title: "AI assistants", icon: Bot, kind: "AI", text: "Specialized assistants that read permitted information, summarize, draft and propose allowed actions." },
  { id: "cases", title: "Cases and tasks", icon: ClipboardList, kind: "Records", text: "Persistent records that organize each problem, assign an owner, set a deadline and keep a timeline." },
  { id: "approvals", title: "Human approvals", icon: UserCheck, kind: "People", text: "Proposed actions wait until an employee with the required permission approves or rejects them." },
  { id: "command", title: "Command Center", icon: Radar, kind: "Visibility", text: "Hospital-wide view of capacity, activity and open problems, with every figure traceable." },
];

export const FLOW: { title: string; optional?: boolean }[] = [
  { title: "Monitor detects issue" }, { title: "Case tracked" }, { title: "AI assists", optional: true },
  { title: "Action proposed", optional: true }, { title: "Human approval" }, { title: "Task executed" }, { title: "Outcome monitored" },
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
  key: string; name: string; icon: LucideIcon; does: string; start: "Launched by staff" | "Runs inside a workflow";
  where: string; proposes: string; auto?: string; never: string;
};
export const ASSISTANTS: AssistantInfo[] = [
  { key: "insurance_guardian", name: "Insurance Guardian", icon: ShieldCheck, start: "Launched by staff", where: "Insurance workspace, Agent Studio",
    does: "Reviews coverage problems before visits and explains what is blocking each one.", proposes: "Staff tasks, patient messages, insurance update requests",
    auto: "New visit-readiness cases", never: "Never claims a payer confirmed coverage." },
  { key: "doctor_assistant", name: "Doctor Assistant", icon: Stethoscope, start: "Runs inside a workflow", where: "The patient chart's Ask AI panel",
    does: "Answers questions about one patient's chart, citing the records it used.", proposes: "Nothing — answers only",
    never: "Never diagnoses, prescribes or writes to the chart." },
  { key: "medical_scribe", name: "Medical Scribe", icon: ClipboardList, start: "Runs inside a workflow", where: "The visit's Scribe panel, with patient consent",
    does: "Drafts a structured visit note from a consented conversation.", proposes: "A draft note for the clinician",
    never: "Never signs; nothing is saved to the chart until the clinician signs." },
  { key: "document_intelligence", name: "Document Intelligence", icon: FileSearch, start: "Runs inside a workflow", where: "When a document is uploaded",
    does: "Classifies incoming documents and extracts key details.", proposes: "A classification and extracted details for staff review",
    never: "Its output is reviewed by staff before it is relied on." },
  { key: "pharmacy_watchdog", name: "Pharmacy Watchdog", icon: Pill, start: "Launched by staff", where: "Pharmacy workspace, Agent Studio",
    does: "Explains stock alerts — low, expiring or unusual usage — and prepares staff actions.", proposes: "Staff tasks; adjusting a drafted purchase quantity",
    auto: "New low-stock and expiring-stock cases", never: "Never prescribes, dispenses or wastes stock." },
  { key: "discharge_coordination", name: "Discharge Coordination", icon: ClipboardCheck, start: "Launched by staff", where: "Inpatient workspace, Agent Studio",
    does: "Summarizes what is still outstanding for a discharge and who owns it.", proposes: "Coordination tasks",
    auto: "New discharge-not-departed cases", never: "Never decides clinical readiness for discharge." },
  { key: "hospital_operations", name: "Hospital Operations", icon: Hospital, start: "Launched by staff", where: "Command Center, Agent Studio",
    does: "Explains operational issues using current figures, open cases and staffing gaps.", proposes: "Administrative tasks",
    never: "Never changes operational records directly." },
  { key: "claims_review", name: "Claims Review", icon: Receipt, start: "Launched by staff", where: "Revenue workspace, Agent Studio",
    does: "Identifies possibly missing billing information on claims.", proposes: "Review tasks for the billing team",
    auto: "New claims-on-hold cases", never: "Never edits, codes or submits claims." },
  { key: "patient_communication", name: "Patient Communication", icon: MessageSquare, start: "Launched by staff", where: "Messages workspace, Agent Studio",
    does: "Drafts routine administrative messages to patients.", proposes: "Patient messages for staff approval",
    never: "Never sends a message without approval; never gives clinical advice." },
  { key: "staff_scheduling", name: "Staff Scheduling", icon: UsersRound, start: "Launched by staff", where: "Roster workspace, Agent Studio",
    does: "Explains staffing gaps and the eligible alternatives the scheduler found.", proposes: "Tasks for a manager",
    auto: "Escalated coverage-gap cases", never: "Never changes assignments — managers decide." },
];

// ------------------------------------------------------------------------------------------------ responsible AI
export const RESPONSIBLE: { title: string; text: string; icon: LucideIcon }[] = [
  { title: "Authorized tool access", icon: ShieldCheck, text: "Each assistant has its own list of allowed tools, and every tool call is checked again on the server against the user's permissions." },
  { title: "Human approval", icon: UserCheck, text: "Anything that would change data — a task, a patient message, a purchase quantity — waits for a person with permission." },
  { title: "Execution logging", icon: ClipboardList, text: "Every AI run records its trigger, the tools it used, the model, tokens and estimated cost, and appears in the audit log." },
  { title: "Model configuration", icon: Wrench, text: "Administrators choose the AI provider and models, set per-run limits, and can disable any assistant." },
  { title: "Live or simulated, always labelled", icon: Activity, text: "Each answer shows whether a live AI provider produced it or a rule-based simulation did." },
  { title: "Clinical decisions stay with clinicians", icon: Stethoscope, text: "AI does not diagnose, prescribe, sign notes, change claims or message patients on its own." },
];

// ------------------------------------------------------------------------------------------------ status (About, AI page)
export type StatusRow = { label: string; tone: "success" | "info" | "warning" | "danger" | "neutral"; text: string };
export const PRODUCT_STATUS: StatusRow[] = [
  { label: "Implemented", tone: "success", text: "The workflows described on this site — patient records, scheduling, emergency and inpatient care, pharmacy, laboratory, radiology, insurance and billing workflows, the 22 monitors, cases and approvals, the Command Center and the patient portal — run end to end on a real database with automated tests." },
  { label: "Synthetic data", tone: "info", text: "All testing and every screenshot on this site use synthetic patients. No real patient information is used." },
  { label: "AI verification", tone: "info", text: "An AI agent run has completed against a live provider (OpenAI) in development. The scribe's transcription, document reading, chart assistant and realtime voice have not yet been verified end to end with a live provider." },
  { label: "Simulated", tone: "neutral", text: "Payer eligibility, the claims clearinghouse, payer decisions, card payments, supplier orders, the imaging archive (PACS), e-prescribing transmission and email/text delivery are simulated and labelled in the application." },
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
