/**
 * HMS Intelligence — the ten department AI agents as presented on the public website.
 *
 * Every capability below is implemented and covered by tests (backend/tests/test_hms_assist.py, e2e/assist_flow.py):
 * reads go through permission- and facility-checked tools; "approval" actions are proposals a DIFFERENT authorized
 * person approves; "confirm" actions run only when the employee confirms. Display names are marketing names (not
 * trademark-cleared); internal agent keys are unchanged. Keep this file in sync with backend/app/agents/runner.py.
 */
import { BadgeDollarSign, ClipboardCheck, FileSearch, HeartPulse, Hospital, MessageSquareText, Mic, Pill, ShieldCheck, UsersRound, type LucideIcon } from "lucide-react";

export type Turn = { from: "staff" | "agent" | "system"; text: string };
export type AgentProfile = {
  key: string; name: string; role: string; tagline: string; icon: LucideIcon; hue: string;
  team: string; where: string; summary: string; ask: string[]; helps: string[]; approval: string[]; confirm: string[];
  never: string[]; automation?: string; example: Turn[];
};

export const INTELLIGENCE = {
  name: "HMS Intelligence",
  line: "Ten specialized AI agents, each working inside its own department.",
  text: "Staff open the agent from the case, claim, stay, message, chart or document they are already working on. The agent reads only what that person may see, explains it with references to the records, and prepares the next step. Anything that changes data waits for the employee's confirmation or for a different authorized person's approval, and the conversation shows the real result.",
};

export const AGENTS: AgentProfile[] = [
  {
    key: "insurance_guardian", name: "Aurelia", role: "Insurance & Coverage AI", tagline: "Coverage problems, explained before the patient arrives.",
    icon: ShieldCheck, hue: "#2563eb", team: "Insurance specialists, front desk", where: "Each insurance case, Insurance Guardian, patient coverage",
    summary: "Aurelia reads the insurance case, the patient's coverage state and recent payer checks, explains what is blocking verification, and prepares the follow-up.",
    ask: ["Why is this patient's insurance unverified?", "Show the latest payer-check evidence", "Prepare a follow-up task"],
    helps: ["Explains the case with its evidence and timeline", "Summarizes recent eligibility checks and patient update requests"],
    approval: ["Follow-up task for the insurance team", "Request asking the patient to confirm insurance in the portal", "Administrative portal message to the patient"],
    confirm: ["Re-run the eligibility check", "Add a note to the case"],
    never: ["Claim a payer confirmed coverage — payer checks in this environment are simulated", "Override a coverage hold"],
    automation: "Assists new visit-readiness cases automatically, once per case.",
    example: [
      { from: "staff", text: "Aurelia, why is this patient's insurance unverified?" },
      { from: "agent", text: "Case C1015: the payer could not be reached on the last two checks, so coverage for the Nov 25 visit is unconfirmed. The insurance on file has no recent successful check." },
      { from: "staff", text: "Prepare a follow-up task." },
      { from: "agent", text: "Proposal created for the insurance specialist team. It is waiting for a different authorized person to approve it in My Work — nothing has changed yet." },
      { from: "system", text: "Approved and executed — task created. Open task →" },
    ],
  },
  {
    key: "pharmacy_watchdog", name: "Veyra", role: "Pharmacy & Inventory AI", tagline: "Stock risks, with the numbers behind them.",
    icon: Pill, hue: "#0d9488", team: "Pharmacists, pharmacy management", where: "Pharmacy cases, item details, the Pharmacy workspace",
    summary: "Veyra explains low, expiring or unusual stock using on-hand quantities, consumption and the reorder recommendation, and prepares pharmacy follow-up.",
    ask: ["How many days of supply are left?", "Is there an open purchase request?", "Prepare a follow-up task for a pharmacist"],
    helps: ["Stock on hand for your facilities, average use and days of supply", "Reorder recommendation with its method", "Recent purchase requests"],
    approval: ["Pharmacist follow-up task", "Change of a submitted purchase-request quantity (within 50–200% of the recommendation, procurement approver)"],
    confirm: ["Add a note to the case"],
    never: ["Prescribe, verify, dispense, administer or waste medication", "Receive stock or place purchases"],
    automation: "Assists new low-stock and expiring-stock cases; unusual-usage assistance can be switched on.",
    example: [
      { from: "staff", text: "Veyra, explain this stock alert." },
      { from: "agent", text: "Ondansetron 4 mg: 38 vials on hand in your facilities, about 9 used per day — roughly 4 days of supply. Recommended reorder: 160 (28-day average × lead time + 14 days − on hand)." },
      { from: "staff", text: "Prepare a follow-up task for a pharmacist." },
      { from: "agent", text: "Proposal created for a pharmacist. It needs approval before the task exists." },
    ],
  },
  {
    key: "discharge_coordination", name: "Elara", role: "Discharge Coordination AI", tagline: "What a discharge is still waiting on, and who owns it.",
    icon: ClipboardCheck, hue: "#7c3aed", team: "Nurses, bed managers, physicians", where: "Each stay's discharge checklist, discharge cases",
    summary: "Elara reads the discharge checklist and the stay's operational status, lists what is still open and which team owns each item, and prepares coordination tasks.",
    ask: ["What is this discharge waiting on?", "Who owns each open item?", "Prepare a coordination task"],
    helps: ["Open checklist items with owners", "Length of stay, discharge-order time, open tasks, medication orders awaiting pharmacy"],
    approval: ["Coordination task for nursing, bed management, pharmacy or the physician"],
    confirm: ["Add a note to the case"],
    never: ["Decide clinical readiness", "Order or complete a discharge"],
    automation: "Assists new discharge-not-departed cases.",
    example: [
      { from: "staff", text: "Elara, what is this discharge waiting on?" },
      { from: "agent", text: "Two items are open: discharge medication reconciliation (pharmacist) and transport (bed manager). The discharge order was placed 3 hours ago." },
      { from: "staff", text: "Prepare a coordination task for transport." },
      { from: "agent", text: "Proposal created for the bed manager. Waiting for approval." },
    ],
  },
  {
    key: "hospital_operations", name: "Orion", role: "Hospital Operations AI", tagline: "Today's bottlenecks, with the cases behind them.",
    icon: Hospital, hue: "#0f766e", team: "Hospital administrators, bed managers", where: "Command Center and every operational case",
    summary: "Orion explains operational issues using the Command Center figures, open cases, recent volume and staffing gaps, and prepares administrative follow-up.",
    ask: ["Explain today's bottlenecks", "Which cases are overdue?", "Add a note to this case"],
    helps: ["Bed, ED and discharge figures with their sources", "Open and overdue cases, 7-day volume, staffing gaps"],
    approval: ["Administrative follow-up task"],
    confirm: ["Add a note to the case timeline"],
    never: ["Assign beds, transfer or discharge patients", "Change clinical records"],
    automation: "Assistance for escalated bed, admission and ED-boarding cases can be switched on.",
    example: [
      { from: "staff", text: "Orion, explain today's bottlenecks." },
      { from: "agent", text: "4 admitted ED patients are waiting for beds; 3 beds are waiting for cleaning (oldest 52 minutes, case C1042). Discharges are behind on Med-Surg." },
      { from: "staff", text: "Add a note: EVS supervisor called, rooms ready in 20 minutes." },
      { from: "agent", text: "Prepared for your confirmation." },
      { from: "system", text: "Note added to case C1042 after you confirmed." },
    ],
  },
  {
    key: "claims_review", name: "Valora", role: "Billing & Claims AI", tagline: "Why a claim is held, and what is missing.",
    icon: BadgeDollarSign, hue: "#b45309", team: "Billing team, insurance specialists", where: "Each claim, billing cases, the Revenue workspace",
    summary: "Valora reads the claim, its scrub errors, open review findings and any denial, explains what is missing, and prepares the billing team's next step.",
    ask: ["Why is this claim on hold?", "List the open findings", "Re-scrub this claim"],
    helps: ["Claim status, payer, amounts, scrub errors and denial reason", "Open review findings"],
    approval: ["Billing review task"],
    confirm: ["Re-scrub an unsubmitted, rejected or denied claim", "Add a note to the case"],
    never: ["Invent or change codes", "Edit, submit, void or appeal claims — the clearinghouse here is simulated"],
    automation: "Assists new claims-on-hold cases; prior-authorization cases can be switched on.",
    example: [
      { from: "staff", text: "Valora, why is this claim on hold?" },
      { from: "agent", text: "Claim CLM-2049 has one scrub error: the member ID on the claim doesn't match the active insurance. There are no open findings." },
      { from: "staff", text: "Re-scrub this claim." },
      { from: "agent", text: "Prepared for your confirmation — it runs with your billing permissions." },
    ],
  },
  {
    key: "patient_communication", name: "Liora", role: "Patient Communication AI", tagline: "Clear administrative messages, reviewed before they go out.",
    icon: MessageSquareText, hue: "#db2777", team: "Front desk, care coordinators", where: "Each message thread and the Messages workspace",
    summary: "Liora summarizes a patient's message thread and drafts administrative replies and reminders. Every message is approved by a staff member before it is posted in the portal.",
    ask: ["Summarize this conversation", "Draft an administrative reply", "Draft an insurance reminder"],
    helps: ["Thread summary with the latest patient message"],
    approval: ["Portal reply or new administrative message (posted under the approving staff member; the patient's channel preferences apply)"],
    confirm: [],
    never: ["Send anything without approval", "Give clinical advice"],
    automation: "Assistance for follow-ups that were never booked can be switched on.",
    example: [
      { from: "staff", text: "Liora, summarize this conversation." },
      { from: "agent", text: "The patient asks where to park for Thursday's visit. No clinical question is involved." },
      { from: "staff", text: "Draft a reply." },
      { from: "agent", text: "Draft proposed. A staff member approves it before it is posted in the portal." },
    ],
  },
  {
    key: "staff_scheduling", name: "Nexa", role: "Staff Scheduling AI", tagline: "Coverage gaps, with eligible people already checked.",
    icon: UsersRound, hue: "#4f46e5", team: "Staffing managers, hospital administrators", where: "Staffing cases and the Roster workspace",
    summary: "Nexa finds departments below minimum staffing in the next 48 hours and lists staff who pass the hard rules — role, overlap, time off, rest, weekly hours and credentials. Managers decide.",
    ask: ["Which departments are short in the next 48 hours?", "Who could cover the first gap?", "Prepare a task for the staffing manager"],
    helps: ["Staffing gaps in your facilities", "Eligible cover candidates with reasons"],
    approval: ["Task for a staffing manager"],
    confirm: [],
    never: ["Assign, cancel or swap shifts", "Override credential, rest or hour limits"],
    automation: "Assists escalated coverage-gap cases.",
    example: [
      { from: "staff", text: "Nexa, who could cover the ICU night gap?" },
      { from: "agent", text: "ICU is one nurse short for tonight's night window. Two nurses are eligible: both have current credentials, one has 24 h this week, the other 30 h." },
      { from: "staff", text: "Prepare a task for the staffing manager." },
      { from: "agent", text: "Proposal created — a manager approves the task and decides the assignment in the roster." },
    ],
  },
  {
    key: "doctor_assistant", name: "Aster", role: "Patient Chart AI", tagline: "Answers from one chart, with every source cited.",
    icon: HeartPulse, hue: "#0284c7", team: "Physicians, nurses", where: "The patient chart and encounter (Ask AI)",
    summary: "Aster answers questions about the selected patient's chart — allergies, medications, problems, visits, results and filed documents — and cites the record behind every statement.",
    ask: ["Summarize this patient's history", "List current medications", "What happened at the last visit?"],
    helps: ["Cited answers from one authorized chart; follow-up questions in the same conversation"],
    approval: [], confirm: [],
    never: ["Diagnose, prescribe or order — those requests are refused", "Sign or change documentation", "Use information outside this chart"],
    example: [
      { from: "staff", text: "Aster, list current medications." },
      { from: "agent", text: "Metformin 500 mg twice daily [S4]; lisinopril 10 mg daily [S5]. No active allergies are recorded [S1]." },
      { from: "staff", text: "Should I increase the metformin?" },
      { from: "agent", text: "I can't make prescribing decisions. I can show the latest A1c and kidney results to support yours." },
    ],
  },
  {
    key: "medical_scribe", name: "Sonara", role: "Medical Scribe AI", tagline: "A draft note from a consented visit — the clinician decides.",
    icon: Mic, hue: "#9333ea", team: "Physicians", where: "The encounter's Scribe panel, with recorded consent",
    summary: "Sonara turns a consented visit conversation into a structured SOAP draft and answers questions about where each part came from. The clinician edits, applies and signs.",
    ask: ["Where in the transcript does the plan come from?", "What did the patient say about symptoms?", "Shorten the plan section"],
    helps: ["SOAP draft from the consented transcript", "Questions about the transcript and the draft"],
    approval: [], confirm: ["Revise one section of the draft (the draft only — not the note)"],
    never: ["Apply the draft to the note or sign it", "Record without consent", "Add facts that are not in the transcript"],
    example: [
      { from: "staff", text: "Sonara, shorten the plan section." },
      { from: "agent", text: "Prepared a shorter plan for your confirmation. Applying it to the note and signing stay with you." },
    ],
  },
  {
    key: "document_intelligence", name: "Lucent", role: "Document Intelligence AI", tagline: "Incoming documents, classified and ready for review.",
    icon: FileSearch, hue: "#475569", team: "Medical records, front desk, nursing", where: "Document upload and the review queue",
    summary: "Lucent classifies incoming documents, extracts key details and patient identifiers, and answers questions about the extraction. Staff confirm identity before anything is filed.",
    ask: ["Why was it classified this way?", "Do the identifiers match a patient?", "What is uncertain in this extraction?"],
    helps: ["Classification, summary, findings and uncertainties", "Patient-match candidates with reasons"],
    approval: ["Routing task"], confirm: [],
    never: ["File, reject or merge documents", "Change patient records from unverified extraction"],
    example: [
      { from: "staff", text: "Lucent, do the identifiers match a patient?" },
      { from: "agent", text: "The name and date of birth match one patient; the MRN is missing on the document, so identity needs your confirmation before filing." },
    ],
  },
];
