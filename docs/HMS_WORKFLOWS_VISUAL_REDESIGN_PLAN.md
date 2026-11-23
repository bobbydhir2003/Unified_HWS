# HMS Workflows — Visual Redesign Plan

**Status:** proposal for approval. Nothing here is implemented. No code, data, branding or deployment was changed.
**Inspected:** 23 Nov 2026 · live site `https://3-19-143-26.sslip.io` (commit 4d9ee66) + local stack (same code) · `frontend/src`.
**Visual concepts:** design canvas *HMS Workflows Redesign Concepts* — https://claude.ai/artifact/Mw2LzQgaNJLq9pbE6Zu4QA (private to the owner until shared). It contains the foundation sheet, the “before” screenshots with annotations, and eight “after” screens.

How to read this document:

- **Fact** — observed on the live site, in screenshots, in measured DOM/CSS values or in the source code.
- **Recommendation** — a design proposal. Nothing is decided until approved.

---

## 1. Executive summary

The structure built in the last redesign is right: role Homes, short navigation, My work, grouped chart and contextual AI. What makes the product look unfinished is **presentation**:

1. **No enforced type scale.** Feature code uses 32 font sizes, 24 of them arbitrary pixel values such as `text-[13px]` (292 uses) and `text-[13.5px]` (123 uses).
2. **Red on almost everything.** Any overdue item becomes a red “Urgent” pill. Seeded tasks are about 4 days old, so Home, My work and Command Center are a wall of red. Real clinical urgency cannot stand out.
3. **Template look.**
   - The dark navy sidebar, gradient logo tile and stacks of equal-size KPI boxes read as a generic React admin dashboard.
   - The brand appears three ways: “Undeclared”, “Undeclared HMS” and “Sign in to Undeclared”.
4. **Every page invents its own pieces.** There are 10 tab or filter implementations, at least 5 KPI tile styles, card-in-card layouts, and one-off button emphasis:
   - Front desk shows 14 primary buttons on one screen;
   - Agent Studio shows 17;
   - Monitors shows 22.
5. **Wasted space next to crowding.** Some layouts leave half-empty columns (Home quick actions, empty kanban columns, fixed-height chart cards). Others pack 20 equal tiles before the first actionable item (Command Center).
6. **Accessibility gaps in shared tokens.**
   - Green and amber status text measures 3.6:1 and 3.4:1; AA needs 4.5:1.
   - Dark-mode cards are only 1.06:1 against the page.
   - BMI and expiry flags use colour alone.

**These are mostly shared-component and token problems.** About 70% of the visible improvement comes from changing about 15 shared files:
- `index.css`;
- `components/ui/*`;
- `components/common/*`;
- `AppShell.tsx`.

Seven page files are then rebuilt on top: Home, My work, chart, Command Center, Front desk, the AI panel and the portal.

**Recommended direction:**
- **Palette A, “Harbor Blue”**, on a light, document-like workspace with a light sidebar;
- Inter with a 7-size type scale;
- one status language in which red means clinical severity only and overdue becomes amber with a clock;
- one metric strip, one table, two tab styles;
- the brand **HMS Workflows**, with a continuous-route “W” mark.

Implement in four phases. Phase A (foundation and shell) alone changes every screen.

---

## 2. Current visual problems, with evidence

### 2.1 How the evidence was gathered (fact)

- **Screens captured.** 57 read-only screen captures:
  - 1440×900 for every role;
  - 1366×768 dark, 1280×720 and 390×844;
  - the live site for the 7 demo roles;
  - the local stack for pharmacist, lab, radiology, bed manager and hospital admin (same code; not on the live demo list).
  - Scripts only navigated. No forms were submitted.
- **DOM metrics per screen:** distinct rendered font sizes, buttons, primary buttons, bordered cards, tables, chips, page height and horizontal overflow.
- **Code scan of `frontend/src/features`:** 59 files, about 12,400 lines.
- **WCAG contrast** computed from the OKLCH tokens in `index.css`.

### 2.2 Measured facts

| Measure | Value | Where |
|---|---|---|
| Distinct font sizes in feature code | **32** (24 arbitrary px values; the largest are on public pages) | `text-[13px]` ×292, `text-[13.5px]` ×123, `text-[15px]` ×31, `text-[12.5px]` ×28 … |
| Tab / filter implementations | **10** | Radix `TabsList` (9 files) + hand-built in `PatientChart`, `SchedulePage`, `PortalHome` (×2), `AIPages`, `DocumentsPage`, `BillingPage`, `AnalyticsPage`, `WorklistPage` |
| KPI tile implementations | **≥5** | `Stat` (`components/common`) + hand-built in `RoleHome`, `BedBoard`, `EdBoard`, `BillingPage`, `PortalHome`, `CommandCenter` |
| Primary buttons on one screen | 14 / 17 / 22 | Front desk / Agent Studio / Monitors & rules |
| Command Center | 55 buttons, 25 bordered boxes, 10 font sizes, 1,758 px tall | live, super admin |
| Monitors & rules page height | 4,910 px, 89 chips | live |
| Horizontal overflow | none at 1440 / 1366 / 1280 / 390 | all captured screens (good) |
| Shadows / radii | 8 shadow styles, 6 radius sizes (`rounded-md` … `rounded-3xl`) | feature code |
| Raw Tailwind palette colours | 57, all in public site, login, video visit and portal | staff app uses tokens (good) |

**Contrast of current tokens** (computed):

| Pair | Ratio | Result |
|---|---|---|
| Body text on background | 16.1 | pass |
| Muted text on card | 5.5 | pass |
| White on primary button | 6.5 | pass |
| **Success text on success-soft** (“Ok”, “Healthy”, “No known allergies”) | **3.63** | **fails AA for 11.5–12 px** |
| **Warning text on warning-soft** (“Synthetic data”, “No analyzer interface…”, “Payer decisions simulated”) | **3.42** | **fails** |
| Warning icon on white | 2.99 | fails 3:1 non-text |
| Border vs card | 1.29 | dividers fine; input outlines too faint |
| **Dark: card vs page** | **1.06** | surfaces nearly indistinguishable |
| Dark: primary button text | 6.7 (sampled from screenshot) | pass |

### 2.3 Screen-by-screen observations (facts from the screenshots)

**App shell (all staff screens)**
- **Sidebar.** A dark navy, 240 px sidebar with a gradient blue “U” tile. This is the strongest “admin template” signal. The selected item is a slightly lighter navy, which is low salience.
- **Facility context.** The facility switcher is in the sidebar, but the department and page appear only as a small breadcrumb in the header. On Home the breadcrumb just says “Home”.
- **Wasted header space.** The search box is 256 px wide with nothing in the middle of the header.
- **Footer.** It appears inside the scroll area on every page, which adds a band of chrome to work screens.

**Doctor Home**
- **Priorities.** All five priorities carry a red dot and a red “Urgent” pill. Each is overdue discharge paperwork, not a clinical emergency.
- **Repetition in each row:**
  - the patient name appears in the title and again in the meta line;
  - the meta line shows “Owner: Doctor” on the doctor’s own list;
  - “overdue 4 days ago” is ungrammatical.
- **Quick actions** occupy a full one-third column for four links, with empty space below.
- **Today** shows four boxed numbers inside a card (card-in-card), and three of them are zero at equal weight. One grid slot is empty.
- **The AI button** (“Summarize my discharge tasks”) floats alone at the top right.
- **Mobile (390 px).** Each priority row wraps to five lines, and “View all (15)” wraps.

**Nurse Home (1366×768)**
- **The most clinically relevant number is below the fold:** “Vitals overdue: 19 of 19 patients”. Above it are five discharge paperwork rows, all red.
- **The ranking causes this.** `backend/app/api/routers/home.py` `_priorities` sorts overdue → severity → due, so any overdue task outranks clinical work.

**Patient chart**
- **Header.** It is a good start: name, DOB/age, MRN, phone and coverage.
  - **Safety issue:** an empty allergy list renders a green “No known allergies” badge (`PatientChart.tsx:91`). No one documented NKA; the list is simply empty.
- **BMI 39.3** is flagged by red text only.
- **Overview cards** are fixed to equal heights. Active problems (1 row) and medications (1 row) leave large blank areas, and there is no recent-results panel.
- **Four header buttons** compete: Ask AI (soft), Edit, Book, Start visit.
- **The chart group tabs** use an underline style. Most other pages use a grey segmented `TabsList`.

**My work**
- **The tabs are good**, but they are a third tab style; the sub-filters (All / Emergency / Discharge) are a fourth.
- **The description is long** (two lines).
- **Rows are not columns.** Owner, due and status are inline text, so lists cannot be scanned vertically.

**Emergency department (dark)**
- **The board is functional** and ESI colours are clear.
- **Ragged rows.** Row heights vary because one to three action buttons stack vertically. The complaint is truncated while provider names wrap.
- **Inconsistent durations.** “89h 58m” here versus “3 d 18 h” elsewhere.

**Front desk**
- **Kanban layout.** Four columns; three are empty but full height, and the busy column needs scrolling.
- **Primary buttons.** A solid primary “Check in” appears on every card (14 primaries).
- **Counts appear twice**, in the chip row and in the column badges.
- **The identity line wraps** mid-field.

**Pharmacy / Lab / Radiology / Claims**
- **Pharmacy.** The table is good, with tabular numbers. However:
  - the KPI tiles are a fourth style (`Stat`, with icon squares);
  - the expiry date is flagged by orange text only;
  - “Expiring ≤ 30 days” shows a link icon.
- **Lab.** A solid primary “Collect” appears on every row (5 primaries). Priority “STAT” is a red pill, which is correct, but “Routine” is outlined. Fine.
- **Claims.** A single-row table floats in an otherwise empty page; the filter is an unlabeled select.

**Bed board.** Clear tiles. A fifth KPI tile style. Unit tabs are a fifth tab style.

**Command Center**
- **20 tiles before any issue.** Twelve tiles in a 6×2 grid plus eight more in a 4×2 grid appear before the first problem row.
- **Tints without meaning.** Peach, pink and green outlines carry no consistent meaning.
- **Header.** Controls wrap onto two misaligned rows.
- **Problem queue.** A flat list where every row is red, overdue and escalated.
- **Wording.** “Updated 11:28 AM (in 0 seconds)” is a wording bug.

**AI surfaces**
- **Agent Studio.**
  - 17 primary “Run” buttons and a toggle on every card;
  - developer vocabulary such as “get claim findings”, “$0.0000” and “limits 6 tools / 60s / $0.25”;
  - the provider state is a small amber chip far from the cards.
- **Ask AI** opens a centred modal that covers the work it is about.

**Monitors & rules**
- **Every rule is an always-open form.** The page is 4,910 px tall.
- **Raw values on screen.** Free-text inputs contain raw role keys (`bed_manager`), and labels are generated from keys (“Threshold Minutes”).

**Patient portal**
- **Navigation.** Nine top-level tabs, plus two bell icons (header and tab bar).
- **Repeated to-dos.** The same two items are repeated for each of three visits (six “Do it now” links).
- **Duplicated warning.** The insurance warning appears twice (banner and list).
- **Staff-sized text.** Staff type size (14 px) is used for patients.

**Super Admin Home.** Three statistics and half a page of empty space; nothing about platform health, integrations or security.

**Login / public**
- **Three brand spellings** across header, title and sidebar.
- **The hero image** contains a glowing medical cross.
- **The login card** sits on a busy photo.

**Local-only note.** The local database contains E2E artefacts such as “Jordan Verified7d3b5”. They are not on AWS, but local screens should not be used for demos.

### 2.4 Root causes (fact → file)

| Symptom | Root cause | Files |
|---|---|---|
| 32 font sizes | No named type tokens; pages pick px values | every `features/*.tsx`; `index.css` has no `--text-*` scale |
| Red everywhere | `toWorkStatus()` maps any `overdue` to `urgent` (solid red) | `components/common/Status.tsx`; Home ranking in `backend/app/api/routers/home.py` |
| Template look | Dark sidebar tokens + gradient brand tile + `Stat`-style tiles | `index.css` (`--sidebar*`), `AppShell.tsx` `Brand`, `components/common/index.tsx` `Stat` |
| Inconsistent tiles/tabs | Primitives exist but are not sufficient (no metric strip, no underline tabs, no segmented control), so pages hand-build | `components/ui/tabs.tsx`, `components/common/index.tsx` |
| Button overload | No rule or variant for row actions; pages use `default` everywhere | `components/ui/button.tsx` + page usage |
| Card-in-card, uneven heights | `Card` padding 20 px everywhere; pages nest bordered boxes inside cards; grids force equal heights | `ui/card.tsx`, `RoleHome.tsx`, `PatientChart.tsx` |
| Low-contrast chips | `-soft` backgrounds with mid-lightness text tokens | `index.css`, `ui/badge.tsx` |
| Dark mode flat | Card and page lightness 0.20 vs 0.165 | `index.css` `.dark` |
| Brand drift | `PRODUCT_NAME` exists in `lib/legal.ts` but `AppShell.tsx`, `index.html`, `LoginForm.tsx` and the public pages hard-code names | listed in §13 |

---

## 3. Proposed HMS Workflows brand identity (recommendation)

**Name.** **HMS Workflows**: “HMS” is set semibold and “Workflows” regular, in the same ink colour. Never “HMSWorkflows”, and never “Workflows” alone.

**Tagline.** *Your Entire Hospital. Working as One.* It appears only on the public site, the login page, About and documentation, never in the working app chrome.

**Mark: a continuous route.** One unbroken line through five points forms a “W”. It reads as both *Workflows* and a patient’s path through departments, and it ends in a teal node (the destination).

| Element | Treatment |
|---|---|
| Tile | Navy `#0B2545` square, radius 8 |
| Route | White, round joins |
| End node | Teal `#2BB3A3` |
| Excluded | No cross, no stethoscope, no circuit or neural-network motif |

- **Sizes.** 28 px in the sidebar, 32 px in the portal and login, 16 px favicon (route only, no node at 16 px).
- **Teal** is brand-only and never used as a status colour.
- **Inverse version.** Tile `#1B3A63` on dark.
- **Where to see it.** The canvas foundation sheet shows the mark and wordmark on light and dark.

Placement details are in §13.

---

## 4. Recommended design system (recommendation)

### 4.1 Colour: three palettes compared

| | A. Harbor Blue (**recommended**) | B. Clinical Teal | C. Ink & Indigo |
|---|---|---|---|
| Primary | `#1D5BD6` | `#0F766E` | `#4F46E5` |
| Feel | Trustworthy, clinical, familiar | Calm, “healthcare” | Modern SaaS |
| Problem | — | Teal is close to success-green: “Start visit” vs “Done” blur; teal links read less clearly | Indigo collides with AI-violet, the one colour whose meaning must be unambiguous |
| Re-learning for current users | Low (blue stays blue) | Medium | Medium |

**Palette A tokens.** Contrast is measured against the surface each colour is used on.

| Role | Light | Dark | Notes |
|---|---|---|---|
| Page (canvas) | `#F5F7FA` | `#090E18` | |
| Surface / card | `#FFFFFF` | `#162033` | dark surfaces step *up* in lightness |
| Subtle surface (table head, hover) | `#F8FAFC` / `#F2F4F7` | `#121B2C` / `#1E2A40` | |
| Divider | `#E4E7EC` | `#33445F` | |
| Input / control border | `#7F8A9C` (3.5:1) | `#6F7E97` (4.0:1) | meets 1.4.11 for input outlines; buttons keep the lighter `#D0D5DD` |
| Title ink | `#101828` | `#F2F5FA` | |
| Body text | `#1D2939` | `#E3E8F0` (13:1) | |
| Secondary text | `#475467` (7.7:1) | `#B4BFD0` | |
| Tertiary / labels | `#5D6B82` (5.0–5.4:1) | `#9AA8BC` (6.7:1) | smallest text colour allowed |
| Primary (actions, links, selection) | `#1D5BD6` (white text 6.0:1) | `#6EA4FF` (dark text 7.5:1) | |
| Primary soft (selected nav or row) | `#EEF4FF`, text `#1849A9` (7.4:1) | `#16294A`, text `#A9C8FF` (8.6:1) | |
| Critical (clinical / safety only) | `#B42318` on `#FEF3F2` (6.0:1) | `#FF9B92` on `#3A1719` (7.9:1) | |
| Warning / overdue | `#93370D` on `#FFFAEB` (7.2:1); icon `#DC6803` | `#FCCB7E` on `#33250D` (9.9:1) | |
| Success / done / normal | `#067647` on `#ECFDF3` (5.4:1) | `#6EE0A6` on `#0F2E21` (9.0:1) | |
| Info | `#1849A9` on `#EEF4FF` | `#A9C8FF` on `#16294A` | |
| AI | `#5925DC` on `#F4F3FF` (7.0:1) | `#C2B4FF` on `#241C47` (8.5:1) | AI-generated content only |
| Brand navy / teal | `#0B2545` / `#2BB3A3` | `#1B3A63` / `#2BB3A3` | logo and public site only |

**Colour rules**
1. Colour carries meaning, never decoration. KPI tiles are neutral unless a rule makes them a warning.
2. **Red = clinical severity or safety only.** Examples: critical result, ESI 1–2, allergy, life-threatening flag, blocked discharge.
3. **Overdue = amber + clock + “4 d overdue”.** Time pressure is not the same thing as clinical danger.
4. Every status has an icon and a label (already true of `StatusChip`; extend it to all badges).
5. At most one solid colour fill per row (the status), plus the one primary button per view.

### 4.2 Typography

**Font.** Inter Variable, already bundled. Use tabular numerals for all numbers (`.tabular` already exists), and use the system mono stack for MRN and codes.

| Token | Size / line | Weight | Use |
|---|---|---|---|
| `text-display` | 28/36 | 600 | Portal greeting, public pages only |
| `text-title` | 22/28 | 600 | One page title per screen |
| `text-section` | 16/24 | 600 | Section titles; card titles use 15/20 |
| `text-body` | 14/20 | 400 | Default; forms; list primary line |
| `text-table` | 13/18 | 400 | Tables, dense lists, meta lines |
| `text-label` | 12/16 | 500 | Column headers (sentence case, not uppercase), field labels, captions |
| `text-metric` | 20/28 | 600 tabular | Numbers in metric strips (not 24–30 px) |
| Portal body | 16/24 | 400 | Patient-facing text |

**Hard rules**
- No arbitrary pixel sizes in features. The codemod in §13 maps today’s values onto these tokens.
- No uppercase micro-labels except where data demands it, such as “STAT”.

### 4.3 Spacing, layout, density

| Item | Value |
|---|---|
| Spacing scale | 4 · 8 · 12 · 16 · 20 · 24 · 32 · 48 |
| Page padding | 24 px (32 px ≥ 1600 px) |
| Content max width | 1440 px (wall display unlimited) |
| Sidebar | 232 px; 64 px icon rail on 1024–1279 px or by choice; drawer under 1024 px |
| Top bar | 56 px |
| Card padding | 16 px (header 14/16) |
| Section gap | 20 px |
| Table row | 44 px comfortable / 36 px compact |
| Grid | 12 columns; Home and Command Center use 8+4 (≥ 1280) collapsing to 12 |
| Breakpoints | 640 (phone), 1024 (tablet / sidebar drawer), 1280 (laptop), 1600 (wide) |
| Radius | 6 controls · 8 cards · 12 dialogs and drawers only |
| Elevation | Cards: 1 px border, no shadow. Shadows only on menus, popovers, drawers, dialogs |

**Density setting.** “Comfortable” by default; “Compact” is chosen per user in the user menu and remembered. It defaults to Compact for ED, bed board, pharmacy, lab, radiology, billing tables and the wall display. Implement it as `data-density` on `<html>` driving CSS variables (row height, cell padding, card padding). No page code changes.

### 4.4 Shared components

| Component | Today (fact) | Recommendation |
|---|---|---|
| `Button` | 8 variants; pages use `default` for row actions | Keep variants. Add the rule “one primary per view”. Add `ai` (violet outline) and make `secondary` the default for row actions. Destructive is used only in confirm dialogs and row overflow |
| `Card` | `rounded-xl`, 20 px padding, hairline shadow | Radius 8, 16 px padding, no shadow. Add `CardHeader` with title, count and action slot; a divider under the header; a `flush` body for tables |
| `Table` | Good base; uppercase 11.5 px headers; sticky blurred head | Sentence-case 12 px labels; density variables; right-aligned numeric columns; `TR` selected state (primary-soft); built-in row overflow menu |
| Tabs | 10 implementations | Two only: **`PageTabs`** (underline, routed, for page sections) and **`Segmented`** (for filters/views inside a card). Both support counts |
| `Stat` + hand-built tiles | ≥ 5 styles | **`MetricStrip` / `Metric`**: one bordered strip with dividers; label 12, value 20 tabular, sub-line 12, optional bar; no icons; tone only via a rule |
| `Badge` / `StatusChip` | Two systems | Make `StatusChip` the only status display; `Badge` remains for neutral tags. Add tones for clinical severity vs overdue (§4.1) |
| `PageHeader` | Title + description + actions | Add `eyebrow` (department · facility · date) and a `toolbar` row for filters; descriptions limited to one line |
| `Dialog` | Centred modal | Keep for confirms and forms. Add **`Drawer`** (`SheetContent` exists) as the standard for record previews and AI |
| `EmptyState` | Large centred icon (48 px padding) | Compact inline variant for empty sections inside cards (“No results in the last 90 days”) |
| Loading | `LoadingRows` skeletons | Keep. Add a skeleton per component (metric strip, table) so layouts don’t jump |
| Notifications | Popover | Keep. Group by type and add “Open My work” |
| Clinical alerts | `AllergyStrip`, ad-hoc banners | **`ClinicalBanner`** with three tiers: inline flag (non-interruptive), banner (persistent until acknowledged), modal (only for hard stops) |
| Forms | `Field` with good aria wiring | Keep. Use one-column forms with 480–640 px measure; required asterisk plus a “required” legend; input borders at the 3:1 token |

---

## 5. Application shell proposal (recommendation)

```
BEFORE                                         AFTER
┌──────────┬───────────────────────────────┐   ┌──────────┬────────────────────────────────────────────┐
│▓▓▓▓▓▓▓▓▓▓│ Home     [Synthetic][Search…][🔔][MC]│   │ ◤W HMS Workflows│[Harborview Health · Downtown ▾] [ Search patients by name, MRN, DOB ⌘K ] [Synthetic] 🔔 MC │
│▓ U Undecl│───────────────────────────────│   │──────────┼────────────────────────────────────────────┤
│▓ [Org ▾] │                               │   │ Home     │ Doctor · Harborview Downtown · Mon Nov 23   │
│▓ ■ Home  │  Good morning, Maya           │   │ My work 15│ Good morning, Dr. Chen          [✦ Ask AI] │
│▓   My wo…│                               │   │ My visits│ Quick actions [Start next visit][Find…][…] │
│▓   …     │                               │   │ Patients │                                            │
│▓ ALL TOOL│                               │   │ Orders…  │                                            │
│▓▓▓▓▓▓▓▓▓▓│ © footer inside every page    │   │ Hospital │                                            │
└──────────┴───────────────────────────────┘   │ More     │  (footer only on Help/About and portal)    │
 dark navy sidebar, org in sidebar,             └──────────┴────────────────────────────────────────────┘
 breadcrumb only context                         light sidebar, facility in top bar, eyebrow names dept
```

- **Sidebar.** A light surface (`#FFFFFF`, right border) at 232 px.
  - Selected item: primary-soft background with primary-dark text and a semibold label.
  - Counts on My work and Messages come from the same queries as the pages.
  - Sections are “(primary)”, “Hospital”, “More”. Group labels are 12 px sentence case, not uppercase tracking.
  - “All tools” stays and opens a grouped menu (today’s behaviour).
- **Top bar (56 px)**, left to right:
  - **Facility context button** (organization · location), moved from the sidebar so it is always visible;
  - **breadcrumb** (on inner pages);
  - **search**, wide, centred, with the “name, MRN or DOB” hint;
  - **“Synthetic data”** chip (dashed amber);
  - **notifications**, then **avatar** (the name appears in the menu, not the bar).
- **Page header.**
  - An eyebrow with *Department · Facility · Date*, an H1, and a one-line description only when needed.
  - Actions on the right, with at most one primary. Filters go in the toolbar row below, never in the title row.
- **Patient context.** When a chart or encounter is open, the sticky **patient banner** sits directly under the top bar (§8).
- **Footer.** Remove it from staff work pages. Keep the copyright in Help & About, the login page, the public site and the portal footer. The copyright text itself is unchanged.
- **Density.** Comfortable and Compact (§4.3). Collapsed rail between 1024 and 1279 px.
- **Mockup:** canvas → *After: app shell + Doctor Home*.

---

## 6. Role-specific Home recommendations

**Structure kept: My priorities · Today · Quick actions.** What changes:

| Element | Change |
|---|---|
| Quick actions | Move to a compact button row under the title (frees a whole column) |
| Today | Becomes a **metric strip** plus one list, no card-in-card |
| My priorities | Becomes a **table grouped by patient or problem**: *Patient/problem · What’s needed · Due · Status · Action* |
| Ordering | Clinical severity before lateness (backend ranking tweak in `home.py`, §16 Phase B) |
| Colour | Overdue is amber |
| Zeros | Zero metrics render in tertiary colour, so the eye skips them |

| Role | Most prominent | Layout |
|---|---|---|
| **Doctor** | Today’s schedule and sign-offs blocking discharges | Left 8 cols: priorities grouped by patient (e.g. “Maya Sorensen — sign summary, approve instructions — 4 d overdue”). Right 4 cols: Today strip (appointments, arrived, to document) + Up next timeline. *Canvas: Doctor Home* |
| **Nurse** | Vitals overdue, critical results, my patients | Metric strip (patients on my units, vitals overdue, open priorities). Priorities with clinical items first (“Vitals overdue — 19 patients → Open vitals list”), then discharge tasks grouped by patient. Primary action: **Record vitals**. *Canvas: Nurse Home, dark* |
| **Front desk** | Next arrivals and anyone waiting too long | Strip (expected, arrived, waiting > 15 min, ready for checkout). Main: **Arrivals in the next 60 minutes** table with *Time · Patient (name · DOB · MRN) · Provider · Insurance status · Check in*. Quick actions: Register, Book, Check in by search |
| **Pharmacist** | Verification queue age | Strip (to verify, oldest waiting, below reorder, expiring ≤ 30 d). Main: verification queue table; side: stock alerts list. Primary: **Verify next** |
| **Hospital Admin** | Capacity and decisions escalated to me | Strip: occupancy (bar), ED (waiting · boarding), awaiting bed, discharges ordered, staffing gaps. Main: escalations grouped by problem with owner and oldest age. Side: unit capacity bars + automation health. Primary: **Open Command Center**. *Canvas: Hospital Admin Home* |
| **Super Admin** | Platform health, not clinical work | Strip: active staff, AI provider (Live/Simulated), automation health, integration status, failed sign-ins (24 h). Main: “Needs configuration” checklist (e.g. AI provider simulated, analyzer interface manual). Side: recent admin audit events. No patient data |

---

## 7. Clinical workspace recommendations

**Patient chart.** *Canvas: Patient chart.*
- **Sticky patient banner**, two lines:
  1. **FAMILY, Given** (family name in capitals, the common patient-banner convention), *sex · age · DOB · MRN*;
  2. allergies, coverage, location or encounter, and isolation or code status *only where the data exists*.
- **Allergies: never infer.**
  - An empty list shows a neutral “Allergies: none recorded — Review”.
  - A green “No known allergies” is shown only once someone documents NKA. This needs an explicit field later; it is not in the data model today.
  - Allergies present: a red outlined chip per substance, life-threatening allergies first.
- **Actions.** One primary (**Start visit**), one AI button (“Ask about this chart”), and a **More** menu for Edit and Book.
- **Tabs.** The six chart groups become `PageTabs` (underline); subsections become `Segmented`.
- **Overview layout.**
  - A full-width vitals strip, with abnormal values flagged by icon and the word “High” or “Low” (not colour only), plus a link to trends.
  - Below: *Problems and medications* (8 cols) and *Visits* (4 cols). Cards size to their content.
  - A compact “No results in the last 90 days” line instead of empty cards.

**Doctor workspace (visit / encounter)**
- **Two panes.** Note on the left (8 cols); right rail (4 cols) with tabs *Summary · Orders · AI scribe*.
- **Note status.** “Draft” versus “Signed” is made obvious (already a rule in `UI_UX_SYSTEM.md`). AI-drafted sections carry the “AI draft — needs review” chip until edited or attested.
- **Today’s schedule** stays reachable from the top-bar breadcrumb.

**Nursing**
- **Assigned patients table**, compact: *Bed · Patient · Last vitals (age) · Due · Alerts (icons with labels) · Tasks · Action*.
- **Row emphasis.** Overdue vitals get an amber clock; a critical result gets a red triangle plus the word.
- **Saved filter.** “My patients”.

**Emergency department.** Keep the board; change presentation only.
- **Fixed row height** with one visible action (the next logical step) and an overflow menu for the rest.
- **Wrapping.** The complaint gets more width; provider and nurse fit on one line with truncation and a tooltip.
- **Durations** use one formatter (“3 d 18 h” or “89 min”). Times over target get an amber clock; ESI keeps its colours with a number.
- **Defaults.** Compact density; Wall display uses large type.

**Pharmacy**
- **Layout.** Metric strip replaces the four icon tiles. The verification queue is the default tab when items are waiting.
- **Flags.** Expiry and low-stock flags get an icon and a word (“Expires in 1 day”), not orange text alone.
- **Columns.** Numbers right-aligned; units in tertiary text.
- **AI** proposals (“Draft reorder”) appear as rows with “Awaiting approval”.

**Laboratory and Radiology**
- **One queue template:** *Priority · Test/Study · Patient · Location · Ordered · Status · Action*.
- **Actions.** Outline buttons on rows; the single primary is “Collect next” or “Read next”.
- **Critical results** get a dedicated red banner with read-back acknowledgement, which already exists functionally.

**Front desk**
- **Replace the 4-column kanban** with a single **arrivals table** and a `Segmented` status filter (Expected 13 · Waiting 0 · Roomed 0 · Ready for checkout 0).
- **Buttons.** Row action “Check in” as outline; Book is the page primary.
- **Identity** is shown on one line: name · DOB (age) · sex · MRN.
- **Optional** “Board” view toggle for large screens.

**Billing and insurance**
- **Dense tables** with sticky header, right-aligned money and payer in its own column.
- **Status chip** examples: *Draft · Submitted · Denied · Needs info*.
- **Actions.** A bulk-action bar appears on selection.
- **Empty states.** Single-row pages such as Claims get a compact empty or short-list state instead of a large blank area.
- **The “simulated payer” notice** moves into the page header as a dashed info chip, not an amber warning, because it is a fact about the environment, not a problem.

---

## 8. Command Center design (recommendation)

**Principle:** *Operational overview → Issues requiring attention → Department detail.* Every number links to its records, and no new metrics are invented. *Canvas: Command Center.*

```
BEFORE (live)                                   AFTER
┌ Title  [Explain][Live][Facility][Dept]      ┐  ┌ Hospital operations · Mon Nov 23 · ● Live · updated 11:28 ┐
│        [Shift handoff][Wall display]        │  │ Command Center          [✦ Explain bottlenecks][Shift handoff][Wall] │
├──────┬──────┬──────┬──────┬──────┬──────┤     │ [All my facilities ▾] [All departments ▾]                 │
│tile  │tile  │tile● │tile● │tile  │tile● │ ×12 │ 1 · HOSPITAL STATUS  (one strip, 6 metrics)               │
├──────┴──────┴──────┴──────┴──────┴──────┤     │ Occupancy 69% ▇▇▇▁ | ED 7 (3 waiting·1 boarding) | Await bed 2 |
│ unit table                                │   │ Discharges 6 | Staffing gaps 20 | Past target 38           │
├─────────┬─────────┬─────────┬─────────┤       │ 2 · NEEDS ATTENTION  (grouped by problem, clinical first)  │
│tile pink│tile     │tile pink│tile pink│ ×8    │ ▲Clinical ED  ESI 3 waiting > 60 min      2  3 d 18 h Doctor  [Open] │
├─────────────────────────┬─────────────┤       │ ▲Clinical ED  Waiting without triage      1  3 d 17 h Nurse   [Open] │
│ Problem queue: 38 red rows │ heat table │      │ ◷Flow  Beds   Waiting for a bed           2  3 d 19 h Bed mgr [Open] │
│ …all Urgent / overdue      │ worklists  │      │ ◷Flow  Disch. Ordered, not departed       6  3 d 22 h Nurse   [Open] │
└─────────────────────────┴─────────────┘       │ 3 · DEPARTMENT DETAIL  [Capacity|Emergency 7|Pharmacy 5|Revenue 12|Equipment 4|Automation & AI] │
                                                 └ unit table with occupancy bars; automation health line    ┘
```

- **Tier 1, status.**
  - Six metrics in one strip: capacity, ED pressure, awaiting bed, discharges, staffing and issues past target.
  - Colour appears only when a configured threshold is crossed (thresholds come from existing monitor settings). Otherwise numbers stay neutral.
- **Tier 2, needs attention.**
  - Open cases grouped by *monitor kind*, which the backend already groups by kind for My work.
  - Each row shows severity category (Clinical / Flow / Revenue / Supply), area, problem, count, oldest age, owner and an action. Clinical rows sort first.
  - This replaces both the flat 38-row list and the department heat table.
- **Tier 3, department detail.**
  - `PageTabs` (Capacity, Emergency, Pharmacy & supply, Revenue, Equipment, Automation & AI), each holding the existing tables.
  - The secondary tiles today (appointments, waiting room, insurance, unsigned notes, equipment, AI activity) move into the relevant tab.
- **Fixes.** “updated 11:28 AM” without the “(in 0 seconds)” wording. Filters go in one toolbar row.
- **Wall display.** Tiers 1 and 2 only, with large type and Compact density.

---

## 9. AI interface design (recommendation)

**Principle:** AI is a quiet helper inside the workflow, not a separate app, and not a chat box on every page.

**One pattern: the AI side panel**, a right `Drawer` 480–520 px wide that keeps the record visible. *Canvas: AI assistant panel.*

1. **Header.** Agent name, a provenance chip, and a “Read-only · your permissions” chip.
2. **The question** that was asked.
3. **Answer.** Short paragraphs at 14/22.
4. **Sources.** Links to the records used (case, checklist, chart section).
5. **What it looked at.** Collapsed; tool steps in plain language (“list open cases · get discharge status”).
6. **Proposed actions.** Each item shows a status chip (“Awaiting approval”) and a link to review in My work. Approve/Reject appears inline only where the user has that permission.
7. **Footer.** “AI output can be incomplete or wrong… not saved to the chart.”

**Provenance vocabulary.** Chips with icon and label, used everywhere (chart, scribe, document intelligence, receptionist, Command Center):

| State | Chip | Meaning |
|---|---|---|
| Live AI | violet ✦ “Live AI · model” | Real model call |
| Simulated | grey dashed ⚗ “Simulated · rule-based” | No model; deterministic summary |
| AI draft | violet dashed ✎ “AI draft — needs review” | Generated text not yet accepted by a person |
| Rule alert | grey ⚙ “Rule alert” | Deterministic monitor, not AI |
| Pending approval | amber ⧗ “Awaiting approval” | Proposal waiting for a human |
| Completed | green ✓ “Approved by J. Rivera” / “Done” | Human-approved action executed |

**Screen-specific changes**
- **Agent Studio.**
  - Cards become a table: *Agent · Purpose · Trigger · Runs (30 d) · Failures · Status · Run*.
  - Toggles and configuration move into the row drawer.
  - Cost shows as “$0.00”.
  - Tool names are written in plain language.
  - “Run” is outline.
  - The provider state appears as a page-level banner (“AI provider: Simulated — answers are rule-based”).
- **Ask AI buttons.** Violet outline, labelled with the question (“Ask about this chart”), opening the panel.
- **Medical Scribe and Doctor Assistant** use the same panel inside the encounter right rail.
- **Document Intelligence.** Show extracted fields next to the document, each with confidence and an “AI draft” chip until confirmed.
- **AI Receptionist and Realtime Voice.** Use the same conversation layout as Messages: transcript on the left, actions and approvals on the right. Add a persistent “Simulated” or “Live” chip and a visible microphone state with text label.
- **AI Settings and Governance.** Standard settings form layout (§4.4). Keys are shown as masked hints only (unchanged behaviour); run logs use the shared table.

---

## 10. Patient portal design (recommendation)

*Canvas: Patient portal.*

- **Navigation.** Five sections:
  - **Home**;
  - **Appointments**;
  - **Messages**;
  - **My health** (results, visit summaries, records, documents, hospital stays);
  - **Billing & insurance**.

  One bell. On phones, a bottom tab bar.
- **Type and targets.** 16/24 body, 44 px touch targets, plain words (“Test results your doctor has released”).
- **Home**, in this order:
  - greeting with “You have 2 things to do”;
  - a **To do** list *deduplicated across visits* (“Confirm your insurance — needed for your next 3 visits”);
  - a **Next visit** card with pre-visit form and reschedule;
  - **Coming up** list;
  - three shortcuts.
- **Brand.** The hospital’s name leads; “powered by HMS Workflows” appears in small text. Same palette, softer radius (12) and more white space than the staff app.
- **Remove** the duplicated insurance banner; the to-do list holds it.
- **Copyright footer** stays unchanged.

---

## 11. Light and dark mode standards (recommendation)

| Standard | Light | Dark |
|---|---|---|
| Surface steps | page `#F5F7FA` → card `#FFFFFF` → subtle `#F8FAFC` | page `#090E18` → card `#162033` → hover `#1E2A40` (step up, don’t invert) |
| Separation | borders `#E4E7EC`; no shadows on cards | borders `#33445F` carry separation; no glow |
| Text | 16:1 / 7.7:1 / 5.0:1 minimum | 13:1 / 6.7:1 minimum |
| Status text on tints | ≥ 5.4:1 (measured, Palette A) | ≥ 7.9:1 (measured) |
| Inputs | border 3.5:1 | border 4.0:1 |
| Focus | 2 px primary ring + 2 px offset (exists) on every interactive element, including table rows | same, ring `#6EA4FF` |
| Tables | zebra off; hover `#F2F4F7`; selected primary-soft | hover `#1E2A40`; selected `#16294A` |
| Images / brand | navy tile | lighter navy tile `#1B3A63` |

**WCAG 2.2 AA items to verify during implementation**
- 1.4.3 contrast (tokens above);
- 1.4.11 non-text contrast (inputs, focus);
- 1.4.1 use of colour (flags carry icon and word);
- 2.4.11 focus not obscured (sticky banner and top bar must not cover focused rows: use `scroll-margin-top`);
- 2.5.8 target size ≥ 24 px (staff) / 44 px (portal);
- 4.1.2 tabs exposed as tabs.

The existing `prefers-reduced-motion` handling stays.

---

## 12. Before-and-after concepts

The visual versions are on the canvas: https://claude.ai/artifact/Mw2LzQgaNJLq9pbE6Zu4QA

| # | Screen | Before (live, observed) | After (concept) | Canvas board |
|---|---|---|---|---|
| 1 | App shell | Dark sidebar, gradient tile, facility in sidebar, search 256 px, footer on every page | Light sidebar with counts; facility switcher in top bar; wide patient search; eyebrow names the department; footer removed from work pages | *After: app shell + Doctor Home* |
| 2 | Doctor Home | 5 red “Urgent” rows; quick-action column; 4 boxed zeros | Priorities grouped by patient with amber “4 d overdue”; quick-action row; Today strip + Up next | same |
| 3 | Hospital Admin Home | 12 boxes and an all-red queue | Hospital strip (6 metrics) + escalations grouped by problem + unit capacity | *After: Hospital Admin Home* |
| 4 | Patient chart | Green “No known allergies” from empty list; equal-height half-empty cards; 4 competing buttons | Sticky two-line banner; “Allergies: none recorded — Review”; vitals strip with “High” flag; content-sized cards; one primary | *After: Patient chart* |
| 5 | My work | Inline meta text; 3 tab styles | Underline tabs with counts; segmented filter; columns (Problem · Patient · Owner · Due · Status); groups expand inline | *After: My work* |
| 6 | Command Center | 20 equal tiles then a flat red list | Three tiers: status strip → grouped attention table → department tabs | *After: Command Center* |
| 7 | AI assistant | Centred modal over the work | Right drawer with provenance, sources, steps, approvals, disclaimer | *After: AI assistant panel* |
| 8 | Patient portal | 9 tabs, 2 bells, 6 repeated “Do it now” links | 5 sections, deduplicated To do, Next visit card, 16 px type | *After: Patient portal* |
| + | Dark mode | Card vs page 1.06:1 | Stepped surfaces, border separation, re-tuned status colours | *After: Nurse Home, dark mode* |

**Concise wireframes**

```
DOCTOR HOME (after)
Doctor · Harborview Downtown · Monday, November 23
Good morning, Dr. Chen                                           [✦ Summarize my discharge tasks]
Quick actions  [Start next visit] [Find a patient] [Orders & results] [Emergency board]
┌ My priorities · 15 open · grouped by patient ─────────── Open My work ┐ ┌ Today ─────────── Schedule ┐
│ Patient          What's needed                 Due          Status       │ │ Appointments 6 │ Arrived 0 │ … │
│ Maya Sorensen    Sign summary · approve instr. ◷ 4 d overdue 2 tasks [Review]│ │ 7:40  Owen Thibault  Scheduled │
│ Isabella Zielin… Sign summary · approve instr. ◷ 4 d overdue 2 tasks [Review]│ │ 10:00 Mateo Fairbanks Confirmed│
│ Ethan Eastwood   Sign summary                  ◷ 4 d overdue 1 task  [Review]│ │ 1:20  Liam Fairbanks  Scheduled│
└ Red is reserved for critical results — none open for you right now ─────┘ └────────────────────────────┘

PATIENT CHART (after)
┌ TW  WHITLOCK, Tomas   Male · 57 y · DOB 01/09/1969 · MRN UD100001        [✦ Ask about this chart][More ▾][Start visit] ┐
│     (i) Allergies: none recorded  Review allergies · Federal Senior Plan · Outpatient · Harborview Downtown            │
└──────────────────────────────────────────────────────────────────────────────────────────────────────── (sticky) ┘
 Overview | Clinical | Visits | Orders & results | Care journey | Documents & details
┌ Latest vitals · Sep 25, 2026 2:58 PM ───────────────────────────────────────────── Trends ┐
│ BP 128/76 │ HR 80 │ RR 14 │ Temp 98.1 °F │ SpO₂ 95% │ Wt 203 lb │ BMI 39.3 ▲High │ Pain 3/10 │
└──────────────────────────────────────────────────────────────────────────────────────────┘
┌ Problems and medications ─────────────── Clinical ┐ ┌ Visits ───────────── All visits ┐
│ Problem     Generalized anxiety disorder   F41.1  │ │ Last: Sep 25 · Cough… · J06.9   │
│ Medication  Sertraline 50 mg · daily       active │ │ Nov 24 7:20 Annual physical  ✓  │
│ Results     No results in the last 90 days        │ │ Nov 25 12:00 Sick visit         │
└───────────────────────────────────────────────────┘ └─────────────────────────────────┘

MY WORK (after)
My work — Everything waiting on you or your team. Most urgent first.
Cases 5 | Tasks 12 | Approvals 0
[All 5 | Emergency 1 | Discharge 4]  [Filter by patient or case #]          Sorted by severity, then overdue
  Problem                         Patient          Owner         Due               Status
▲ Waiting without triage #1038    Ethan Castillo   Nurse / MA    ◷ 3 d 17 h overdue Escalated → Clinic Admin [Triage]
▾ Discharge ordered, not departed · 4 patients                    ◷ oldest 3 d 20 h  4 not started
    #1006 …                       Kenji Nakamura   Nurse / MA    3 d overdue        Not started   [Open]
    #1007 …                       Felix Goldberg   Nurse / MA    4 d overdue        Not started   [Open]
    Show 2 more patients

AI PANEL (after) — drawer on the right of the discharge checklist
┌ ✦ Discharge Coordination                                    ✕ ┐
│ [✦ Live AI · gpt-4.1-mini] [Read-only · your permissions]      │
│ You asked: "What is blocking this discharge…?"                 │
│ ANSWER   …                                                     │
│ SOURCES  Discharge checklist — Maya Sorensen ·  Open tasks     │
│ ▸ What it looked at (3 steps)                                  │
│ ┌ ⧗ Awaiting approval  Proposed: reminder task for Dr. Chen ┐  │
│ └ Nothing changes until a person approves it. [Review]       ┘  │
│ AI output can be incomplete or wrong…                          │
└────────────────────────────────────────────────────────────────┘

PATIENT PORTAL (after)
[W] Harborview Health · Patient portal       Home | Appointments | Messages | My health | Billing & insurance  🔔 EL
Hello, Elena — You have 2 things to do before your next visit.                       [Book an appointment]
┌ To do ───────────────────────────────────────────────┐ ┌ Next visit ─────────────────────┐
│ 🛡 Confirm your insurance — needed for next 3 visits  [Confirm insurance] │ │ Tue, Nov 24 · 6:00 AM         │
│ ☑ Pre-visit questionnaires — 3 visits                [Start]             │ │ Follow-up with Maya Chen, MD  │
└──────────────────────────────────────────────────────┘ └ [Pre-visit form] [Reschedule]  ┘
```

The mockups use the synthetic demo data seen on the live site. Where a value was not visible on screen, the mockup omits it rather than inventing one; the AI answer text is labelled illustrative.

---

## 13. Shared component strategy (how to implement efficiently)

**Fact.** The app already funnels most of its visuals through a small set of files:
- `index.css` (tokens);
- `components/ui/*` (10 primitives);
- `components/common/index.tsx` (PageHeader, Stat, EmptyState, KeyValue, badges);
- `Status.tsx`;
- `AppShell.tsx`.

**Strategy:** fix the foundation, add the four missing primitives, then migrate pages mechanically. Do not restyle 50 pages by hand.

**Step 1: tokens (`frontend/src/index.css`).**
- Replace the OKLCH values with the Palette A light and dark values (keep the same variable names, so every `bg-primary`, `text-muted-foreground` and similar class updates automatically).
- Add `--warning-foreground`, `--success-foreground` and `--critical-*` text tokens with the measured contrast.
- Add the `--text-*` type scale in `@theme` (Tailwind v4 creates `text-title`, `text-section`, `text-body`, `text-table`, `text-label`, `text-metric` utilities).
- Add `data-density` variables.
- Change sidebar tokens to light values.

**Step 2: codemod arbitrary sizes.** A script maps the arbitrary sizes onto the scale (`text-[13px]`, `text-[13.5px]`, `text-[12.5px]` → `text-table` or `text-body` by context; `text-[11px]`, `text-[11.5px]` → `text-label`; `text-[15px]` → `text-section`). It is reviewable as one diff and touches 627 class usages across 70 files in `features/` and `components/` without changing layout logic.

**Step 3: primitives.**

| File | Change |
|---|---|
| `components/ui/card.tsx` | Radius 8, 16 px, no shadow, `CardHeader` count + action slot, `flush` variant |
| `components/ui/table.tsx` | Sentence-case labels, density vars, numeric alignment helper, selected row |
| `components/ui/tabs.tsx` | Add `PageTabs` (underline) and `Segmented`; restyle `TabsList` to `Segmented` look so the 9 existing users update automatically |
| `components/ui/button.tsx` | `ai` variant; document “one primary” rule; `xs` size retained for dense rows |
| `components/ui/badge.tsx` | New tones; contrast-safe text tokens |
| `components/ui/dialog.tsx` | Standard `Drawer` sizes (md 480, lg 640) on the existing `SheetContent` |
| `components/common/index.tsx` | `PageHeader` eyebrow and toolbar; **`MetricStrip`/`Metric`** replacing `Stat`; compact `EmptyState` |
| `components/common/Status.tsx` | Separate `overdue` (amber clock) from `urgent/critical` (red); add provenance chips (`AIProvenance`) |
| New `components/common/PatientBanner.tsx` | Extracted from `PatientChart.tsx` header; used by chart, encounter, inpatient detail, ED drawer |
| `components/layout/AppShell.tsx` | Light sidebar, `Brand` uses the new mark and `PRODUCT_NAME`, facility button in top bar, wider search, footer removed from work routes, density toggle in user menu |

**Step 4: page migrations.** Mostly replace hand-built tiles and tabs with the new primitives:
- `RoleHome.tsx`, `CommandCenter.tsx`, `WorklistPage.tsx` + `ops.tsx`, `PatientChart.tsx`, `FrontDesk.tsx`, `EdBoard.tsx`, `BedBoard.tsx`, `PharmacyPage.tsx`, `LabPage.tsx`, `RadiologyPage.tsx`, `RevenuePage.tsx`, `BillingPage.tsx`, `InsuranceGuardian.tsx`;
- `AgentStudio.tsx`, `AIPages.tsx`, `AskAI.tsx` (modal → drawer), `MonitorsPage.tsx` (collapsed rule rows + role select);
- `PortalHome.tsx`, `SchedulePage.tsx`, `AnalyticsPage.tsx`, `DocumentsPage.tsx`, `AISettingsPage.tsx`.

**Step 5: branding.** Driven by constants.
- Set `PRODUCT_NAME = "HMS Workflows"` and add `PRODUCT_TAGLINE` in `lib/legal.ts`.
- Replace hard-coded names in:
  - `AppShell.tsx` (`Brand`);
  - `index.html` (`<title>`);
  - `public/favicon.svg`;
  - `features/auth/LoginForm.tsx` and `AuthPages.tsx`;
  - `features/public/*`;
  - `features/help/content.ts` + `HelpPage.tsx`;
  - `features/account`;
  - backend strings that mention the product. There are 9 files: `main.py`, `seed.py`, `core/config.py`, `models/radiology.py`, `integrations/fhir.py`, `integrations/adapters.py`, `ai/scribe.py`, `api/routers/auth.py` and `api/routers/admin.py`. Review each; some are identifiers or system URIs that should *not* change, such as FHIR system names already stored in data.
- **Name the assistant consistently.** Today: “Undeclared AI”. Proposed: “HMS Workflows AI” in marketing only; inside the app, call assistants by function (“Discharge Coordination”).
- **The hero image** (`public/background.png`, with a glowing cross) should be replaced with a neutral building or abstract route image.
- **Preserve** the copyright notice `© 2026 Sidra Riaz Awan. All rights reserved.` (`COPYRIGHT_NOTICE`), unchanged.

**Dependencies.** None new. Tailwind v4, Radix, lucide and Inter are all already present.

---

## 14. Phased implementation roadmap

**Recommended order:** A → B (Home, My work, chart first) → C (Command Center, AI) → D. Phase A is the highest-leverage step: it changes every screen and de-risks the rest.

### Phase A — Brand and visual foundation
| | |
|---|---|
| **Problem** | 32 font sizes, colour without meaning, template shell, low-contrast chips, flat dark mode, three brand spellings |
| **Solution** | Palette A tokens (light and dark), type scale and codemod, density variables, restyled primitives (Card, Table, Tabs/Segmented/PageTabs, Badge, Button `ai`), `MetricStrip`, status split (overdue ≠ critical), provenance chips, light shell, HMS Workflows brand via constants |
| **Screens affected** | All |
| **Files** | `index.css`, `components/ui/*`, `components/common/index.tsx`, `Status.tsx`, `AppShell.tsx`, `nav.ts`, `lib/legal.ts`, `index.html`, `public/favicon.svg`, `LoginForm.tsx`, `features/public/*`, `help/content.ts` |
| **Visual impact** | Very high — every screen becomes calmer, consistent and less red |
| **Risk** | Low–medium: class-name and token changes only. Risk is in E2E selectors that match text such as “Urgent” or styles, and in the brand rename touching help and public text |
| **Complexity** | Medium (1 codemod + about 15 files) |
| **Minimal testing** | `npm run build` (typecheck); visual screenshot sweep (the capture script used for this audit) in light, dark, 1280 and 390; contrast check of tokens; update E2E text matchers for renamed labels; backend tests untouched |

### Phase B — Core hospital workspaces
| | |
|---|---|
| **Problem** | Home card-in-card and all-red priorities; My work without columns; chart allergy wording and empty cards; front-desk kanban; ED row ragging; inconsistent queues |
| **Solution** | Home layouts per role (§6) using the strip and grouped priorities table; small backend ranking change in `home.py` (severity before lateness; group by patient for tasks); My work columns and groups; `PatientBanner` + overview layout + allergy wording; front-desk arrivals table; ED fixed rows + one formatter; shared queue template for lab, radiology, pharmacy verification and claims |
| **Screens** | Home (11 roles), My work, Patient chart, Encounter, Nursing, ED, Front desk, Schedule, Pharmacy, Lab, Radiology, Claims, Billing, Insurance Guardian |
| **Files** | `RoleHome.tsx`, `WorklistPage.tsx`, `ops.tsx`, `PatientChart.tsx`, `EncounterPage.tsx`, `InpatientPages.tsx`, `EdBoard.tsx`, `FrontDesk.tsx`, `SchedulePage.tsx`, `PharmacyPage.tsx`, `LabPage.tsx`, `RadiologyPage.tsx`, `RevenuePage.tsx`, `BillingPage.tsx`, `InsuranceGuardian.tsx`, `backend/app/api/routers/home.py` (+ `test_home.py`) |
| **Visual impact** | High — the screens people use all day |
| **Risk** | Medium. Layout changes on clinical screens need care for patient identity display and allergy semantics; the Home ranking change needs a test |
| **Complexity** | Medium–high (about 15 page files) |
| **Minimal testing** | Backend `test_home.py` (ranking); E2E: `clinical_flow`, `adt_flow`, `ed_flow`, `lab_flow`, `pharmacy_flow`, `radiology_flow`, `billing_flow`, `insurance_guardian_flow` (selectors); screenshot sweep per role |

### Phase C — Advanced experiences
| | |
|---|---|
| **Problem** | Command Center tile wall; AI as modal and cards; Monitors 4,900 px of forms; portal with 9 tabs; Super Admin Home empty |
| **Solution** | Three-tier Command Center; AI drawer and provenance vocabulary everywhere; Agent Studio as table + drawer; Monitors as collapsed rows with role select; Realtime Voice and Receptionist transcript layout; portal with 5 sections, deduplicated To do and 16 px type; Super Admin platform-health Home; remaining admin screens on shared table and form layouts |
| **Screens** | Command Center, Agent Studio, AI assistants, AI settings, AI governance, Scribe, Document review, Receptionist, Monitors, Admin pages, Portal (all tabs), Video visit |
| **Files** | `CommandCenter.tsx`, `AskAI.tsx`, `AgentStudio.tsx`, `AIPages.tsx`, `AISettingsPage.tsx`, `ScribePanel.tsx`, `DocumentsPage.tsx` / review, `MonitorsPage.tsx`, `features/admin/*`, `PortalHome.tsx`, `VideoVisit.tsx`; backend: none required. Command Center grouping can be done client-side from `/cases`; an optional server grouping endpoint is a later optimisation |
| **Visual impact** | High for admins, demos and patients |
| **Risk** | Medium. The portal restructure changes URLs: keep old routes as redirects. AI drawer must keep the approval flow intact |
| **Complexity** | High |
| **Minimal testing** | E2E: `command_center_flow`, `ai_flow`, `scribe_flow`, `documents_flow`, `portal_telehealth_flow`, `help_flow`; `deploy_smoke` on staging |

### Phase D — Final visual consistency
| | |
|---|---|
| **Problem** | Leftover one-off styles, responsive edge cases, accessibility verification, loading and empty states |
| **Solution** | Lint rule or CI grep that fails on new `text-[Npx]`, raw palette classes in the staff app and `bg-primary` on row actions; responsive pass at 1024, 1280 and 390; WCAG 2.2 AA checklist (§11) with axe on key pages; skeletons per component; compact empty states; final alignment review |
| **Screens** | All |
| **Files** | `eslint` / CI config, page files flagged by the grep |
| **Visual impact** | Medium (polish) but prevents regression |
| **Risk** | Low |
| **Complexity** | Low–medium |
| **Minimal testing** | axe run on 10 key routes; screenshot sweep; full E2E once |

---

## 15. Top 15 highest-impact changes (ranked)

1. **Separate “overdue” from “critical”.**
   - *Today:* every overdue item is a solid red “Urgent” pill, so most of Home, My work and Command Center is red.
   - *Should be:* overdue is an amber chip with a clock and “4 d overdue”; red only for clinical severity or safety.
   - *Why:* restores the meaning of red, which is essential for alert fatigue and patient safety.
   - *How:* change the `toWorkStatus` mapping and add a `critical` tone; Home ranks severity first.
   - *Changes:* `Status.tsx`, `ui/badge.tsx`, `ops.tsx`, `RoleHome.tsx`, `home.py`.
2. **One type scale and a codemod.**
   - *Today:* 32 sizes and jittery hierarchy.
   - *Should be:* 7 named sizes.
   - *Why:* the single biggest “polished vs unfinished” signal.
   - *How:* `@theme` `--text-*`, plus a scripted replacement of the 627 arbitrary-size classes.
   - *Changes:* `index.css`, all feature files (mechanical).
3. **Light, quiet app shell.**
   - *Today:* dark navy template sidebar and gradient tile; facility hidden in the sidebar.
   - *Should be:* light sidebar with counts, facility in the top bar, wide search, eyebrow context.
   - *Why:* the shell is on every screen; it sets the product’s character.
   - *How:* sidebar tokens plus `AppShell.tsx` layout.
   - *Changes:* `index.css`, `AppShell.tsx`.
4. **`MetricStrip` replacing tiles.**
   - *Today:* at least 5 tile styles, oversized numbers, card-in-card.
   - *Should be:* one bordered strip with dividers, 20 px tabular values, neutral unless a rule fires.
   - *Why:* removes most visual noise on Home, ED, beds, pharmacy and Command Center.
   - *How:* new component; replace `Stat` and hand-built tiles.
   - *Changes:* `components/common/index.tsx`, `RoleHome.tsx`, `EdBoard.tsx`, `BedBoard.tsx`, `PharmacyPage.tsx`, `BillingPage.tsx`, `CommandCenter.tsx`.
5. **Two tab styles only.**
   - *Today:* 10 implementations.
   - *Should be:* underline `PageTabs` for sections, `Segmented` for filters.
   - *Why:* consistency people feel immediately.
   - *How:* add both, restyle `TabsList`, migrate the 9 hand-built ones.
   - *Changes:* `ui/tabs.tsx` + 9 files.
6. **One primary button per view.**
   - *Today:* 14, 17 and 22 primaries on some pages.
   - *Should be:* row actions outline or ghost; one page primary.
   - *Why:* makes the next action obvious.
   - *How:* change row-action variants; add a CI grep in Phase D.
   - *Changes:* `FrontDesk.tsx`, `LabPage.tsx`, `RadiologyPage.tsx`, `AgentStudio.tsx`, `MonitorsPage.tsx`, `RevenuePage.tsx`.
7. **Patient banner and allergy wording.**
   - *Today:* an empty allergy list shows a green “No known allergies”; no sticky banner pattern shared across chart and encounter.
   - *Should be:* sticky two-line banner; “Allergies: none recorded — Review”; red chips for real allergies.
   - *Why:* patient safety and wrong-patient prevention.
   - *How:* extract `PatientBanner`; change the empty state. Record NKA explicitly later (backend field; separate decision).
   - *Changes:* `PatientChart.tsx`, `EncounterPage.tsx`, `InpatientPages.tsx`.
8. **Command Center in three tiers.**
   - *Today:* 20 equal tiles before any issue.
   - *Should be:* status strip, then grouped attention table, then department tabs.
   - *Why:* administrators understand the hospital in one glance and know what to act on.
   - *How:* rebuild with `MetricStrip`, the grouped table and `PageTabs`.
   - *Changes:* `CommandCenter.tsx`.
9. **Grouped priorities table on Home.**
   - *Today:* five near-identical red rows repeating the patient name and “Owner: Doctor”.
   - *Should be:* grouped by patient or problem, with columns.
   - *Why:* readable at a glance; shorter on laptops and phones.
   - *How:* group client-side (`toWorkStatus` + grouping like `groupCases`).
   - *Changes:* `RoleHome.tsx`.
10. **Contrast-safe status and dark-mode tokens.**
    - *Today:* 3.4–3.6:1 chips; dark card vs page 1.06:1.
    - *Should be:* ≥ 5.4:1 light, ≥ 7.9:1 dark; stepped dark surfaces with border separation.
    - *Why:* WCAG 2.2 AA; long-shift comfort.
    - *How:* token values in §4.1.
    - *Changes:* `index.css`, `ui/badge.tsx`.
11. **AI side panel and provenance chips.**
    - *Today:* centred modal; labels vary by page.
    - *Should be:* drawer with sources, steps and approvals; six provenance states everywhere.
    - *Why:* trust, and clear separation of AI from rules from human decisions.
    - *How:* `AskAI.tsx` → `Drawer`; `AIProvenance` in `Status.tsx`.
    - *Changes:* `AskAI.tsx`, `ScribePanel.tsx`, `AIPages.tsx`, `AgentStudio.tsx`, document review.
12. **Front desk arrivals table.**
    - *Today:* a kanban with 3 empty columns and 14 primaries.
    - *Should be:* one arrivals table, a segmented status filter, outline check-in.
    - *Why:* the receptionist sees the next patient instantly.
    - *How:* rebuild `FrontDesk.tsx` around `Table` and `Segmented`; keep the board as an optional view.
    - *Changes:* `FrontDesk.tsx`.
13. **Table standard and density.**
    - *Today:* uppercase 11.5 px heads; uneven row heights; no compact mode.
    - *Should be:* sentence-case 12 px heads, 44/36 px rows, numeric alignment, one action plus overflow.
    - *Why:* data-dense departments (ED, pharmacy, billing) read faster.
    - *How:* `ui/table.tsx` plus the `data-density` toggle.
    - *Changes:* `table.tsx`, `AppShell.tsx` (toggle), `EdBoard.tsx`.
14. **Portal simplification.**
    - *Today:* 9 tabs, 2 bells, repeated to-dos, 14 px text.
    - *Should be:* 5 sections, deduplicated To do, Next visit card, 16 px type and 44 px targets.
    - *Why:* patients of all ages on phones.
    - *How:* restructure `PortalHome.tsx` navigation and keep old URLs as redirects.
    - *Changes:* `PortalHome.tsx`.
15. **One brand: HMS Workflows.**
    - *Today:* “Undeclared”, “Undeclared HMS”, “Sign in to Undeclared”; gradient “U” tile; hero image with a cross.
    - *Should be:* the route-W mark and wordmark everywhere via `PRODUCT_NAME`, with tagline only on public, login and About.
    - *Why:* a coherent, serious product identity.
    - *How:* constants plus the files listed in §13 step 5.
    - *Changes:* `lib/legal.ts`, `AppShell.tsx`, `index.html`, `favicon.svg`, `LoginForm.tsx`, `features/public/*`, help content.

---

## 16. Recommended final visual direction

**HMS Workflows should look like a calm clinical document, not a dashboard.**

- **Look.**
  - A light work surface and a light sidebar.
  - One confident blue for actions.
  - Inter at seven sizes.
  - Tables and metric strips instead of tile walls.
  - Red reserved for clinical danger.
  - Violet for AI, with its provenance always labelled.
- **Each role’s Home answers three questions in under five seconds:** *What needs me? How is today going? Where do I go next?*
- **The chart always shows who the patient is and what could hurt them.**
- **Each department sees the same kind of queue.**
- **The Command Center** reads from status, to problems, to detail.
- **The portal** speaks plain language at a comfortable size.

**Decisions needed before implementation**

1. Approve **Palette A** (or choose B or C).
2. Approve the **light sidebar** (alternative: keep a navy sidebar with the new tokens; less change, less improvement).
3. Approve the **route-W mark** direction (a designer can refine the drawing).
4. Approve **“overdue = amber, critical = red”** and the Home ranking change (severity before lateness).
5. Approve the allergy wording change now, and decide later whether to add an explicit “No known allergies” documentation field.
6. Approve the portal restructure to 5 sections, with redirects for old links.

After approval, start with Phase A on a branch, check it with the screenshot sweep across all roles in light, dark, laptop and phone, then proceed to Phase B.

---

### Appendix — research basis (recommendation context)

The patterns below are drawn from publicly described conventions of established hospital systems and published usability guidance. They were **not** taken from proprietary screens, and no vendor UI was copied or inspected in this audit:

- **Persistent patient banner** with identity, allergies and alerts on every clinical screen. This is the common pattern in Epic’s patient header, Oracle Health (Cerner) PowerChart’s banner bar, and NHS Common User Interface guidance (family name in capitals, DOB, sex, identifier, allergy status). It prevents wrong-patient errors.
- **Tracking or status boards** for ED and beds (Epic ASAP, MEDITECH Expanse status boards and similar):
  - one row per patient, fixed row height;
  - icon columns with legends;
  - time since arrival;
  - colour only for exceptions.
- **Unified work queue / in-basket.** A single inbox grouped by type with counts in the navigation (the Epic In Basket concept), which matches HMS Workflows’ My work.
- **Role-based workspaces.** Each role lands in a workspace built around its tasks, with less-used activities one level deeper. This matches the current primary nav plus “All tools”.
- **Tiered clinical decision support.** Non-interruptive flags by default, interruptive alerts only for hard stops. This reflects alert-fatigue findings in AHRQ and ONC SAFER guidance, and is why red must be scarce.
- **Dense, scannable tables** with right-aligned numbers and sticky headers for pharmacy, lab and billing work.

These inform the principles above. The proposed visual identity (palette, mark, layout) is original to HMS Workflows.
