/**
 * Help & About content — typed, frontend-only. Every route and button label here is taken from the running app;
 * update this file when a screen's wording changes. Access rules mirror the sidebar (the server enforces them again).
 */
import {
  Activity, BedDouble, Bot, CalendarDays, ClipboardPen, CreditCard, FileStack, FlaskConical, HeartHandshake, HeartPulse,
  Hospital, Inbox, type LucideIcon, MessageSquare, Pill, Radar, Receipt, ScanLine, ShieldCheck, Siren, Sparkles, Stethoscope,
  UsersRound, Video, Wrench, BarChart3, ScrollText, KeyRound,
} from "lucide-react";
import type { Role } from "@/lib/types";

export type Access = { perm?: string; any?: string[] };
export type HelpLink = { label: string; to: string } & Access;

export type Module = {
  id: string;
  title: string;
  icon: LucideIcon;
  summary: string; // plain-language, safe for every staff member
  who: string;
  when: string;
  steps: string[];
  example: string;
  links: HelpLink[];
  access: Access; // who gets the step-by-step instructions
  simulated?: string; // what part of this area is simulated, if any
};

export const MODULES: Module[] = [
  {
    id: "patients", title: "Patient registration & search", icon: UsersRound,
    summary: "Every patient has one record. Registration checks for possible duplicates before a new record is created, so the same person isn't registered twice.",
    who: "Receptionists, nurses, doctors, insurance staff", when: "When a new patient arrives or calls, or whenever you need to find a patient.",
    steps: [
      "To find someone, press ⌘K (Ctrl+K on Windows) or click “Search patients…” at the top and type a name, date of birth or MRN.",
      "To register, open Patients and choose “Register patient”. Required fields are marked with *.",
      "If the system finds a possible match, review it. Open the existing chart if it is the same person, or confirm that this is a new patient.",
      "To correct details later, open the chart and choose Edit.",
    ],
    example: "A caller says she has never been here before. You search her name, find no match, register her and add her insurance details in the same form.",
    links: [{ label: "Patients", to: "/patients", perm: "patients:read" }, { label: "Register patient", to: "/patients/new", perm: "patients:write" }],
    access: { perm: "patients:read" },
  },
  {
    id: "appointments", title: "Appointments & front desk", icon: CalendarDays,
    summary: "The schedule shows every clinician's day. The front desk moves each visit along: confirmed, checked in, roomed, and checked out.",
    who: "Receptionists, nurses, doctors", when: "Booking visits, running the waiting room, and finishing visits.",
    steps: [
      "Open Schedule and choose “New appointment”, or use “Book” from Front desk. Pick the patient, clinician, type and time.",
      "When the patient arrives, open the appointment on Front desk and choose “Check in”.",
      "When a room is ready, choose “Room”. The clinician can then start the visit from the chart.",
      "After the visit, choose “Check out”. Use “Reschedule”, “Cancel” or “No-show” when plans change.",
    ],
    example: "Mr. Lee arrives 10 minutes early. You check him in, the nurse rooms him, and after the doctor finishes you check him out and book his follow-up.",
    links: [{ label: "Front desk", to: "/front-desk", perm: "schedule:write" }, { label: "Schedule", to: "/schedule", perm: "schedule:read" }],
    access: { perm: "schedule:read" },
  },
  {
    id: "ehr", title: "Medical record (EHR)", icon: Stethoscope,
    summary: "The chart holds visits, vitals, problems, allergies, medications, orders, results, documents and notes. Signed notes are locked; corrections are added as addenda.",
    who: "Doctors and nurses (read access for some other clinical roles)", when: "During and after every clinical visit.",
    steps: [
      "Open the patient's chart. The banner at the top always shows allergies.",
      "Choose “Start visit” to open a visit, then record vitals and write the note (Subjective, Objective, Assessment, Plan).",
      "Update the Problems, Medications and Allergies tabs as needed.",
      "Choose “Save” as you go. When the note is complete, choose “Sign note”. To correct a signed note, use “Add addendum”.",
      "Use the Journey tab for a single timeline of everything that happened to the patient across departments.",
    ],
    example: "Dr. Chen reviews allergies on the banner, documents the visit, adds hypertension to the problem list and signs the note.",
    links: [{ label: "My visits", to: "/encounters", perm: "clinical:read" }, { label: "Orders", to: "/orders", perm: "clinical:read" }],
    access: { perm: "clinical:read" },
  },
  {
    id: "orders", title: "Orders & results", icon: ClipboardPen,
    summary: "Clinicians order labs, imaging and medications. Results come back to the ordering clinician; patients see lab results only after they are verified and released.",
    who: "Doctors (sign orders); nurses (draft orders)", when: "Whenever a test or medication is needed.",
    steps: [
      "From the chart's Orders tab, or from Orders, choose “New order”.",
      "Choose the test or medication and add the details.",
      "A physician reviews it and chooses “Sign”. Signed orders go to the laboratory, radiology or pharmacy.",
      "Results appear on the chart's Results tab. Critical results also raise an alert that someone must acknowledge.",
    ],
    example: "A nurse drafts a CBC order, the doctor signs it, the lab collects and verifies it, and the result appears on the Results tab.",
    links: [{ label: "Orders", to: "/orders", perm: "clinical:read" }],
    access: { perm: "clinical:read" },
  },
  {
    id: "insurance", title: "Insurance Guardian", icon: ShieldCheck,
    summary: "Insurance Guardian checks coverage with the payer before visits. It never treats a stored end date as proof; only a payer check counts. When something looks wrong, it opens a case and asks the patient to confirm their insurance in the portal.",
    who: "Receptionists, insurance and billing staff", when: "Every day, before upcoming visits.",
    steps: [
      "Open Insurance Guardian to see visits ready, visits at risk, and open insurance cases.",
      "Open a case to see the evidence (what the check found) and the steps already taken.",
      "Use “Check with payer” to re-verify. When a patient sends a new card, review it under Card review: compare the details and choose “Confirm & re-verify”.",
      "When coverage is confirmed by the payer, the case closes automatically.",
    ],
    example: "A patient's plan reports inactive. Guardian opens a case and asks the patient to confirm. The patient uploads a new card, you confirm it, and the visit is ready.",
    links: [{ label: "Insurance Guardian", to: "/insurance", any: ["insurance:write", "automation:manage"] }],
    access: { any: ["insurance:write", "automation:manage"] },
    simulated: "Payer checks use a simulated payer connection in this build.",
  },
  {
    id: "scribe", title: "AI Medical Scribe", icon: Sparkles,
    summary: "With the patient's consent, the scribe listens to the visit and drafts a note for the clinician. Nothing is added to the record until the clinician inserts it, edits it and signs it.",
    who: "Doctors", when: "During a visit, if the patient agrees.",
    steps: [
      "In an open visit, open the Scribe panel and record how consent was given.",
      "Choose “Start recording”. You can pause and resume. Choose “Stop” when you are done.",
      "Review the draft. Choose “Insert into note” for the parts you want, edit them, then sign the note as usual.",
      "Choose “Discard” to delete a session you don't need.",
    ],
    example: "The patient agrees to recording. After the visit, the doctor inserts the draft plan, corrects a dose and signs.",
    links: [{ label: "My visits", to: "/encounters", perm: "clinical:write" }],
    access: { perm: "clinical:write" },
    simulated: "Without a configured AI provider, the scribe uses a labeled synthetic demo conversation.",
  },
  {
    id: "documents", title: "Document Intelligence", icon: FileStack,
    summary: "Uploaded faxes, letters and reports are read by the system. It suggests a document type, the patient it belongs to, and a short summary. A person reviews every document before it is filed.",
    who: "Front desk, nurses, doctors, insurance staff", when: "When outside records arrive.",
    steps: [
      "Open Documents and choose “Choose files” to upload.",
      "Open the document and choose “Review”. Check the suggested patient and document type against the document itself.",
      "Choose “File to chart” when everything is correct.",
    ],
    example: "A referral letter arrives. The system suggests the patient and type, you check the date of birth on the letter, and you file it to the chart.",
    links: [{ label: "Documents", to: "/documents", perm: "documents:read" }],
    access: { perm: "documents:read" },
    simulated: "Without a configured AI provider, reading uses simple rules and is labeled as simulated.",
  },
  {
    id: "messages", title: "Secure messages", icon: MessageSquare,
    summary: "Staff and patients exchange secure messages. Patient messages arrive in a shared inbox for the care team.",
    who: "All staff with messaging", when: "Answering patient questions, or coordinating with colleagues.",
    steps: ["Open Messages and choose a conversation, or choose “New message”.", "Type your reply and choose “Send”.", "Choose “Mark resolved” when the question is answered."],
    example: "A patient asks when to stop a medication. You forward the question to the doctor, then reply and mark it resolved.",
    links: [{ label: "Messages", to: "/messages", perm: "messages:use" }],
    access: { perm: "messages:use" },
    simulated: "Email and text notifications go to a message outbox; they are not sent to real phones or inboxes.",
  },
  {
    id: "ed", title: "Emergency department", icon: Siren,
    summary: "The tracking board shows everyone in the ED with timers, acuity (ESI) and bay. It covers arrival, triage, rooming, provider assignment and disposition (admit or discharge).",
    who: "ED nurses and physicians", when: "From arrival until the patient leaves the ED.",
    steps: [
      "Choose “New arrival”. If the patient can't be identified, register them as unidentified and correct the identity later.",
      "The triage nurse records the ESI level and vitals, then chooses “Save triage”.",
      "Choose “Room” to place the patient in a bay. A physician chooses “Assign me”.",
      "The physician chooses “Disposition”. Admitting sends the patient to the bed board.",
      "To correct an unidentified patient, use “Identify” (or “Merge records”). History is kept.",
    ],
    example: "A walk-in with chest pain is triaged ESI 2, roomed in Bay 4, seen by Dr. Santos and admitted. The bed manager then assigns a ward bed.",
    links: [{ label: "Emergency", to: "/ed", perm: "adt:read" }],
    access: { perm: "adt:read" },
  },
  {
    id: "inpatient", title: "Admissions, beds & discharge", icon: BedDouble,
    summary: "The bed board shows every inpatient bed and who is waiting. Admissions, transfers and discharges all happen here. A discharge checklist makes sure nothing is missed before a patient goes home.",
    who: "Bed managers, nurses, doctors", when: "Admitting, moving or discharging inpatients.",
    steps: [
      "On Bed board, choose “Assign bed” next to a waiting patient, pick a free bed, then choose “Assign & admit”.",
      "To move a patient, click their bed, choose the new bed and choose “Transfer”. ED bays can't be used as inpatient beds.",
      "When the doctor chooses “Order discharge”, a checklist is created and each department receives its own task.",
      "Each department completes its items. Some items close by themselves when the record shows they're done (for example, a booked follow-up).",
      "When the checklist is complete, choose “Complete discharge”. The bed goes to cleaning; choose “Mark clean” when it's ready.",
    ],
    example: "Dr. Santos orders discharge. The pharmacist reconciles medications, the nurse teaches the patient, the front desk books a follow-up, and the nurse completes the discharge.",
    links: [{ label: "Bed board", to: "/beds", perm: "adt:read" }, { label: "Inpatients", to: "/inpatients", perm: "adt:read" }],
    access: { perm: "adt:read" },
  },
  {
    id: "nursing", title: "Nursing", icon: HeartHandshake,
    summary: "Nurses see their patients, overdue vitals and open tasks in one place, and hand over at shift change.",
    who: "Nurses", when: "Throughout every shift.",
    steps: [
      "Open Nursing to see “My units” or “My assigned patients”. Overdue vitals are flagged.",
      "Open a patient to “Record vitals” and complete nursing tasks.",
      "At the end of your shift, choose “Write handoff”, then “Save handoff”.",
      "On the discharge checklist, mark the nursing items (education, transport) as done.",
    ],
    example: "At 14:00 you see two patients with overdue vitals, record them, and write handoff notes for the evening nurse.",
    links: [{ label: "Nursing", to: "/nursing", perm: "nursing:write" }],
    access: { perm: "nursing:write" },
  },
  {
    id: "pharmacy", title: "Pharmacy & inventory", icon: Pill,
    summary: "Pharmacy tracks every lot with its expiry date, every stock movement and every purchase. Pharmacy Watchdog raises cases for expiring stock, low stock and unusual use. Expired lots can't be dispensed.",
    who: "Pharmacists (nurses can view stock)", when: "Daily stock checks, medication verification, purchasing.",
    steps: [
      "Under Verification, review new medication orders and choose “Verify” or “Clarify”.",
      "Under Inventory, check levels and expiry dates. Use “Receive” for deliveries and “Dispense” for issues.",
      "Removing or wasting stock needs a second pharmacist to approve it.",
      "Low stock creates a purchase request under Purchasing. A hospital administrator approves it before “Send order”.",
      "Watchdog alerts appear in My work; resolve them by fixing the stock.",
    ],
    example: "Watchdog flags an expired heparin lot. You request waste, a second pharmacist approves it, and the case closes once the stock is gone.",
    links: [{ label: "Pharmacy & inventory", to: "/pharmacy", perm: "inventory:read" }],
    access: { perm: "inventory:read" },
    simulated: "Purchase orders to suppliers are simulated.",
  },
  {
    id: "lab", title: "Laboratory", icon: FlaskConical,
    summary: "Lab orders move through collection, receipt in the lab, result entry and verification by a second person. Critical results alert the ordering clinician.",
    who: "Laboratory staff (doctors review results)", when: "From specimen collection to verified result.",
    steps: [
      "Choose “Collect & label” when drawing the specimen. The lab chooses “Receive”, or “Reject” with a reason.",
      "Enter the values and choose “Save preliminary”.",
      "A different person checks them and chooses “Verify”. Only verified results are released.",
      "Critical values must be acknowledged. To fix a released result, use “Correct”; the original is kept.",
    ],
    example: "A potassium of 6.4 is verified, the system alerts the doctor, and the doctor acknowledges it.",
    links: [{ label: "Laboratory", to: "/lab", any: ["lab:work", "lab:verify", "orders:sign"] }],
    access: { any: ["lab:work", "lab:verify", "orders:sign"] },
  },
  {
    id: "radiology", title: "Radiology", icon: ScanLine,
    summary: "Imaging orders are scheduled, performed and reported. Radiologists sign the final report, which is then locked.",
    who: "Radiology technologists and radiologists", when: "From scheduling an exam to the signed report.",
    steps: [
      "Choose “Schedule”, then “Arrived” when the patient comes in.",
      "Choose “Start exam”, then “Complete”.",
      "The radiologist writes the report, chooses “Save draft”, and chooses “Sign” when it is final. Critical findings raise an alert.",
    ],
    example: "A CT head is scheduled, performed and read. The radiologist signs “No acute abnormality”, and the result appears on the chart.",
    links: [{ label: "Radiology", to: "/radiology", perm: "radiology:work" }],
    access: { perm: "radiology:work" },
    simulated: "The image archive (PACS) connection is simulated.",
  },
  {
    id: "billing", title: "Billing, claims & prior authorization", icon: Receipt,
    summary: "Charges become claims, which go to the payer and then to the patient for any balance. Revenue integrity checks claims and prior authorizations before they are sent. It suggests; people decide.",
    who: "Billing and insurance specialists", when: "After visits and discharges, and when payers respond.",
    steps: [
      "In Billing, review the visit's charges, then choose “Save & create claim” (or “Save & bill patient” for self-pay).",
      "In Revenue integrity, under “Claim review”, choose “Run review”. Fix any blocking findings before “Submit to payer”.",
      "Track required authorizations under “Prior authorizations”.",
      "Under “Denials”, review the reason and choose “Appeal” when appropriate.",
      "Patients can see their balance and pay in the portal.",
    ],
    example: "A claim is held because a prior authorization is missing. You obtain it, re-run the review and submit.",
    links: [{ label: "Billing", to: "/billing", perm: "billing:read" }, { label: "Revenue integrity", to: "/revenue", any: ["billing:read", "insurance:write"] }],
    access: { perm: "billing:read" },
    simulated: "Payer responses, appeals and patient card payments are simulated. No money moves.",
  },
  {
    id: "operations", title: "Command Center & My work", icon: Radar,
    summary: "The Command Center shows live hospital numbers: inpatients, free beds, ED, discharges, alerts and staffing. Each number says where it comes from. My work lists the cases, tasks and approvals that are waiting on you.",
    who: "Hospital administrators, bed managers, all staff (My work)", when: "Start of shift, and throughout the day.",
    steps: [
      "Open My work. Choose “Take it” on a case, follow its steps, and choose “Resolve”. Use “Reassign” or “Snooze” when needed.",
      "Under the Approvals tab, review each request and choose “Approve” or “Reject”. You can't approve your own request.",
      "In the Command Center, click any tile to see the patients or cases behind it.",
      "Choose “Shift handoff” for a summary of open issues; every line references a case.",
    ],
    example: "The ED tile turns amber for boarding patients. You open it, see two patients waiting for beds, and ask the bed manager to prioritize them.",
    links: [{ label: "My work", to: "/worklist", perm: "cases:read" }, { label: "Command Center", to: "/command", any: ["command:view", "automation:manage"] }],
    access: { perm: "cases:read" },
  },
  {
    id: "equipment", title: "Equipment, supplies & purchasing", icon: Wrench,
    summary: "The system keeps a register of equipment with maintenance history, and stock levels for each location. Equipment that is due for service and supplies below their minimum level raise cases.",
    who: "Hospital administrators, pharmacists", when: "Maintenance planning and restocking.",
    steps: [
      "Open Equipment to see items and when service is due. Choose “Log service” after maintenance.",
      "Purchase requests are listed under Pharmacy & inventory → Purchasing. Approve them there if you have purchasing approval.",
    ],
    example: "An infusion pump is due for service. Biomed services it and you log the service; the case closes.",
    links: [{ label: "Equipment", to: "/equipment", perm: "inventory:write" }],
    access: { perm: "inventory:write" },
  },
  {
    id: "insights", title: "Analytics & insights", icon: BarChart3,
    summary: "Dashboards and reports show visit volumes, no-shows and revenue. Insights adds a daily briefing, where every number lists its source, and simple forecasts for planning.",
    who: "Administrators, billing", when: "Planning and reviewing performance.",
    steps: [
      "Open Analytics for dashboards and exports.",
      "Open Insights for the daily briefing. References like [M3] point to the numbered metrics.",
      "Forecasts are basic baselines marked “not validated” (shadow mode). Use them for discussion only, not for staffing decisions.",
    ],
    example: "Before the bed meeting, you read the briefing and check the top discharge blockers.",
    links: [{ label: "Analytics", to: "/analytics", perm: "analytics:read" }, { label: "Insights", to: "/insights", perm: "analytics:read" }],
    access: { perm: "analytics:read" },
  },
  {
    id: "agents", title: "AI Agent Studio & governance", icon: Bot,
    summary: "Agents are AI helpers with a narrow job, such as Insurance Guardian, Pharmacy Watchdog, Discharge Coordination or Hospital Operations. They can only use the tools they are allowed, under your permissions. Anything that would change data becomes a request a person must approve.",
    who: "Staff with AI access; administrators manage settings", when: "When you want a summary or a suggested next step.",
    steps: [
      "Open Agent Studio, choose an agent and run it with your question. You'll see every tool it used.",
      "Any proposal it makes appears under My work → Approvals for a person to approve.",
      "Administrators can change an agent's instructions, tools and limits. Every change is saved as a new version.",
      "AI governance shows usage, cost, failures, feedback and evaluation results.",
    ],
    example: "You ask Hospital Operations for a shift summary. It reads the live numbers and lists the open cases with their references.",
    links: [{ label: "Agent Studio", to: "/agents", perm: "ai:use" }, { label: "AI governance", to: "/admin/ai-governance", perm: "ai:manage" }],
    access: { perm: "ai:use" },
  },
  {
    id: "admin", title: "Administration", icon: KeyRound,
    summary: "Administrators manage facilities, staff and roles, scheduling setup, automation monitors, AI settings and the audit log.",
    who: "Super Admins and facility administrators", when: "Setting up and overseeing the system.",
    steps: [
      "Under Staff & roles, choose “Invite staff” to add someone, and choose their role. Roles decide what each person can see and do.",
      "Facilities and Clinic settings set up locations, departments and hours.",
      "Monitors & rules turns automated checks on or off and adjusts their thresholds.",
      "AI settings (Super Admin only): enter the OpenAI key (it is stored encrypted and never shown again), pick models, and choose “Test connection”.",
      "The Audit log shows who did what and when.",
    ],
    example: "A new pharmacist joins. You invite them with the Pharmacist role; they can see pharmacy screens only.",
    links: [
      { label: "Staff & roles", to: "/admin/staff", perm: "users:manage" }, { label: "Monitors & rules", to: "/automation/monitors", any: ["automation:manage", "command:view"] },
      { label: "AI settings", to: "/admin/ai-settings", perm: "org:manage" }, { label: "Audit log", to: "/admin/audit", perm: "audit:read" },
    ],
    access: { any: ["users:manage", "clinic:manage", "org:manage", "audit:read"] },
  },
];

export type RoleGuide = { id: string; title: string; roles: Role[]; intro: string; tasks: { title: string; steps: string[]; module?: string; link?: HelpLink }[] };

export const ROLE_GUIDES: RoleGuide[] = [
  {
    id: "doctor", title: "Doctor", roles: ["doctor"], intro: "Your day starts in My visits and the schedule; everything about a patient is in their chart.",
    tasks: [
      { title: "Find today's patients", steps: ["Open My visits or Schedule and filter to “Just me”.", "Click a patient to open their chart."], module: "appointments", link: { label: "Schedule", to: "/schedule", perm: "schedule:read" } },
      { title: "Review history and allergies", steps: ["Allergies show on the chart banner at all times.", "Check the Problems, Medications, Results and Journey tabs."], module: "ehr" },
      { title: "Document a visit (with or without AI Scribe)", steps: ["Choose “Start visit” on the chart.", "Write the note, or use the Scribe panel with the patient's consent and choose “Insert into note”.", "Edit as needed and choose “Sign note”."], module: "scribe" },
      { title: "Order tests and review results", steps: ["Choose “New order”, complete it and choose “Sign”.", "Acknowledge critical results when alerted."], module: "orders", link: { label: "Orders", to: "/orders", perm: "clinical:read" } },
      { title: "Admit and discharge", steps: ["In the ED, choose “Disposition” → admit.", "For inpatients, choose “Order discharge”, sign the discharge summary, and approve the patient instructions."], module: "inpatient", link: { label: "Inpatients", to: "/inpatients", perm: "adt:read" } },
      { title: "Manage follow-ups", steps: ["Put the follow-up in the plan. The front desk books it, and the system flags a case if it isn't booked."], module: "appointments" },
    ],
  },
  {
    id: "nurse", title: "Nurse", roles: ["nurse"], intro: "Nursing shows your patients; My work shows tasks assigned to nurses.",
    tasks: [
      { title: "Open your patient list", steps: ["Open Nursing and choose “My units” or “My assigned patients”."], module: "nursing" },
      { title: "Record observations", steps: ["Open the patient and choose “Record vitals”. Overdue vitals are flagged in red."], module: "nursing" },
      { title: "Triage in the ED", steps: ["Open Emergency, select the patient, set the ESI level and vitals, and choose “Save triage”."], module: "ed", link: { label: "Emergency", to: "/ed", perm: "adt:read" } },
      { title: "Complete nursing tasks", steps: ["Open My work, choose “Take it”, do the task and mark it done."], module: "operations" },
      { title: "Help with discharge", steps: ["Open the stay's Discharge tab and complete the education and transport items.", "When everything is complete, choose “Complete discharge”."], module: "inpatient" },
      { title: "Hand over", steps: ["Choose “Write handoff” and then “Save handoff” before you leave."], module: "nursing" },
    ],
  },
  {
    id: "receptionist", title: "Receptionist", roles: ["receptionist"], intro: "Front desk is your home screen: today's arrivals and the waiting room.",
    tasks: [
      { title: "Register a patient", steps: ["Search first (⌘K). If there's no match, open Patients → “Register patient”.", "If a possible duplicate appears, check it before continuing."], module: "patients" },
      { title: "Schedule an appointment", steps: ["Choose “Book appointment” on Front desk, pick the clinician, time and reason."], module: "appointments" },
      { title: "Check a patient in", steps: ["Find the appointment on Front desk and choose “Check in”."], module: "appointments" },
      { title: "Update patient information", steps: ["Open the chart, choose Edit, correct the details and choose “Save changes”."], module: "patients" },
      { title: "Handle insurance alerts", steps: ["Open Insurance Guardian or My work, open the case, and follow its steps."], module: "insurance" },
    ],
  },
  {
    id: "billing", title: "Billing & insurance specialist", roles: ["billing", "insurance_specialist"], intro: "You work across Insurance Guardian, Billing and Revenue integrity.",
    tasks: [
      { title: "Review insurance cases", steps: ["Open Insurance Guardian → Cases, open a case and read the evidence, then “Check with payer”."], module: "insurance" },
      { title: "Check authorization requirements", steps: ["Open Revenue integrity → “Prior authorizations”. Orders that need one are flagged automatically."], module: "billing", link: { label: "Revenue integrity", to: "/revenue", any: ["billing:read", "insurance:write"] } },
      { title: "Prepare claims", steps: ["In Billing, review the charges and choose “Save & create claim”.", "Run a claim review and clear any blockers before “Submit to payer”."], module: "billing" },
      { title: "Investigate denials", steps: ["Open “Denials”, read the payer's reason, correct the issue or choose “Appeal”."], module: "billing" },
      { title: "Track balances", steps: ["Billing shows open balances; patients pay in the portal."], module: "billing" },
    ],
  },
  {
    id: "pharmacist", title: "Pharmacist", roles: ["pharmacist"], intro: "Pharmacy & inventory holds verification, stock and purchasing. Watchdog alerts land in My work.",
    tasks: [
      { title: "Verify medication orders", steps: ["Open Pharmacy & inventory → Verification and choose “Verify” or “Clarify”."], module: "pharmacy" },
      { title: "Review stock and expiry", steps: ["Open Inventory. Lots close to expiry and below their reorder level are highlighted."], module: "pharmacy" },
      { title: "Record stock movements", steps: ["Use “Receive” for deliveries and “Dispense” for issues. Waste needs a second pharmacist's approval."], module: "pharmacy" },
      { title: "Respond to Watchdog alerts", steps: ["Open My work, take the case, fix the stock issue; the case closes once the stock confirms it."], module: "operations", link: { label: "My work", to: "/worklist", perm: "cases:read" } },
      { title: "Discharge medication reconciliation", steps: ["Complete the medication reconciliation item on the discharge checklist."], module: "inpatient" },
    ],
  },
  {
    id: "lab", title: "Laboratory staff", roles: ["lab_tech"], intro: "Laboratory shows specimens to collect, receive, result and verify.",
    tasks: [
      { title: "Collect and receive", steps: ["Choose “Collect & label”, then “Receive” in the lab, or “Reject” with a reason."], module: "lab" },
      { title: "Enter and verify results", steps: ["Enter the values and choose “Save preliminary”. A different person chooses “Verify”."], module: "lab" },
      { title: "Critical results and corrections", steps: ["Make sure critical alerts are acknowledged. Use “Correct” to amend a released result; the original is kept."], module: "lab" },
    ],
  },
  {
    id: "radiology", title: "Radiology staff", roles: ["radiology_tech", "radiologist"], intro: "Radiology is a worklist from scheduling to the signed report.",
    tasks: [
      { title: "Run the exam", steps: ["Choose “Schedule”, “Arrived”, “Start exam”, then “Complete”."], module: "radiology" },
      { title: "Report (radiologists)", steps: ["Write the report, choose “Save draft”, then “Sign”. Signed reports are locked."], module: "radiology" },
    ],
  },
  {
    id: "bed_manager", title: "Bed manager", roles: ["bed_manager"], intro: "The bed board and the Command Center are your main screens.",
    tasks: [
      { title: "Place waiting patients", steps: ["On Bed board, choose “Assign bed”, pick a free inpatient bed, then “Assign & admit”."], module: "inpatient" },
      { title: "Transfers and bed status", steps: ["Click a bed to “Transfer” its patient. Use “Mark clean”, “Block” or “Return to service” to update bed status."], module: "inpatient" },
      { title: "Watch capacity", steps: ["Open the Command Center to see free beds, patients waiting for a bed, and ordered discharges."], module: "operations", link: { label: "Command Center", to: "/command", any: ["command:view", "automation:manage"] } },
    ],
  },
  {
    id: "hospital_admin", title: "Hospital administrator", roles: ["hospital_admin", "clinic_admin"], intro: "Use the Command Center to see the hospital at a glance and My work for anything that needs your approval.",
    tasks: [
      { title: "Use the Command Center", steps: ["Open the Command Center, filter by department, and click any tile to drill down."], module: "operations", link: { label: "Command Center", to: "/command", any: ["command:view", "automation:manage"] } },
      { title: "Review problems and assign work", steps: ["Open a case, choose “Reassign” to send it to the right team, or resolve it."], module: "operations" },
      { title: "Approve requests", steps: ["Open My work → Approvals, for example purchase requests. You can't approve your own request."], module: "operations" },
      { title: "Review analytics", steps: ["Open Analytics and Insights for trends and the daily briefing."], module: "insights" },
    ],
  },
  {
    id: "super_admin", title: "Super Admin", roles: ["super_admin"], intro: "You set up the organization, its people and its AI configuration.",
    tasks: [
      { title: "Organizations, facilities and staff", steps: ["Use Organizations, Facilities, and Staff & roles. Give each person only the role they need."], module: "admin" },
      { title: "Configure AI", steps: ["Open AI settings, enter the key, pick the text, vision, transcription and realtime voice models, then choose “Test connection”. Until it passes, AI features stay in labeled simulation."], module: "admin", link: { label: "AI settings", to: "/admin/ai-settings", perm: "org:manage" } },
      { title: "Manage agents", steps: ["In Agent Studio, adjust each agent's instructions, allowed tools and limits. Every change is versioned."], module: "agents", link: { label: "Agent Studio", to: "/agents", perm: "ai:use" } },
      { title: "Oversee AI and automation", steps: ["Check AI governance for usage, cost and evaluations, Monitors & rules for automated checks, and the Audit log for activity."], module: "agents", link: { label: "AI governance", to: "/admin/ai-governance", perm: "ai:manage" } },
    ],
  },
];

export type AITopic = { id: string; title: string; body: string[] };

export const AI_TOPICS: AITopic[] = [
  { id: "what", title: "What the AI assistants do", body: ["AI in Undeclared reads, summarizes and drafts. It can summarize a chart, draft a visit note from a conversation, read an uploaded document, explain an alert, and suggest a next step.", "It does not diagnose, prescribe, sign notes, change claims or codes, or message patients on its own."] },
  { id: "openai", title: "When OpenAI models are used", body: ["If a Super Admin has entered an OpenAI key and the connection test passes, AI features use the chosen OpenAI models. The key is stored encrypted on the server and never sent to your browser.", "Patient data is only sent to an external AI service when the organization's privacy settings allow it. Demo organizations use synthetic (made-up) patients."] },
  { id: "voice", title: "Text AI vs. Realtime Voice", body: ["Text AI handles written work: summaries, drafts and document reading.", "Realtime Voice is a live spoken conversation, used for practice calls on the AI receptionist page. It only starts when a realtime voice model is configured; otherwise the page says it is simulated and the button is disabled."] },
  { id: "guardian", title: "How Insurance Guardian works", body: ["Before visits it asks the payer whether coverage is active. A date stored in the record is never treated as proof.", "If coverage looks inactive or can't be checked, it opens a case for staff and can ask the patient to confirm their card in the portal. Staff confirm before anything changes."] },
  { id: "scribe", title: "How the AI Medical Scribe works", body: ["Recording starts only after consent is recorded. The scribe turns the conversation into a draft note.", "The clinician chooses what to insert, edits it and signs. The draft never signs itself."] },
  { id: "docs", title: "How Document AI works", body: ["It suggests the document type, the patient it belongs to, and a summary, along with a confidence level and anything it was unsure about. A person reviews and files every document."] },
  { id: "automation", title: "How pharmacy and discharge automations work", body: ["Automated checks (monitors) run in the background. Examples: expiring or low stock, critical results not acknowledged, discharges with missing items, follow-ups not booked.", "Each problem becomes one case, assigned to the right role with a deadline. The case closes only when the record shows the problem is fixed."] },
  { id: "approval", title: "Why some actions need approval", body: ["Anything that changes data, spends money or affects a patient goes through a person: AI proposals, stock waste, purchases and discharge instructions. Usually a second person must approve, never the one who asked."] },
  { id: "check", title: "Why you must check AI suggestions", body: ["AI can be wrong, can miss things, or can misread a document. Always compare against the source (the document, the chart, the patient) before you accept anything."] },
  { id: "live", title: "Is it live or simulated?", body: ["Look for the “Simulated” label on screens and results. Administrators can check AI workspace → “Check provider connection” and AI governance for the active provider. Payers, pharmacies, the image archive, email and text messages, and card payments are simulated in this build."] },
];

export type FAQ = { id: string; q: string; a: string; audience: "staff" | "patient"; link?: HelpLink };

export const FAQS: FAQ[] = [
  { id: "find", audience: "staff", q: "How do I find a patient?", a: "Press ⌘K (Ctrl+K) or click “Search patients…” at the top of any page, then type a name, date of birth or MRN.", link: { label: "Patients", to: "/patients", perm: "patients:read" } },
  { id: "book", audience: "staff", q: "How do I schedule an appointment?", a: "Go to Front desk and choose “Book appointment”, or go to Schedule and choose “New appointment”.", link: { label: "Schedule", to: "/schedule", perm: "schedule:read" } },
  { id: "correct", audience: "staff", q: "How do I correct patient information?", a: "Open the chart and choose Edit. Signed clinical notes can't be changed. Use “Add addendum” instead, so the original stays on record." },
  { id: "ins", audience: "staff", q: "How do I review an insurance alert?", a: "Open the case from My work or Insurance Guardian. Read the evidence, then use “Check with payer” or follow the listed steps. The case closes when the payer confirms coverage.", link: { label: "Insurance Guardian", to: "/insurance", any: ["insurance:write", "automation:manage"] } },
  { id: "scribe", audience: "staff", q: "How do I use the AI Medical Scribe?", a: "In an open visit, record the patient's consent in the Scribe panel, choose “Start recording”, then “Stop”. Insert the parts of the draft you want, edit them, and sign the note yourself." },
  { id: "ai-change", audience: "staff", q: "Can AI automatically change clinical records?", a: "No. AI drafts and suggests. Notes are signed by clinicians, and anything an agent proposes waits for a person to approve it." },
  { id: "task", audience: "staff", q: "How do I complete an assigned task?", a: "Open My work, choose “Take it”, do the work, and choose “Resolve”. Many cases close by themselves once the record shows the fix.", link: { label: "My work", to: "/worklist", perm: "cases:read" } },
  { id: "access", audience: "staff", q: "Why can't I access a particular department?", a: "Screens appear based on your role. If you need access for your job, ask your administrator to review your role. The system blocks access even if you have a direct link." },
  { id: "facility", audience: "staff", q: "How do I switch facilities?", a: "Use the organization and facility switcher at the top of the sidebar. You only see facilities you belong to." },
  { id: "approvals", audience: "staff", q: "How do I find pending approvals?", a: "Open My work and choose the Approvals tab. You can't approve your own requests.", link: { label: "My work", to: "/worklist", perm: "cases:read" } },
  { id: "sim", audience: "staff", q: "How do I know whether an external connection is simulated?", a: "Simulated features carry a “Simulated” label. In this build, payers, pharmacy suppliers, the image archive, email and text messages, card payments and AI without a configured key are simulated." },
  { id: "wrong", audience: "staff", q: "What should I do if I see incorrect patient information?", a: "Don't act on it. Check it with the patient or the source document, correct demographic details through Edit, and tell the responsible clinician about clinical errors so they can add an addendum. If two records are the same person, tell your administrator." },
  { id: "p-book", audience: "patient", q: "How do I book an appointment?", a: "Choose “Book an appointment” on the Home page, pick the type of visit, then a time that suits you.", link: { label: "Book", to: "/portal/book" } },
  { id: "p-form", audience: "patient", q: "How do I fill in a pre-visit form?", a: "Go to Appointments and choose “Complete pre-visit form” next to your upcoming visit.", link: { label: "Appointments", to: "/portal/appointments" } },
  { id: "p-video", audience: "patient", q: "How do I join a video visit?", a: "Go to Appointments. The “Join video visit” button appears 30 minutes before the start time.", link: { label: "Appointments", to: "/portal/appointments" } },
  { id: "p-results", audience: "patient", q: "Why can't I see a test result yet?", a: "Results appear after your clinician has reviewed them. If you have questions, send your care team a message.", link: { label: "Test results", to: "/portal/results" } },
  { id: "p-ins", audience: "patient", q: "How do I update my insurance?", a: "Open Insurance, enter your new details and add a photo or file of your card. Our team reviews it and confirms it with your insurer.", link: { label: "Insurance", to: "/portal/insurance" } },
  { id: "p-wrong", audience: "patient", q: "Something in my record looks wrong. What do I do?", a: "Send a message to your care team explaining what looks incorrect. They will review it and correct it if needed.", link: { label: "Messages", to: "/portal/messages" } },
  { id: "p-pay", audience: "patient", q: "How do I pay a bill?", a: "Open Billing and choose “Pay now” next to an open statement. In this demo, payments are simulated and no card is charged.", link: { label: "Billing", to: "/portal/billing" } },
  { id: "p-emergency", audience: "patient", q: "Can I use messages for an emergency?", a: "No. Messages are not monitored around the clock. In an emergency, call your local emergency number." },
];

export type JourneyStage = { id: string; title: string; icon: LucideIcon; text: string; who: string; module?: string };

export const JOURNEY: JourneyStage[] = [
  { id: "arrive", title: "Patient arrives", icon: Hospital, text: "The patient arrives for a booked visit or walks into the emergency department.", who: "Front desk / ED", module: "ed" },
  { id: "register", title: "Registration", icon: UsersRound, text: "Staff find the existing record or register the patient. Duplicates are checked first.", who: "Receptionist", module: "patients" },
  { id: "insurance", title: "Insurance check", icon: ShieldCheck, text: "Insurance Guardian confirms coverage with the payer and flags any problem early.", who: "Insurance staff", module: "insurance" },
  { id: "visit", title: "Appointment or ED visit", icon: CalendarDays, text: "The patient is checked in and roomed, or triaged and placed in an ED bay.", who: "Front desk / Nurse", module: "appointments" },
  { id: "care", title: "Doctor & nurse", icon: Stethoscope, text: "The care team examines the patient, records vitals and notes, places orders, and admits if needed.", who: "Doctor / Nurse", module: "ehr" },
  { id: "services", title: "Lab, imaging & pharmacy", icon: FlaskConical, text: "Tests are collected and verified, images are read, and medications are checked and dispensed.", who: "Lab / Radiology / Pharmacy", module: "lab" },
  { id: "billing", title: "Billing", icon: Receipt, text: "Charges become claims. Problems are found before submission, and any patient balance appears in the portal.", who: "Billing", module: "billing" },
  { id: "discharge", title: "Discharge", icon: BedDouble, text: "A checklist gives each department its part. The patient leaves only when the checklist is complete.", who: "Doctor / Nurse / Pharmacist", module: "inpatient" },
  { id: "follow", title: "Follow-up", icon: HeartPulse, text: "The follow-up is booked and instructions are shared in the portal. If no follow-up is booked, a case is raised.", who: "Front desk / Patient", module: "appointments" },
];

export type PatientTopic = { id: string; title: string; icon: LucideIcon; steps: string[]; to: string; label: string };

export const PATIENT_TOPICS: PatientTopic[] = [
  { id: "book", title: "Book an appointment", icon: CalendarDays, to: "/portal/book", label: "Book", steps: ["Choose “Book an appointment” on Home.", "Pick the visit type and a time.", "You'll see it under Appointments."] },
  { id: "forms", title: "Complete forms before your visit", icon: ClipboardPen, to: "/portal/appointments", label: "Appointments", steps: ["Open Appointments.", "Choose “Complete pre-visit form” next to your visit.", "You can update it until the visit starts."] },
  { id: "visits", title: "See visit information and results", icon: FileStack, to: "/portal/visits", label: "Visit summaries", steps: ["Visit summaries shows plans and follow-up instructions.", "Test results shows results after your clinician reviews them.", "Health record lists your medications, allergies and conditions."] },
  { id: "messages", title: "Send a secure message", icon: MessageSquare, to: "/portal/messages", label: "Messages", steps: ["Open Messages and start a new message.", "Your care team replies here. Don't use messages for emergencies."] },
  { id: "insurance", title: "Update your insurance", icon: ShieldCheck, to: "/portal/insurance", label: "Insurance", steps: ["Open Insurance.", "Enter your details and add your card.", "Our team checks it with your insurer and confirms."] },
  { id: "video", title: "Join a video visit", icon: Video, to: "/portal/appointments", label: "Appointments", steps: ["Open Appointments.", "Choose “Join video visit” (available 30 minutes before the start).", "Allow camera and microphone when your browser asks."] },
  { id: "bills", title: "Review and pay statements", icon: CreditCard, to: "/portal/billing", label: "Billing", steps: ["Open Billing to see statements and what your insurance paid.", "Choose “Pay now” on an open statement. Payments are simulated in this demo."] },
  { id: "stays", title: "Hospital stays & documents", icon: Inbox, to: "/portal/stays", label: "Hospital stays", steps: ["Hospital stays shows discharge instructions once your clinician has approved them.", "Documents lets you upload outside records for your care team to review."] },
];

export const ABOUT_MODULES = [
  "Patient records & scheduling", "Electronic health record & orders", "Emergency, inpatient & nursing", "Pharmacy, inventory & equipment",
  "Laboratory & radiology", "Insurance, billing & revenue integrity", "Patient portal & telehealth", "Command Center, automation & AI agents",
];

export const SECTION_ICONS = { overview: Hospital, start: Activity, features: FileStack, roles: UsersRound, ai: Sparkles, faq: MessageSquare, about: ScrollText };
