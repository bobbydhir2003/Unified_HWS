# Undeclared HMS — UX Simplification Audit & Redesign Strategy

_Inspection-only report (November 2026). No application code was changed. Evidence comes from the frontend source and
from signing in to the running application (local dev stack, synthetic data) as each implemented role, capturing every
first screen, the sidebar for each role, and the main workflow screens. "Observed" means seen in the running app or the
code; "Proposed" means a recommendation. Click counts are estimates from the current screen structure, not timed
measurements._

---

## 1. Executive summary

The application has a broad, working feature set, and several screens are already strong (the discharge checklist, the
patient chart overview, the ED board, the AI workspace's "draft only" framing). The usability problem is not missing
features — it is that **the product is organised around modules, not around what each person needs to do next.**

Five observed problems drive most of the confusion:

1. **Everyone gets the same clinic dashboard.** All 12 staff roles land on "Up next / Waiting room / Appointment volume".
   A pharmacist, lab technologist or bed manager sees appointments and an empty chart — nothing about their actual work.
2. **Navigation is long and module-shaped.** Sidebars range from 12 links (radiology) to 42 (Super Admin), 36 for a
   hospital administrator, 22 for a doctor — including links most roles never need (a doctor sees *Front desk*, *Staff
   roster*, *Operating rooms*; everyone sees *AI workspace* and *Agent Studio*).
3. **"My work" doesn't show priorities.** The hospital administrator's list has 55 cases, almost all labelled *High ·
   Escalated L2 · Overdue 4 days* — when everything is red, nothing is. A nurse opens My work and sees "No open cases for
   you" while 26 tasks sit on the next tab.
4. **Overlapping names for similar things.** Cases vs Tasks vs Approvals vs a separate *Tasks* page; *Analytics* vs
   *Insights*; *AI governance* vs *AI monitoring*; *Monitors & rules* vs *Automation studio*; *Inpatients* vs *Nursing*
   vs *Bed board*; *Billing* vs *Revenue integrity*; *Facilities* vs *Clinic settings*.
5. **Status rarely says who is next.** Discharge shows "0/7 · 6 blocking" but not "waiting on pharmacy"; "Complete
   discharge" is disabled without a visible reason; case rows repeat "Detected automatically" and show raw minutes
   ("waiting 5452 min").

The recommended strategy: **role-based home screens built from three blocks (My priorities · Today · Quick actions),
a sidebar of ~6–9 role-relevant destinations, one unified "My work" with sensible defaults, a single status language
("status → owner → next step"), and AI offered inside the workspace where the question arises.** All of it can be done
in the frontend first, with small backend help for case routing and summaries, and without removing any clinical
safeguard.

---

## 2. Current UX problems (observed)

| # | Problem | Evidence |
|---|---|---|
| P1 | Generic dashboard for all staff | `frontend/src/features/dashboard/Dashboard.tsx` renders the same KPI cards (*Appointments today, In clinic now, Active patients*), *Up next*, *Waiting room*, *Appointment volume* for every staff role; only two buttons are permission-gated. Observed identical for pharmacist, lab, radiology, bed manager, nurse. |
| P2 | The appointment chart renders empty | *Appointment volume* shows axes but no bars for every role on the dev stack (7 appointments exist today). Looks broken to a first-time user. |
| P3 | Long, flat sidebars | Counted from the live sidebar: Super Admin 42, Hospital Admin 36, Clinic Admin 33, Doctor 22, Nurse 20, Front desk 19, Billing 17, Insurance 17, Pharmacist 16, Bed manager 15, Lab 13, Radiology 12. Source: `frontend/src/components/layout/nav.ts` (one list filtered only by permission). |
| P4 | Irrelevant links per role | Doctor: *Front desk, Staff roster, Operating rooms, AI receptionist, Analytics*. Pharmacist: *Schedule, Emergency, Bed board, Inpatients*. Lab: *Pharmacy & inventory*. These are permission-legal but not part of the role's day. |
| P5 | AI spread across 8 entries | Super Admin sees *AI workspace, Insights, Agent Studio, AI governance, Monitors & rules, Automation studio, AI receptionist, AI monitoring*. *AI monitoring* (`/admin/ai`) and *AI governance* overlap; *Automation studio* (older workflow builder) and *Monitors & rules* overlap. |
| P6 | Alarm fatigue in My work | Hospital admin: 55 cases, ~45 shown as *High* and *Escalated L2*, most *Overdue 4 days*; 16 separate staffing-gap cases (one per unit per shift). Each row repeats "Detected automatically". Page height ≈ 4,100 px. (`features/ops/WorklistPage.tsx`, `ops.tsx`) |
| P7 | Work lands on the wrong person | Escalation re-assigns overdue cases to the *Hospital Administrator* (owner shown on every row), so frontline roles see few cases (nurse: 0 cases) while the admin sees everything. (`backend/app/engine/cases.py` escalation behaviour) |
| P8 | Misleading default tab | My work opens on *Cases* even when Cases = 0 and Tasks = 26 (nurse). |
| P9 | Raw durations | "Waiting 5452 min without triage", "Bed 4B-408B waiting for cleaning 5443 min" — not human-readable. |
| P10 | Patient chart has 15 tabs | *Overview, Visits, Problems, Medications, Allergies, History, Vitals, Orders, Results, Timeline, Journey, Documents, Appointments, Demographics, Front-desk notes* — overflows the row at 1440 px (`features/patients/PatientChart.tsx`, `TABS`). *Timeline* and *Journey* look like the same thing. |
| P11 | Discharge "next step" implicit | Checklist is clear item by item, but no summary of *who* is blocking; disabled *Complete discharge* has only a tooltip explanation (`features/inpatient/InpatientPages.tsx`). |
| P12 | Command Center density | ≈50 buttons, ~22 tiles in two grids plus tables (≈1,860 px tall). Good data, weak hierarchy: green "0" tiles get the same weight as red ones (`features/command/CommandCenter.tsx`). |
| P13 | Duplicate places for the same work | *Tasks* page and *My work → Tasks*; *Orders* page and chart *Orders* tab; *Front desk* and *Schedule* both book. |
| P14 | Two "realtime" ideas, two "AI receptionist" ideas | Live-update stream vs Realtime Voice; text receptionist sandbox (rule-based) vs voice panel on the same page — users can't tell which is AI. |
| P15 | Badges everywhere | "9+" notification badge on most accounts; every case row carries 2–3 coloured pills. |

Things that are working well and should be kept: the sticky patient banner with allergies, ⌘K patient search, the
"draft only" labelling in the AI workspace, the discharge checklist's "verified from the record automatically" text,
breadcrumbs, and the consistent card/table components.

---

## 3. Role-by-role findings

Legend for "today": nav count = links visible in the sidebar for that role (observed).

| Role | First screen (observed) | Top daily tasks | Priorities visible on arrival? | Nav count | Needed daily | Main pain points | Proposed change |
|---|---|---|---|---|---|---|---|
| **Super Admin** | Clinic dashboard (appointments) | Configure facilities/staff, AI settings, review audit/system health | No | 42 | ~8 | Everything visible; AI spread over 8 pages | *Admin home*: system health, AI status, recent config changes, audit shortcuts; sidebar grouped under **Administration** & **AI & Automation** |
| **Hospital Admin** | Clinic dashboard | Watch capacity, unblock discharges, approve purchases, review staffing | No (has to open Command Center) | 36 | ~7 | 55 undifferentiated cases | Land on **Operations**: 5 headline tiles + "Top 5 bottlenecks" + approvals |
| **Clinic Admin** | Clinic dashboard | Clinic schedule, staff, settings | Partly | 33 | ~7 | Admin links mixed with clinical | Clinic home: today's schedule health + admin shortcuts |
| **Doctor** | Clinic dashboard with *Up next* (useful) | See today's patients, document & sign, review results/critical alerts, admit/discharge | Partly — no critical results, unsigned notes count only small | 22 | ~6 | Front-desk/roster/OR links; critical results not on home | **My patients today** + "Needs my signature / acknowledgement" list |
| **Nurse** | Clinic dashboard (appointments) | Assigned patients, vitals due, tasks, handoff, discharge items | No | 20 | ~6 | Home irrelevant; My work opens on empty Cases tab | Land on **My patients** (Nursing) with vitals-due and tasks |
| **Front desk** | Clinic dashboard with Register/Book buttons | Check in, register, book, insurance issues | Partly | 19 | ~6 | Revenue integrity, Bed board, Staff roster links | Land on **Front desk** (arrivals + insurance flags on the same row) |
| **Billing** | Clinic dashboard | Claims held, denials, coding queue, prior auth | No | 17 | ~5 | Billing vs Revenue integrity split | **Revenue** home: held claims, denials, authorisations due |
| **Insurance staff** | Clinic dashboard | Coverage cases, card reviews, re-checks | No | 17 | ~4 | Guardian not on home | Land on **Insurance Guardian** cases sorted by visit date |
| **Pharmacist** | Clinic dashboard (irrelevant) | Verify orders, expiring/low stock, waste approvals, purchase requests | No | 16 | ~4 | Nothing pharmacy on home | Land on **Pharmacy**: verification queue + Watchdog alerts |
| **Lab** | Clinic dashboard (irrelevant) | Collect, receive, result, verify, critical calls | No | 13 | ~3 | Pharmacy link; home irrelevant | Land on **Laboratory** worklist by stage |
| **Radiology** | Clinic dashboard (irrelevant) | Worklist, perform, report, sign | No | 12 | ~3 | Home irrelevant | Land on **Radiology** worklist |
| **Bed manager** | Clinic dashboard (irrelevant) | Place waiting patients, cleaning, transfers | No | 15 | ~4 | Has to find Bed board | Land on **Bed board** with "waiting for a bed" first |
| **Patient** | Portal home (good) | Book, messages, results, bills, insurance | Yes | 13 tabs | ~6 | Tab row scrolls horizontally; Help last | Keep; group tabs into 5 (Home, Visits, Messages, Health, Billing & insurance) |

Estimated clicks for common tasks today (from the current screen structure):

| Task | Path today | Approx. clicks |
|---|---|---|
| Front desk checks in a patient | Sidebar *Front desk* → row → *Check in* | 2–3 |
| Nurse records vitals | *Nursing* → patient → *Record vitals* → save | 4 + typing |
| Doctor documents & signs | Dashboard *Up next* / *Patients* → chart → *Start visit* → note → *Sign note* | 4–5 + typing |
| Pharmacist verifies an order | *Pharmacy & inventory* → *Verification* tab → *Verify* | 3 |
| Lab verifies a result | *Laboratory* → specimen → enter/verify | 3–4 |
| Admin finds a discharge bottleneck | *Command Center* → *Discharges ordered* tile → stay → *Discharge* tab | 4 |
| Super Admin configures AI | User menu or sidebar *AI settings* → fill → *Save* → *Test connection* | 3 + typing |

Most tasks are short once the user is in the right place; the cost is **finding the right place** and **knowing what is
urgent**, not the number of clicks inside a workflow.

---

## 4. Navigation redesign proposal

### Principles
- Show each role **6–9 destinations**, ordered by daily use; everything else one level down.
- Group by **intent**, not by module. Keep emergency/critical entry points one click away for clinical roles.
- One name per concept (see §9 glossary).

### Proposed structure (role-filtered)

```
Home                         ← role-specific (see §5)
My work                      ← cases + tasks + approvals in one list (badge = urgent only)
Patients                     ← search, chart (chart tabs regrouped, §6)
Departments ▸                ← only the user's departments, first one expanded
    Emergency · Inpatients & beds · Nursing · Pharmacy · Laboratory · Radiology · Operating rooms
Front desk & scheduling      ← front desk, schedule, insurance readiness (clinic/reception roles)
Revenue ▸                    ← billing, claims & authorisations, insurance guardian (billing/insurance roles)
Operations ▸                 ← Command Center, staffing/roster, equipment & purchasing (admins, bed managers)
Reports                      ← analytics + insights merged
AI & Automation ▸            ← AI assistants (workspace), Agent Studio, Automation rules, AI governance (merged with AI monitoring)
Administration ▸             ← organisations, facilities & clinics, staff & roles, scheduling setup, AI settings, audit, outbox, system
Help
```

Merges: *AI monitoring* → *AI governance*; *Automation studio* + *Monitors & rules* → *Automation rules* (two tabs);
*Analytics* + *Insights* → *Reports*; *Tasks* page → *My work*; *Facilities* + *Clinic settings* → *Facilities & clinics*;
*Billing* + *Revenue integrity* → *Revenue* (tabs). *Staff roster* moves under Operations for managers; staff see
"My shifts" from the user menu.

Example sidebars after the change:

| Role | Proposed sidebar |
|---|---|
| Nurse | Home (My patients) · My work · Patients · Nursing · Emergency · Inpatients & beds · Help |
| Doctor | Home · My work · Patients · My visits · Emergency · Inpatients & beds · Orders & results · Help |
| Pharmacist | Home (Pharmacy) · My work · Pharmacy · Purchasing · Patients · Help |
| Hospital admin | Home (Operations) · My work · Operations ▸ · Departments ▸ · Revenue ▸ · Reports · AI & Automation ▸ · Administration ▸ · Help |
| Super Admin | Home (Admin) · My work · Administration ▸ · AI & Automation ▸ · Operations ▸ · Reports · Help (+ "All modules" search) |

Files: `frontend/src/components/layout/nav.ts` (add role→nav profiles and collapsible groups), `AppShell.tsx`
(group rendering, expanded state memory). Permissions are unchanged — the server still enforces every route.

---

## 5. Dashboard (Home) redesign proposal

Every Home has the same three blocks; the **content** differs by role.

```
┌─ Good morning, Grace · Medical-Surgical · Day shift ─────────────────────┐
│ MY PRIORITIES (max 5, most urgent first)                     View all → │
│ ● 401B Avery Board — vitals overdue 2 h                      [Record]   │
│ ● 4C-12 Nora Sorensen — discharge waiting on you: education  [Open]     │
│ ● Critical K+ 6.4 for J. Lee — acknowledge (Dr Santos notified)  [View] │
├─ TODAY ──────────────────────────────────┬─ QUICK ACTIONS ───────────────┤
│ My patients 6 · Vitals due 2 · Handoff at 19:00  │ Record vitals         │
│ Admissions to my unit 1 · Discharges 2           │ Find a patient        │
│                                                   │ Write handoff         │
└───────────────────────────────────────────────────┴───────────────────────┘
```

| Role | My priorities (sources) | Today | Quick actions |
|---|---|---|---|
| Doctor | Critical results to acknowledge; unsigned notes; orders awaiting signature; discharge items owned by doctor | My appointments / inpatients | Start visit · Find patient · New order |
| Nurse | Vitals overdue; tasks; discharge items (nurse); new admissions to unit | My patients, handoff time | Record vitals · Write handoff · Find patient |
| Front desk | Arrivals with insurance problems; unsigned intake forms; follow-ups not booked | Arrivals & waiting room | Check in · Register · Book |
| Pharmacist | Orders to verify; expiring/expired lots; waste approvals; low stock | Verification queue size, purchase requests | Verify next · Receive stock · Find item |
| Lab / Radiology | Critical results unacknowledged; specimens to receive/verify / unread studies | Worklist by stage | Collect · Verify · Report |
| Bed manager | Patients waiting for a bed (longest first); beds in cleaning > threshold | Free beds by unit | Assign bed · Mark clean |
| Billing / Insurance | Claims held; denials; authorisations due; coverage cases for visits in next 48 h | Claims by status | Run review · Check with payer |
| Hospital admin | Top 5 bottlenecks (grouped), approvals | 5 headline tiles (inpatients, free beds, ED waiting, discharges, staffing) | Open Command Center · Approvals · Shift handoff |
| Super Admin | System/automation health problems, AI test failures | Recent config changes | AI settings · Invite staff · Audit log |

Rules: maximum five priorities; each has a verb button; empty state says what "good" looks like ("No vitals overdue on
your unit"). Remove *Appointment volume* from non-clinic roles (and fix the empty chart, P2).

Files: `features/dashboard/Dashboard.tsx` (split into `homes/<Role>Home.tsx` + shared `PrioritiesList`, `TodayStrip`,
`QuickActions`); reuse existing endpoints (`/worklist`, `/nursing/patients`, `/pharmacy/verifications`, `/adt/board`,
`/command/summary`). A small `GET /home/priorities` endpoint would make ranking consistent (Phase 2).

---

## 6. Workflow recommendations

| Workflow | Observed today | Proposed |
|---|---|---|
| **Registration** | Search first is optional; duplicate warning appears after submit | Start with search ("Is the patient already here?"); show duplicate candidates *inline as they type*; insurance as step 2 of a short stepper |
| **Appointments** | Booking from *Schedule* or *Front desk*; check-in/room/check-out buttons on rows | One "Front desk" page with a status lane (Expected → Arrived → Roomed → With provider → Done); insurance flag on the row |
| **Doctor encounter** | Chart → *Start visit* → note → *Sign* (clear) | Keep; add "Ready to sign" checklist (note complete, orders signed) and scribe button in the note header |
| **Patient chart** | 15 tabs | 6 tabs: **Summary** · **Notes & visits** · **Orders & results** · **Medications & allergies** · **History** (problems, history, vitals, timeline/journey merged) · **Documents & admin** (documents, demographics, appointments, front-desk notes) |
| **Nursing** | Nursing list → patient → vitals | Home = my patients; inline "Record vitals" row action |
| **ED** | Board with buttons per row (good) | Add a "next step" column per patient (Triage → Room → Provider → Disposition) |
| **Discharge** | Checklist 0/7, "6 blocking", disabled Complete button | Header sentence: **"Waiting on: Pharmacy (med reconciliation), Doctor (summary)"**; group items by owner; show *why* Complete is disabled under the button |
| **Pharmacy** | 4 tabs (Verification, Inventory, Purchasing, Watchdog) | Default to Verification with count; Watchdog alerts as a banner on Inventory |
| **Lab** | Stage buttons per specimen | Lanes by stage with counts; critical first |
| **Insurance Guardian** | 4 tabs; cases in My work too | Sort by visit date; each case row shows "Next: check with payer / waiting on patient card" |
| **Agent Studio → approval** | Run agent → proposal → user must go to *My work → Approvals* | Show proposals inline in the run result with Approve/Reject (still requiring a second person where the rule says so) |

Clinical sign-offs, two-person rules, audit and permissions are unchanged in every proposal.

---

## 7. Information hierarchy

| Level | What | Treatment |
|---|---|---|
| Primary | Urgent items, the patient banner, the next action | Top of page, one accent colour, verb buttons |
| Secondary | Today's activity, lists | Neutral cards/tables, sensible default filters ("my unit", "next 48 h") |
| Tertiary | History, audit, configuration, technical detail | Collapsed sections, side panels, "View all" |

Apply to: Command Center (collapse green/zero tiles into a "All clear" row; P12), My work (group repeated cases — e.g.
"Staffing gaps: 16 shifts across 3 units" as one expandable row; humanise durations "3 d 18 h"; P6/P9), chart overview
(already good), AI governance (summary first, tables collapsed).

---

## 8. AI & automation that feels natural

Observed: AI is mostly reached through separate pages; the chart has *Ask AI*; the AI workspace explains features well.

Proposed:
- **Contextual "Ask" entry points** that call the existing agents/assistants with the context pre-filled:
  Doctor chart → "Summarise this chart" (chart assistant); Front desk → "Which of today's arrivals have insurance
  issues?" (Insurance Guardian agent); Command Center → "Explain today's bottlenecks" (Hospital Operations agent);
  Pharmacy → "Summarise items needing stock review" (Pharmacy Watchdog); Claim row → "Why is this claim held?" (Claims
  Review). Agent Studio stays as the advanced configuration area.
- **One visual language for automation vs AI** (badge + icon):

| Label | Meaning |
|---|---|
| **Rule alert** | Created by a monitor (deterministic) |
| **AI summary** | Generated text; may be wrong; shows sources |
| **AI proposal · needs approval** | Nothing has happened yet |
| **Approved / Done** | A person approved and the system executed it |
| **Simulated** | Rule-based fallback or simulated vendor |
| **Live AI** | Produced by the configured provider |

- Never word AI output as an action ("AI created a task") when it was a proposal.

---

## 9. Status clarity

Adopt one status set everywhere, each with one colour and one icon:
**Not started · In progress · Waiting on <team> · Needs approval · Blocked · Done · Failed · Urgent** (urgent is a flag,
not a status).

Pattern for multi-step work: **Status → Owner → Next action**, e.g. "Discharge — Waiting on Pharmacy — Medication
reconciliation". Apply to discharge, cases, insurance cases, claims, lab specimens, purchase requests.

Glossary fixes: *Case* (automatic problem) vs *Task* (assigned piece of work) vs *Approval* (decision) — explain once in
My work's header and Help; rename *Inpatients* → *Inpatients & beds* hub; *Revenue integrity* → *Claims review*;
*AI workspace* → *AI assistants*.

Errors: say what happened and what to do ("The payer didn't respond — try again or mark as checked by phone").

Badges: show counts only for urgent items; cap the bell at real notifications for *you*.

---

## 10. Visual design & accessibility

Observed strengths: consistent Inter typography, shadcn-style components, light/dark themes, focus rings, breadcrumbs,
reduced-motion support.

Recommendations:
- Fewer competing colours on lists: one severity dot + text; drop the second "Escalated" pill when overdue is shown.
- Tables: default to 25 rows, sticky headers, "group by" for repeated items.
- Sidebar: collapsible groups; remember expanded state; width unchanged.
- Fix the empty *Appointment volume* chart (P2) or remove it where irrelevant.
- Mobile: staff app is usable but long pages (My work ≈ 4,100 px) need grouping; portal tab row should wrap/group.
- Accessibility follow-ups: verify colour contrast of status pills in dark mode; ensure disabled buttons expose the
  reason as text (not only `title`); keyboard path through checklists.

---

## 11. Benchmark notes (conceptual, not copied)

General patterns common to mature clinical platforms (from public product material and common practice — not verified
against any specific product's current UI):
- **Role-based workspaces** that open on the user's worklist (e.g. "my patients", "my inbox").
- **Persistent patient context** — a banner with identifiers and allergies (Undeclared already does this well).
- **In-basket / worklist** as the centre of daily work, with clear ownership.
- **Track boards** for ED and beds with a "next step" column.
- **Sidebar of favourites** plus global search for everything else.

The proposal applies these ideas to Undeclared's existing components rather than imitating any product.

---

## 12. Before-and-after examples

**Sidebar (nurse)**
```
BEFORE (20 links)                          AFTER (7)
Dashboard · My work · Front desk ·         Home (My patients)
Schedule · Patients · Messages · Orders ·  My work            3
Documents · Tasks · Emergency · Bed board· Patients
Inpatients · Nursing · Pharmacy & inv. ·   Nursing
Staff roster · Laboratory · AI workspace · Emergency
Agent Studio · AI receptionist · Help      Inpatients & beds
                                           Help      (+ ⌘K for anything else)
```

**My work (hospital admin)**
```
BEFORE: 55 rows, ~45 "High · Escalated L2 · Overdue 4 days", 16 staffing rows, raw minutes
AFTER:
 URGENT (5)       ED: 3 patients waiting > 1 h for a provider          [Open ED board]
                  Discharges stalled: 9 (most waiting on Doctor summary) [Review]
 TODAY (12)       Staffing gaps: 16 shifts across 3 units ▸
                  Beds in cleaning > 2 h: 11 ▸
 LATER (38)       Equipment maintenance due ▸ …
```

**Discharge**
```
BEFORE: "Discharge 0/7 · 6 blocking"   [Complete discharge] (disabled, no reason)
AFTER:  Discharge for Avery Board — waiting on 3 teams
        Doctor     ○ Summary signed            [Write summary]
        Pharmacy   ○ Medication reconciliation  (assigned to Noah F.)
        Nursing    ○ Education   ○ Transport   [Done] [Done]
        Front desk ○ Follow-up booked           [Book]
        Complete discharge — available when the 6 required items are done
```

**Pharmacist Home**
```
BEFORE: Appointments today 0 · In clinic 0 · Up next: none · empty chart
AFTER:  My priorities: 4 orders to verify · 1 expired lot (ICU) · 1 waste approval
        Today: purchase requests 2 · low stock 3
        Quick: Verify next · Receive stock · Find item
```

---

## 13. Three-phase roadmap

Each item: problem → current → proposal → roles → files → impact / complexity → risks → testing.

### Phase 1 — Immediate clarity (low risk, frontend-led)

| Change | Problem | Current | Proposal | Roles | Files | Impact / complexity | Risks | Testing |
|---|---|---|---|---|---|---|---|---|
| 1.1 Role-based Home | P1 | One clinic dashboard | Home per role from existing APIs (3 blocks) | All staff | `features/dashboard/*`, `main.tsx` | High / Medium | Missing data for a role → show empty state, not errors | Browser flow per role (reuse `help_flow` pattern) |
| 1.2 Role nav profiles + groups | P3–P5 | Flat permission-filtered list | 6–9 links per role, collapsible groups, merges listed in §4 | All | `layout/nav.ts`, `AppShell.tsx` | High / Low–Med | Hiding something a role relies on → keep ⌘K and "All modules" | Nav snapshot test per role; route access unchanged |
| 1.3 My work defaults | P8, P9, P6 (visual) | Cases tab first; raw minutes; repeated pills | Open on tab with items; humanised durations; one severity marker; group repeated titles | All | `ops/WorklistPage.tsx`, `ops.tsx` | High / Low | None | Unit test duration formatter; worklist flow |
| 1.4 Discharge "waiting on" + disabled reason | P11 | Implicit | Header sentence + owner grouping + visible reason | Clinical | `inpatient/InpatientPages.tsx` | High / Low | Must reflect the same readiness data | `adt_flow` + discharge test |
| 1.5 Glossary & renames | P4, P13 | Overlapping names | Apply §9 names; explain Case/Task/Approval | All | `nav.ts`, page headers, Help content | Med / Low | Docs/Help must match | Help flow |
| 1.6 Fix/remove empty chart | P2 | Empty axes | Fix data or hide for non-clinic roles | All | `Dashboard.tsx` | Med / Low | — | Visual check |

### Phase 2 — Workflow simplification

| Change | Problem | Proposal | Files | Complexity | Risks |
|---|---|---|---|---|---|
| 2.1 Chart tabs 15 → 6 | P10 | Regroup tabs (§6) with sub-sections | `patients/PatientChart.tsx`, clinical tab components | Medium | Clinicians must still reach every section in ≤ 2 clicks |
| 2.2 Case routing to frontline roles | P7 | Escalate *notify* the admin but keep the owner role; admin sees escalations as a group | `backend/app/engine/cases.py`, monitors config | Medium (backend) | Must not drop escalation safety; audit unchanged |
| 2.3 Group repeated cases | P6 | Parent "bundle" view for same monitor + same shift/unit | `WorklistPage.tsx` (+ optional backend grouping key) | Medium | Don't hide individual SLAs |
| 2.4 Front desk status lanes | — | Expected → Arrived → Roomed → With provider → Done | `schedule/FrontDesk.tsx` | Medium | Concurrency with existing actions |
| 2.5 Command Center hierarchy | P12 | 5 headline tiles + bottleneck list; zero tiles collapsed | `command/CommandCenter.tsx` | Medium | Keep "source" links |
| 2.6 Unified status component | §9 | Shared `StatusChip` + "Status → Owner → Next" line | `components/common` + adoption | Medium | Consistency across modules |
| 2.7 Inline approvals for agent proposals | — | Approve/Reject in run result | `ai/AgentStudio.tsx` | Low | Same server checks (no self-approval) |

### Phase 3 — Intelligent UX

| Change | Proposal | Files | Complexity | Risks |
|---|---|---|---|---|
| 3.1 Contextual "Ask" buttons | Pre-filled agent questions in chart, front desk, Command Center, pharmacy, claims | Feature pages + `agents` API | Medium | AI wording must never imply actions; label simulated vs live |
| 3.2 Priority ranking service | `GET /home/priorities` merging cases, tasks, approvals, critical results, overdue vitals with one score | new router + Home | Medium–High | Explainable ordering; no hidden items |
| 3.3 Personalised workspace | Pin favourites, remember filters/unit | `AppShell`, local prefs | Low–Med | — |
| 3.4 Cross-department guidance | "What happens next" panel on patient (from journey + open cases) | chart + journey API | Medium | Must stay factual |

---

## 14. Top 10 improvements (ranked)

1. **Role-based Home screens** (`Dashboard.tsx`) — the first screen decides whether a new user understands the product;
   today 8 of 12 staff roles see irrelevant appointment data.
2. **Role-specific, grouped sidebar** (`nav.ts`, `AppShell.tsx`) — cut 16–42 links to 6–9 and merge duplicates.
3. **My work that ranks and groups** (`WorklistPage.tsx`) — 55 identical red rows hide the five that matter.
4. **Route cases to the people who do the work** (`engine/cases.py`) — escalation currently concentrates everything on
   the administrator; the nurse sees "No open cases".
5. **"Waiting on <team>" for discharge** (`InpatientPages.tsx`) — the most cross-departmental workflow needs one
   sentence saying who is next.
6. **Default My work to the tab with items + humanised times** — removes a misleading empty state and "5452 min".
7. **Patient chart tabs 15 → 6** (`PatientChart.tsx`) — fewer choices, no overflow, Timeline/Journey merged.
8. **One status language and chip** — same words and colours from ED to billing.
9. **Command Center hierarchy** — headline tiles + bottlenecks; zero/green tiles out of the way.
10. **Contextual AI with clear labels** — ask in place; distinguish rule alert, AI summary, proposal, done, simulated,
    live.

---

## 15. Scenario walk-throughs (proposed vs today)

| Scenario | Today | With the proposal |
|---|---|---|
| New receptionist checks in a patient | Lands on generic dashboard; must know to open *Front desk*; row → *Check in* | Lands on Front desk; arriving patient is first row with insurance flag; *Check in* (same 1 click on the row) |
| Nurse manages assigned patients | Generic dashboard → *Nursing*; My work shows empty Cases | Home = My patients with vitals due and discharge items; My work opens on Tasks |
| Doctor completes an encounter | *Up next* → chart → *Start visit* → *Sign* | Same steps; Home also lists unsigned notes and critical results to acknowledge |
| Pharmacist handles a review | Generic dashboard → sidebar → *Pharmacy* → *Verification* | Home shows "4 orders to verify" → *Verify next* |
| Admin responds to an operational problem | Dashboard → Command Center or 55-row My work | Home = Operations: top 5 bottlenecks, each opens the right board |
| Patient books a follow-up | Portal *Book an appointment* (already clear) | Unchanged; portal tabs grouped so Help and Billing are visible |
| Super Admin configures AI | Find *AI settings* among 42 links | Admin Home → *AI settings* quick action; AI pages consolidated under AI & Automation |

Click counts inside workflows mostly stay the same; the gain is in **arriving at the right place with priorities
visible**. No measured time savings are claimed — they should be validated (§16).

---

## 16. Risks & validation plan

Risks:
- **Hiding a needed link** — mitigated by keeping ⌘K search, an "All modules" entry, and unchanged route permissions.
- **Mis-ranking priorities** — keep ranking rules explicit and visible ("why is this first?").
- **Routing change in escalation** (2.2) — must keep escalation notifications and audit; test with the engine tests.
- **AI wording** — review all AI labels so nothing implies an action that wasn't approved.
- **Regression in clinical workflows** — every proposal keeps signing, two-person rules and approvals.

Validation:
1. Clickable prototype of Home + sidebar for 4 roles (nurse, doctor, pharmacist, admin).
2. Five-minute task tests with 3–5 people per role: "What needs your attention?", "Record vitals for…", "Why can't this
   patient go home yet?" — record success and time.
3. Ship Phase 1 behind a per-user "new layout" toggle; compare navigation clicks and task completion.
4. Automated checks: per-role nav snapshot, existing browser flows (`e2e/*_flow.py`), accessibility scan of new Home
   pages, backend tests for any routing change.

**Status (2026-11-23):** Phases 1–3 were approved and implemented — see `docs/IMPLEMENTATION_PROGRESS.md` → "UX simplification".
Still open from this plan: a Command Center hierarchy pass (2.5), front-desk status lanes (2.4), a dedicated priority-ranking
service beyond `/home` (3.2) and user testing (§16).
