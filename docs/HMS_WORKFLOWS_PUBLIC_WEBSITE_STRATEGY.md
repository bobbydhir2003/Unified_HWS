# HMS Workflows — Public Website Strategy

**Status:** proposal for approval. Nothing has been implemented.

**Inspected on 23 Nov 2026:**
- the live site `https://3-19-143-26.sslip.io` (release e5debab), at 1440×900 and 390×844;
- `frontend/src/features/public/*` and `features/auth/LoginForm.tsx`;
- `docs/COMPLETE_APP_UNDERSTANDING.md`, `docs/UX_SIMPLIFICATION_AUDIT.md` and `docs/HMS_WORKFLOWS_VISUAL_REDESIGN_PLAN.md`;
- the redesigned application, and the AI provider state, both live and local.

**How to read this document:**
- **Fact** — observed on the site, in code, or by an API call.
- **Recommendation** — a proposal. Nothing is decided until you approve it.

---

## 1. Executive summary

The public site is honest and well organised. That is a strong base: simulated integrations are labelled, and nothing is overclaimed. But the homepage still reads as a **sign-in page with marketing underneath**, not as the website of a hospital-software company.

Three things cause most of the problem:

1. **The hero's main object is a login card.** The brightest element above the fold is a white sign-in form with seven demo buttons. The product is described in a 35-word paragraph beside it. A first-time visitor's eye lands on "Sign in", not on what HMS Workflows does.
2. **There is almost no product evidence, and the one screenshot is out of date.**
   - The site has a single product image: the Command Center.
   - It still shows the old *Undeclared* brand, the dark sidebar and the pre-redesign layout.
   - Everything else is icons, gradient tiles and an abstract hub diagram.
   - The real, newly redesigned application is the best credibility asset you have, and the site does not show it.
3. **The core idea is never stated as a problem and a solution.** The site lists systems, journey steps, AI features and modules. It never says *what goes wrong in hospitals today* or *how a shared system changes that*. It also mixes rules-based automation into "Meet HMS Workflows AI", which blurs the distinction you most want visitors to understand.

**Recommended direction:**
- a product-first homepage (Hero concept A, §6);
- sign-in moved to the existing `/login` page;
- a clear "Explore the demo" path built on the existing one-click demo accounts;
- a single problem → solution narrative;
- real screenshots of the redesigned app;
- a plain-language AI & Automation section separating rules, AI and human approval;
- the light, restrained HMS Workflows visual system carried over from the app.

Navigation becomes **Platform · Solutions · AI & Automation · About · Explore the demo · Sign in**. The homepage drops from nine content blocks to seven focused sections.

---

## 2. Current homepage problems (with evidence)

### 2.1 Answers to your twelve questions

| # | Question | Answer | Evidence (fact) |
|---|---|---|---|
| 1 | Understand what it is in 5 seconds? | **Partly.** "Hospital" is clear; "management platform" appears only in a small pill and paragraph | H1 is the slogan; the product noun is in the 12 px pill "AI-powered hospital management" and inside a 35-word paragraph |
| 2 | Explains the problem? | **No** | No section, sentence or heading on Home describes a problem; first H2 is "Sign in to HMS Workflows" |
| 3 | Distinctive value? | **Weakly.** Differentiators exist but live on About | `DIFFERENTIATORS` (7 items) only rendered on `/about` |
| 4 | Hero too focused on sign-in? | **Yes** | the login card spans about a third of the fold's width (31%) and is its highest-contrast element; 11 actions above the fold (2 hero CTAs, nav Sign In, email, password, Sign in, Forgot password, 7 demo roles); on mobile the form starts at y = 552 px, before any product content |
| 5 | Generic, repetitive or technical? | **Some generic, some repetitive** | "one intelligent workspace", "connected platform", "connected" ×7 on Home; "Six connected systems. One platform." vs "Everything Your Hospital Needs, Connected." vs "All Connected." |
| 6 | Coherent platform? | **Inconsistent taxonomy** | Home shows "Six connected systems"; Modules shows six *different* groups (e.g. Home "Pharmacy & Laboratory" vs Modules "Pharmacy, Laboratory & Radiology"; Home puts analytics under Command Center, Modules under "Analytics & Administration"); 15 module cards |
| 7 | How departments connect? | **Asserted, not shown** | Hub diagram with dashed lines and one sentence; nothing shows a hand-off (e.g. discharge checklist waiting on pharmacy) |
| 8 | Automation and AI understandable? | **Blurred** | "Meet HMS Workflows AI" includes Pharmacy Watchdog ("Rule-based monitoring") and Insurance Guardian (workflow + simulated payer) as AI features |
| 9 | Enough of the real application? | **No; one stale screenshot** | `/images/command-center.webp` (committed 19 Nov, before the redesign) shows "Undeclared", dark sidebar, old tiles |
| 10 | Credible without exaggerating? | **Yes on honesty; weak on proof** | Status labels ("Payer connection simulated") are good; but credibility comes from evidence, and the site shows little |
| 11 | Navigation makes sense? | **Partly** | "Modules" is internal vocabulary; no AI page; no demo entry; Sign In appears 3 times (nav, hero, footer) |
| 12 | Enterprise SaaS or dev demo? | **Closer to a polished demo** | Login-first hero, glow rings (`eco-pulse`), blurred radial gradients, gradient H1 text, gradient icon tiles, fake browser "traffic lights", photo of a building with a glowing medical cross |

### 2.2 Specific weaknesses and corrections

| Weakness | Correction |
|---|---|
| Login card dominates the hero | Remove it from Home. Sign in lives at `/login` (already exists); a restrained "Sign in" button stays in the nav |
| No problem statement | Add a short "The problem" section directly after the hero (§8.2) |
| Stale, off-brand screenshot | Recapture all product images from the redesigned app with synthetic data (§11) |
| Abstract hub diagram | Replace with a "one patient, every department" walkthrough built from real screens (§8.4) |
| AI section mixes rules and AI | Re-structure as *Automation · AI assistance · Human approval* (§8.6) |
| Taxonomy differs between Home and Modules | One set of five capability areas used everywhere (§9) |
| Decorative effects | Remove glows, gradient text, gradient icon tiles and traffic-light frame; use whitespace, type and real screenshots (§14) |
| Hero photo with medical cross | Replace the photo with a product screenshot on a light background (also resolves the open item from the redesign) |
| Status scattered across badges | Keep inline labels short; add one "Product status" block on About and the demo page that explains *Implemented · Simulated · Requires credentials* |
| Mobile: login before content | With login removed, mobile reads headline → one-sentence definition → two CTAs → screenshot |

### 2.3 What is already good (keep)

- **Honest status language.** Simulated integrations are named and no outcomes are claimed. This is rare and valuable.
- **The tagline:** *Your Entire Hospital. Working as One.* It is memorable and fits the product.
- **Content accuracy.** `content.ts` content is accurate to the code and can be edited rather than rewritten.
- **Copyright.** The footer has it with a legal link.
- **Patient journey.** The *idea* is right; it needs real screens, not text cards.

---

## 3. What the product actually is (verified)

The capability statuses below come from `COMPLETE_APP_UNDERSTANDING.md` §3 and §11, plus today's checks.

| Area | Status (fact) |
|---|---|
| Registration, scheduling, front desk, EHR (visits, notes with signing, vitals, problems, medications, allergies), orders & results | **Implemented**; reminders by email/SMS go to an outbox (simulated sending) |
| Emergency department, admissions, nursing, bed board, transfers, discharge checklist | **Implemented** |
| Pharmacy verification, lots/expiry, two-person waste, purchasing | **Implemented**; supplier purchase orders simulated |
| Laboratory (collect → verify), radiology (worklist → signed report), critical-result acknowledgement | **Implemented**; PACS image archive simulated |
| Insurance Guardian, claims, prior authorizations, denials, statements | **Workflow implemented**; payer, clearinghouse and card payments **simulated** |
| Automation engine (monitors → cases with owners, deadlines, escalation; approvals) | **Implemented** |
| Command Center, analytics, daily briefing | **Implemented**; forecasts labelled "not validated" |
| Patient portal (booking, forms, messages, results, video visits, insurance, bills) | **Implemented**; payments simulated; video is peer-to-peer WebRTC (no relay server) |
| AI: chart assistant, scribe, document intelligence, agents, receptionist, realtime voice | **Implemented with a labelled simulation fallback** |

**AI facts today.**
- **Local.** A live OpenAI provider is configured (key set through the UI). The local database records **one successful live agent run (`gpt-4.1-mini`)** and one rule-based run.
- **Not yet verified live:** scribe transcription, document reading and realtime voice have not been verified end to end.
- **AWS:** demo sessions report `simulated` (they never use a platform key, by design). Whether a platform key is configured for real administrators on AWS is not visible to demo accounts.

**Website rule:** the site may say AI features *use a configured AI provider, such as OpenAI, when an administrator enables one, and otherwise run in a labelled simulation.* It must **not** say AI is live in the public demo, or show a "Live AI" result as the norm.

**Not to claim:**
- customer hospitals, deployments, payer or vendor connections, or certifications;
- HIPAA compliance or clinical outcomes;
- time or cost savings, or "AI-powered decisions".

---

## 4. Refined core product definition

**Your central idea, evaluated.** *"One unified platform that connects hospital departments, patient information, operational workflows, and AI assistance so healthcare teams can coordinate care and manage hospital operations without switching between disconnected systems."*

This is accurate to the code.
- One database and one patient record across departments.
- Cross-department workflows: the discharge checklist, cases routed to roles.
- AI that runs inside the same permissions.

Two refinements:
1. **Name the mechanism.** "Connects" is abstract. The real mechanism is *shared records + owned work + one hospital view*.
2. **Qualify "without switching systems".** It is true *inside* HMS Workflows, but outside systems (payers, PACS, suppliers) are simulated today. Phrase it as a design goal, not a delivered integration.

**One-sentence definition.**
> HMS Workflows is a hospital management platform that puts every department on one shared patient record, turns problems into owned and tracked work, and gives leaders one live view of the hospital — with AI that drafts and summarizes while people decide.

**Elevator pitch (≈50 words).**
> Hospitals run on separate systems for each department, so information is retyped, work is chased by phone, and no one sees a delay until it's late. HMS Workflows gives clinical, operational and financial teams one shared record and one list of what needs doing. Automation finds problems; AI assists; people approve.

**30-second explanation (≈90 words).**
> A patient's stay touches the front desk, doctors, nurses, the lab, pharmacy, bed management and billing. In most hospitals each of those has its own tools. HMS Workflows puts them on one platform. Everyone works from the same patient record. Background checks spot problems — an unconfirmed insurance policy, a discharge step nobody has done, stock about to expire — and assign each one to the right team with a deadline. Administrators see the whole hospital in a Command Center where every number opens the records behind it. AI drafts notes and summaries, and anything it proposes waits for a person to approve.

**Problem statement.**
> Hospital work crosses departments, but hospital software usually doesn't. Information is re-entered, hand-offs happen by phone, responsibility for delays is unclear, and leaders only see bottlenecks after they have already affected patients.

**How HMS Workflows solves it.**
1. **One shared record:** every department reads and writes the same patient information.
2. **Owned work:** problems become cases with an owner, a deadline and escalation that keeps the owner accountable.
3. **One hospital view:** the Command Center shows capacity, delays and priorities, each traceable to its source.
4. **Assistance with control:** automation and AI reduce manual checking and drafting; people review, approve and sign.

**Differentiated capabilities (each verified in code).**
1. **Problems become owned work.** Monitors open one case per problem, route it to a role with a deadline, escalate without removing the owner, and close it only when the record shows it is fixed (`backend/app/engine/`, migration 0029).
2. **A traceable hospital view.** Every Command Center figure opens the cases or patients behind it.
3. **AI inside the same permissions, with approvals.** Agents act only through backend tools under the user's permissions. Proposals wait in My work. Every answer is labelled *Live AI* or *Simulated*.
4. **Cross-department hand-offs built in.** The discharge checklist shows what each department still owes; critical results require acknowledgement; pharmacy waste needs a second person.
5. **Role-specific workspaces.** Each role lands on its own Home, with its priorities, today's figures and quick actions.

**Value proposition for hospital administrators.**
> See where the hospital is waiting — beds, discharges, emergency, coverage, stock — and who owns each problem, in one place, without asking every department for a report.

---

## 5. Target audience

| Audience | Main concerns | What they need to see |
|---|---|---|
| Hospital executives | Capacity, throughput, risk, cost of change | One-line value, Command Center, honest status |
| **Hospital administrators / operations leaders** (primary) | Delays, discharges, beds, ownership, reporting burden | Problem statement, owned work, Command Center, patient journey |
| Clinical leaders | Safety, documentation burden, alert fatigue | Patient chart, allergy safety, AI drafts needing sign-off, red-only-for-danger status |
| Doctors and nurses | Speed, fewer clicks, clear priorities | Role Home, My work, chart, scribe |
| Operational managers (bed, pharmacy, lab, billing) | Queues, hand-offs, stock, denials | Department screenshots on Solutions |
| Healthcare IT | Security, roles, audit, integrations, deployment | Architecture summary, RBAC, audit, simulated vs live table, AI key handling |
| Academic / research stakeholders | Design rationale, AI governance, honesty | AI & Automation page, product status, about |
| Partners and investors | Scope, differentiation, maturity | One-sentence definition, differentiators, demo, status |

**Recommendation.** The homepage speaks to **hospital administrators and operations leaders**, with clinical leaders as the secondary audience. Everyone else is routed to a supporting page:
- clinicians → Solutions;
- IT and academics → AI & Automation and About;
- evaluators → Explore the demo.

---

## 6. Hero concepts

All three keep authentication and demo access working. Only their location changes.

### Concept A — Product-first (recommended)

```
[W HMS Workflows]   Platform  Solutions  AI & Automation  About      [Explore the demo] [Sign in]
──────────────────────────────────────────────────────────────────────────────────────────────
 HOSPITAL MANAGEMENT PLATFORM
 Your Entire Hospital.                                    ┌──────────────────────────────────┐
 Working as One.                                          │  real screenshot: Command Center │
                                                          │  (redesigned, synthetic data)    │
 One shared patient record, one list of what needs doing, │                                  │
 and one live view of the hospital — for clinical,        └──────────────────────────────────┘
 operational and financial teams.                          Synthetic demonstration data
 [Explore the live demo]   [See how it works →]
```

- **Eyebrow:** Hospital management platform
- **Headline:** Your Entire Hospital. Working as One.
- **Subheadline:** One shared patient record, one list of what needs doing, and one live view of the hospital — for clinical, operational and financial teams.
- **Primary CTA:** Explore the live demo (→ demo section or `/demo`)
- **Secondary CTA:** See how it works (→ #how-it-works)
- **Visual:** the redesigned Command Center screenshot on a light background, captioned "Synthetic demonstration data".
- **Tradeoffs.**
  - *Pros:* answers what, who and why in one screen; keeps the approved tagline; real product as proof; lowest risk.
  - *Cons:* the tagline alone is still a slogan, so the subheadline must do the work.

### Concept B — Problem-first

- **Headline:** Hospital work crosses departments. Your software should too.
- **Subheadline:** HMS Workflows puts every department on one patient record, turns problems into owned work, and shows leaders where the hospital is waiting.
- **Tagline** moves to the eyebrow: *Your Entire Hospital. Working as One.*
- **CTAs:** Explore the live demo · See how it works
- **Visual:** a split screenshot: a discharge checklist "Waiting on: Pharmacist, Receptionist" beside the Command Center.
- **Tradeoffs.**
  - *Pros:* strongest narrative; immediately relevant to administrators.
  - *Cons:* demotes the approved tagline, and the headline sounds like a statement rather than a brand.

### Concept C — Role-first, interactive

- **Headline:** Your Entire Hospital. Working as One.
- **Subheadline:** Choose a role to see your workspace.
- **Control:** a segmented control (*Administrator · Doctor · Nurse · Front desk · Patient*) swaps the screenshot and one sentence beneath it.
- **CTAs:** Try this role in the demo · Sign in
- **Tradeoffs.**
  - *Pros:* engaging; shows breadth; links straight into the matching demo role.
  - *Cons:* more to build and maintain (five screenshots that must stay current); the definition gets pushed below the fold; risks feeling like a demo again.

**Recommendation:** **Concept A** for the hero, with Concept B's problem sentence as the first section after it. Concept C's role switch can live in the "Built for each team" section.

---

## 7. Login and Demo Access strategy

| | A. Product homepage + dedicated Sign in (recommended) | B. Product homepage + small login | C. Keep split hero, improve content |
|---|---|---|---|
| **Advantages** | Clear purpose per page; enterprise convention; product gets the hero; `/login` already exists with the same `LoginForm` and demo box | Returning users sign in from Home without a click | Least change; familiar to current users |
| **Disadvantages** | One extra click for returning staff | Still competes with the product story; cramped; demo box hard to fit | Product remains second to the form; the core problem persists |
| **Visitors** | Understand the product first | Mostly understand it, with distraction | Still read it as a login page |
| **Returning users** | "Sign in" stays top-right on every public page; `/login` can be bookmarked; signed-in users are redirected straight to the app as today | Fastest | Fastest |
| **Public demo** | Dedicated *Explore the demo* section and page with role cards explaining what each role sees, plus the same one-click accounts | Demo squeezed into the hero | Unchanged |
| **Complexity** | **Low**: remove `LoginForm` from `HomePage`; nav button → `/login`; new demo section reuses `ServerDemoAccess` logic (`/auth/demo`, `/auth/demo-login`) | Medium (new compact form variant) | Low–medium |

**Recommendation: Option A.**
- **Sign in:** a nav button opens `/login` (unchanged form, unchanged demo box).
- **Explore the demo:** a homepage section and an optional `/demo` page with seven role cards, for example:
  - "Doctor — today's patients, chart, AI scribe";
  - "Super Admin — AI settings in an isolated demo session".

  Each card has a *Start as Doctor* button that calls the existing demo login.

  Above the cards, a short notice: *"Synthetic data only. Demo sessions can't change real settings. AI answers in the demo are labelled Simulated unless you add your own key in the demo AI settings."*
- **No change to authentication behaviour,** the demo allowlist or the AI isolation.

---

## 8. Recommended homepage (sections, copy, visuals)

Seven sections plus the footer, about 3,400–3,800 px at desktop (today: 4,303 px). Light page with one dark band at most.

| # | Section | Main message | Visitor should understand | Visual | Short copy | Action | Placement |
|---|---|---|---|---|---|---|---|
| 1 | **Hero** | What it is, for whom | A hospital management platform for all teams | Real Command Center screenshot | See Concept A | Explore the live demo · See how it works | Home |
| 2 | **The problem** | Hospital work crosses departments; software doesn't | Why a shared platform matters | Three short text columns, no icons or one line icon each | see 8.2 | — | Home |
| 3 | **How it works** | Shared record → owned work → one view → assistance | The mechanism, in four steps | Four small real screenshots (chart, My work, Command Center, AI panel) | see 8.3 | Platform overview → | Home |
| 4 | **One patient, every department** | Hand-offs are built in | Departments connect through the same record and checklists | Stepper of 6 stages; each shows the real screen for that stage | see 8.4 | — | Home |
| 5 | **See the whole hospital** | Leaders see delays and owners | Command Center = status → problems → detail, traceable | Large current screenshot with 3 callouts | see 8.5 | Command Center details → | Home |
| 6 | **Automation and AI, explained** | Rules find problems, AI drafts, people decide | The difference between automation, AI and approval | A 5-row comparison, no glowing tiles | see 8.6 | AI & Automation → | Home |
| 7 | **Built for each team · Explore the demo** | Every role has its own workspace; try one | Who it's for, and how to explore safely | 4 team columns + 7 role cards | see 8.7 | Start as … | Home (full detail on Solutions / Demo) |
| — | **Footer** | Navigation, status, legal | Where to find status and legal notes | — | see 8.8 | — | All pages |

**Removed or merged from today's Home.**
- *Six connected systems* hub: merged into section 4.
- Hero highlight pills and the "AI-powered" sparkle pill: removed.
- *Explore every module and role* band: replaced by section 7.
- The login card: moved to `/login`.

### 8.2 The problem — copy
**Hospital work crosses departments. Most hospital software doesn't.**
- **Information is entered twice.** Registration, the ward, pharmacy and billing each keep their own version of the patient.
- **Hand-offs depend on phone calls.** A discharge can wait on a signature, a medication check and a transport booking, and nobody sees all three.
- **Delays surface late.** Leaders learn about blocked beds and overdue tasks from reports, after patients have waited.

### 8.3 How it works — copy
**One platform, four layers.**
1. **One shared record.** Every department works on the same patient record and timeline.
2. **Work with an owner.** Problems become cases with an owner, a deadline and escalation, and close only when the record shows they're fixed.
3. **One view of the hospital.** The Command Center shows capacity, delays and priorities, and every number opens the records behind it.
4. **Assistance, with people in control.** Automation checks for problems; AI drafts notes and summaries; anything that changes data waits for approval.

### 8.4 One patient, every department — copy and screens
**Follow one patient through the hospital.**

| Stage | Screen | Copy |
|---|---|---|
| Arrival | Front desk arrivals list | Check-in, insurance readiness and wait times in one list. |
| Emergency | ED board | Triage, rooming and time in department, with acuity recorded by clinicians. |
| Care | Patient chart | History, vitals, problems and allergies in one chart; "none recorded" is never shown as "no known allergies". |
| Tests & medication | Lab bench / pharmacy verification | Results are verified by a second person; new orders are verified by a pharmacist. |
| Admission & discharge | Discharge checklist ("Waiting on…") | Each department sees what it still owes before the patient leaves. |
| Billing & follow-up | Claims review · Patient portal To do | Claims are checked before submission; patients confirm insurance and forms online. |

### 8.5 Command Center — copy
**See where the hospital is waiting.**
- **Hospital status:** occupancy, emergency pressure, patients waiting for a bed, discharges and staffing gaps.
- **Needs attention:** open problems grouped by area, clinical risk first, each with an owner and how overdue it is.
- **Department detail:** capacity by unit, queues and automation health, and every figure opens the records behind it.

### 8.6 Automation and AI, explained — copy
**Automation finds the problem. AI helps with the work. People decide.**

| | What it does | Example in HMS Workflows | Who's in control |
|---|---|---|---|
| **Rules-based automation** | Checks records on a schedule and opens a case when something is wrong | Coverage not confirmed before a visit; stock expiring; discharge step missing | Thresholds set by administrators; cases assigned to a team |
| **AI summaries and drafts** | Reads what you're allowed to see and writes a summary or draft | Visit-note draft from a consented conversation; document details extracted for review | Clinician or staff reviews, edits and signs |
| **AI assistants (agents)** | Answers questions using approved tools and can *propose* actions | "What is blocking this discharge?" → proposes a reminder task | Proposals wait for approval in My work |
| **Realtime voice** | Spoken conversation in the browser for administrative tasks | Receptionist practice calls | Needs a configured AI provider |
| **Human approval** | Every data-changing proposal needs a person | Approve or reject in My work | Recorded in the audit log |

*Footnote:* "AI features use a configured AI provider, such as OpenAI, when an administrator enables one, and otherwise run in a clearly labelled simulation. Every answer shows which."

### 8.7 Built for each team · Explore the demo — copy
**Built for each team.**
- **Clinical teams** — today's patients, charts and documentation help.
- **Operations** — beds, discharges, emergency flow and the Command Center.
- **Revenue** — coverage checks, claim review and authorizations.
- **Patients** — booking, forms, messages, results and bills.

**Explore the demo.** "Sign in as a role with synthetic data. Demo sessions can't change real settings." Seven role cards follow.

### 8.8 Footer
| Column | Links |
|---|---|
| Platform | Overview, Command Center, Automation & AI, Patient portal |
| Solutions | By role |
| Company | About, Product status, Legal notices |
| Access | Sign in, Explore the demo |

The bottom bar keeps `© 2026 Sidra Riaz Awan. All rights reserved.` and adds the note *"Demonstration build with synthetic data; not certified for clinical use."* Remove "Reset password" from the footer; it already lives on `/login`.

---

## 9. Supporting pages and information architecture

**Navigation:** Platform · Solutions · AI & Automation · About · [Explore the demo] · [Sign in]. That is four content pages and two actions, without adding a new page for every module.

| Page | Purpose | Content structure |
|---|---|---|
| **Platform** (renames *Modules*; `/modules` redirects) | What the system does, organised one way everywhere | 1) Short definition. 2) Five capability areas with one real screenshot each — **Clinical care** (registration, scheduling, EHR, orders/results); **Hospital operations** (ED, inpatient, nursing, beds, discharge); **Diagnostics & pharmacy** (lab, radiology, pharmacy, inventory); **Revenue** (Insurance Guardian, claims, authorizations, billing); **Coordination & insight** (My work, automation, Command Center, analytics). 3) Patient portal. 4) Administration & security (roles, audit, key handling). 5) "Implemented vs simulated" table |
| **Solutions** | By role | Keep the 8 roles, but each gets: the problem in one line, a screenshot of that role's Home or workspace, and 3–4 bullets. Add "Try this role" buttons that call the demo login |
| **AI & Automation** (new) | The careful explanation | Rules vs AI vs approval table (expanded); each assistant with its permission boundary; provenance labels (Live AI / Simulated / AI draft / Rule alert / Awaiting approval); data handling (keys encrypted server-side, never shown in the browser; PHI setting); what has and hasn't been verified live |
| **About** | Mission and honest status | Mission; differentiators (the five from §4); product status (Implemented · Simulated · Requires credentials · Not certified); technology summary for IT; legal |
| **Explore the demo** (section on Home, optional `/demo`) | Safe exploration | Role cards, what each role sees, synthetic-data and isolation notice |
| **Sign in** (`/login`, exists) | Returning users | Unchanged form and demo box |

---

## 10. Brand messaging and content quality

| Current copy (fact) | Issue | Replacement |
|---|---|---|
| Pill: "HMS Workflows · AI-powered hospital management" | Generic "AI-powered" lead | Eyebrow: "Hospital management platform" |
| "…in one intelligent workspace. With AI-assisted documentation and coordinated workflows, healthcare teams can manage the patient journey through a connected platform." | Abstract, repeats "connected", 35 words | "One shared patient record, one list of what needs doing, and one live view of the hospital — for clinical, operational and financial teams." |
| "Six connected systems. One platform." | Count conflicts with Modules | "Follow one patient through the hospital." |
| "Meet HMS Workflows AI" + 6 cards | Mixes rules and AI | "Automation finds the problem. AI helps with the work. People decide." |
| "Practical AI assistance built into everyday healthcare workflows." | Generic | (removed; the table explains it) |
| "See the Whole Hospital. In One Workspace." | Good, slightly generic | "See where the hospital is waiting." |
| Modules H1 "Everything Your Hospital Needs, Connected." | Overclaims completeness | "One platform for clinical, operational and financial work." |
| Solutions H1 "Designed Around the People Who Run Healthcare." | Acceptable | "A workspace for every role in the hospital." |
| About "intelligent automation" | Vague | "background checks that assign problems to the right team" |
| "HMS Workflows AI" sub-brand | Implies a separate AI product | Refer to "AI assistants in HMS Workflows" |

**Style rules for all public copy.**
- Write sentences of fewer than 25 words. Use a verb plus a concrete object.
- Never use "revolutionize", "cutting-edge", "seamless" or "intelligent" (as filler).
- Make no number claims except product facts, such as "seven demo roles".
- Name a simulated integration once per page, in context, not as a badge on every card.
- Title Case for headings is inconsistent today ("From Arrival to Follow-Up. All Connected." versus sentence-case elsewhere). Use **sentence case** for all headings, matching the app.

---

## 11. Product screenshot recommendations

Capture with a script (Playwright, the same approach used for audits) against the local synthetic-data stack, so the images can be regenerated after every UI change.

**Capture settings.**
- 1440×900, light theme, comfortable density.
- Synthetic data only, with no personal email addresses visible.
- Exclude `/admin/ai-settings` (key hints), the outbox (reset links), the audit log (emails and IPs) and anything showing API keys.
- Export WebP at 1600 and 800 widths, with descriptive alt text.

| # | Screen | Message it supports | Where |
|---|---|---|---|
| 1 | Command Center (three levels) | Leaders see delays and owners | Hero, section 5, Platform |
| 2 | Patient chart (banner, vitals with "High", allergies none recorded) | One record; safety-aware design | Section 3/4, Platform, Solutions (doctors) |
| 3 | My work (cases with owners and overdue) | Problems become owned work | Section 3, AI & Automation |
| 4 | Discharge checklist "Waiting on…" | Cross-department hand-offs | Section 4 |
| 5 | Doctor Home (priorities, Today, quick actions) | Role workspaces | Section 7, Solutions |
| 6 | Front desk arrivals | Arrival and insurance readiness | Section 4, Solutions |
| 7 | ED board | Emergency flow | Section 4, Platform |
| 8 | AI side panel (Simulated label, evidence, awaiting approval) | AI with provenance and approval | Section 6, AI & Automation |
| 9 | Agent Studio | Configurable assistants with limits | AI & Automation |
| 10 | Patient portal Home (To do, next visit) | Patient experience | Section 7, Platform |
| 11 | Insurance Guardian | Coverage checks before visits | Platform (revenue) |

**Presentation rules.**
- **Frame:** a 1 px border, 8–12 px radius and a soft shadow. No fake macOS window dots.
- **Caption:** "Synthetic demonstration data" under each image.
- **Callouts:** at most three numbered callouts per image.
- **Accuracy:** never alter screenshots to show data or features that don't exist.

---

## 12. Before-and-after concepts

**1. Main hero.**
```
BEFORE                                                    AFTER
┌ photo of hospital (glowing cross), dark navy ─────────┐ ┌ white/light background ─────────────────────────────┐
│ [✦ AI-powered hospital management]   ┌─────────────┐  │ │ HOSPITAL MANAGEMENT PLATFORM                         │
│ Your Entire Hospital.                │ Sign in     │  │ │ Your Entire Hospital.          ┌───────────────────┐ │
│ Working as One. (gradient)           │ email       │  │ │ Working as One.                │ Command Center    │ │
│ From the first appointment…          │ password    │  │ │ One shared patient record, one │ (real screenshot) │ │
│ 35-word paragraph                    │ [Sign in]   │  │ │ list of what needs doing, one  └───────────────────┘ │
│ (pill)(pill)(pill)                   │ Demo: 7 btn │  │ │ live view of the hospital.     Synthetic data        │
│ [Explore modules] See how…           └─────────────┘  │ │ [Explore the live demo] [See how it works →]         │
└───────────────────────────────────────────────────────┘ └─────────────────────────────────────────────────────┘
```

**2. Navigation.**
```
BEFORE  [U?] HMS Workflows   Home  Modules  Solutions  About                     [Sign In]
AFTER   [W] HMS Workflows    Platform  Solutions  AI & Automation  About   [Explore the demo] [Sign in]
```
"Explore the demo" is the solid button; "Sign in" is an outline button.

**3. Connected ecosystem.**
```
BEFORE  glowing hub "HMS Workflows" + 6 floating boxes + dashed lines (abstract)
AFTER   "Follow one patient through the hospital"
        (Arrival)──(Emergency)──(Care)──(Tests & meds)──(Discharge)──(Billing & follow-up)
        ┌ selected stage: real screen + 1 sentence + which teams act here ┐
```

**4. Patient journey.**
```
BEFORE  7 equal text cards with module pills
AFTER   merged into 3 (one stepper, real screenshots, 6 stages, keyboard and swipe accessible)
```

**5. AI and automation.**
```
BEFORE  "Meet HMS Workflows AI": 6 gradient-icon cards (2 of them are rules, not AI)
AFTER   "Automation finds the problem. AI helps with the work. People decide."
        ┌ Rules-based automation │ AI summaries & drafts │ AI assistants │ Realtime voice │ Human approval ┐  (table)
        [AI side panel screenshot: Simulated label · evidence · awaiting approval]   [AI & Automation →]
```

**6. Command Center showcase.**
```
BEFORE  old "Undeclared" screenshot (dark sidebar), 8 icon bullets, fake window dots
AFTER   current Command Center screenshot with 3 numbered callouts:
        ① Hospital status  ② Needs attention (owner + overdue)  ③ Department detail   [Command Center details →]
```

**7. Demo Access and Sign in.**
```
BEFORE  login form + 7 small demo chips inside the hero card
AFTER   Home: "Explore the demo" section → 7 role cards (title, what you'll see, [Start as Doctor])
        Notice: synthetic data · demo sessions can't change real settings · AI labelled Simulated unless you add a key
        Nav: [Sign in] → /login (existing form + demo box, unchanged)
```

**8. Footer.**
```
BEFORE  brand blurb | Platform: Modules/Solutions/About | Account: Sign in/Reset password/Legal
        © 2026 Sidra Riaz Awan. All rights reserved.            HMS Workflows | About & Legal
AFTER   brand + one-sentence definition | Platform | Solutions | Company (About, Product status, Legal) | Access
        © 2026 Sidra Riaz Awan. All rights reserved. · Demonstration build with synthetic data; not certified for clinical use.
```

---

## 13. Visual design recommendations

Carry the app's design system to the public site rather than keeping a separate "marketing look".

- **Canvas.**
  - Light (`#FFFFFF` / `#F5F7FA`), Harbor Blue `#1D5BD6` for actions.
  - Navy `#0B2545` for at most one band (the footer, or the AI section).
  - Remove the photographic hero.
- **Typography.** Inter, with a display scale for the website only:

  | Role | Size / line height |
  |---|---|
  | H1 | 56/64 desktop, 36/44 mobile |
  | H2 | 36/44 |
  | Lead | 18/28 |
  | Body | 16/26 |

  Line length is capped at about 65 characters, with sentence-case headings.
- **Layout.**
  - 12-column grid, 1200 px content width, generous vertical rhythm (96 px between sections).
  - Text left with the screenshot right, alternating sparingly.
- **Remove these effects:**
  - `eco-pulse` / `eco-flow` animations and blurred radial gradients;
  - gradient text on the H1 and gradient icon tiles;
  - traffic-light window frames and the sparkle "AI-powered" pill.
- **Icons.** Lucide only, single colour, used to label, not to decorate. Many sections need none.
- **Motion.**
  - A 150–200 ms fade on scroll into view.
  - The journey stepper transitions.
  - Respect `prefers-reduced-motion`, as today.
- **Logo.** Fix the open issue: on dark backgrounds the navy tile needs the inverse version (lighter tile `#1B3A63` or a 1 px white/15% outline).
- **Accessibility.**
  - AA contrast throughout, which a light canvas makes easier.
  - Real headings in order and descriptive alt text on screenshots.
  - The stepper is operable by keyboard and announced as tabs.
  - No text inside images except the screenshots themselves.

**Reference principles** from mature enterprise and healthcare software sites (organisation and trust only, not design or copy):
- one sentence that says what the product is;
- product imagery over illustration;
- a clear split between product, solutions and company pages;
- a visible "contact / demo" path;
- restraint in colour and claims.

---

## 14. Implementation roadmap

**Reuse.**
- `PublicLayout` (header and footer structure).
- `PublicLoginPage` and `LoginForm` (unchanged, on `/login`).
- The demo-login logic in `LoginForm.tsx` (`ServerDemoAccess`, `/auth/demo`, `/auth/demo-login`), extracted into a `DemoRoleCards` component.
- `Logo.tsx` and `lib/legal.ts` (name, tagline, copyright).
- `content.ts`: edit and regroup into five capability areas.
- The design tokens and components of the app (Button, Badge, Card, Segmented).

**Redesign or new.**
- `HomePage` sections (§8).
- `ProductShot` component: `<picture>` with WebP 1600/800, caption and callouts.
- `JourneyStepper`, which replaces `Ecosystem.tsx` and the journey cards.
- `AiExplainer` table.
- `PlatformPage` (replaces `ModulesPage`, with a `/modules` redirect).
- `AiAutomationPage`.
- An updated footer.

**Remove.**
- The hero login card on Home.
- `HospitalBackdrop` on Home (keep it on `/login` or replace it there too).
- The `eco-*` CSS and `Ecosystem.tsx` once replaced.
- `HIGHLIGHTS`, and `HOME_MODULES` if unused.

**Assets.**
- A screenshot capture script, e.g. `scripts/capture_marketing_shots.py`.
- `frontend/public/images/product/*.webp`.
- Retire `command-center*.webp` and `hospital-hero*.webp` once replaced.
- Images are lazy-loaded below the fold, with explicit width and height to avoid layout shift. The hero image is eager.

**Responsive.**
- Hero stacks: text, CTAs, then screenshot.
- The stepper becomes a vertical list with a screenshot per stage.
- The AI table becomes stacked cards on phones.

**Performance.** No new dependencies, and a total image weight target of about 600 KB for Home.

**Minimal testing.**
- Typecheck and build.
- A focused Playwright check:
  - Home renders the H1;
  - the demo role card signs in as Doctor;
  - `/login` works;
  - `/modules` redirects to `/platform`;
  - no horizontal scroll at 390 px;
  - no page errors.
- Live: the deploy smoke test.
- No backend changes are needed.

**Order.**
1. Screenshot capture script and assets.
2. Content and taxonomy edits in `content.ts`.
3. Home sections.
4. Demo section, with login moved off Home.
5. Platform page, with `/modules` redirect.
6. AI & Automation page.
7. About and Solutions refresh.
8. Footer and navigation.
9. Polish, accessibility and mobile.

Steps 1–4 deliver most of the improvement.

---

## 15. Risks and limitations

- **Screenshots go stale.** Mitigation: scripted capture, and regenerate on UI changes.
- **"Live AI" expectations.** The public demo runs simulated AI by design. The site must say so, or visitors will assume something is broken.
- **Returning-user friction.** One extra click to sign in. Mitigation: a prominent nav "Sign in"; `/login` bookmarkable; signed-in users skip public pages, as today.
- **Overclaiming by implication.** Screenshots of payer and claims screens could imply live payer connections. Captions must note simulated integrations where relevant.
- **Live AI verification.** Live OpenAI is verified only for one agent run locally. Scribe, document reading and voice are not yet verified live, so don't feature them as live.
- **Sign-in behaviour.** It is unchanged. Only the homepage entry point moves.
- **Out of scope.** This plan does not cover SEO, analytics, cookie consent or a contact/lead form. There is no backend for leads, so don't add a "Request a demo" form without one.

---

## 16. Final recommended direction

Make the homepage a calm, light, product-first page that:
- **says plainly what HMS Workflows is:** a hospital management platform with one shared record, owned work, one hospital view, and AI with people in control;
- **shows the real redesigned application** as the evidence;
- **follows one patient** through the departments;
- **explains automation, AI and approval** in one honest table;
- **ends with a safe, well-explained demo.**

Move sign-in to `/login`, keep the tagline, keep the honesty, and remove the decorative effects that make it look like a prototype.

### The five decisions to approve before implementation

1. **Hero:** Concept A (product-first, tagline kept, real Command Center screenshot), with B's problem statement as section 2.
2. **Sign in:** Option A. Remove the login card from Home; Sign in via the nav to the existing `/login`; demo access moves to an "Explore the demo" section with role cards.
3. **Navigation and taxonomy:** Platform · Solutions · AI & Automation · About · Explore the demo · Sign in. *Modules* becomes *Platform* (with a redirect), and the five capability areas are used everywhere.
4. **Product evidence:** replace all illustrative and stale imagery, including the old-brand screenshot and the hospital photo with the cross, with scripted screenshots of the redesigned app on synthetic data.
5. **AI messaging:** a new AI & Automation page and homepage table that separate rules, AI drafts, assistants, voice and human approval. The public demo is described as *Simulated unless a key is provided*; no live-AI claims beyond what has been verified.
