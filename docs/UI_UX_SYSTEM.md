# UI / UX system

## Visual direction — HMS Workflows (Harbor Blue)

Approved redesign: `docs/HMS_WORKFLOWS_VISUAL_REDESIGN_PLAN.md`. Calm, clinical, dense but readable: light sidebar, light work surface,
one blue (`#1D5BD6`) for actions, colour reserved for meaning. Brand: **HMS Workflows** — continuous-route "W" mark
(`components/common/Logo.tsx`), tagline *Your Entire Hospital. Working as One.* (`lib/legal.ts`).

**Type scale (7 sizes, Inter):** `text-label` 12/16 · `text-table` 13/18 · `text-body` 14/20 · `text-section` 16/24 · `text-metric` 20/28 ·
`text-title` 22/28 · `text-display` 28/36. Arbitrary `text-[Npx]` is blocked in CI. The patient portal scales the same tokens up
(`.portal-scale`, 16 px body).

**Status colours:** red = clinical danger / failure (`Urgent`, `Blocked`, `Failed`), amber = overdue / escalated / needs approval,
green = done, blue = active workflow, neutral = waiting. Overdue work is never red. Every status has an icon and a label
(`components/common/Status.tsx`). AI provenance: `ProvenanceChip` — Live AI · Simulated · AI draft · Rule alert · Awaiting approval · Done.

**Density:** Comfortable (default) or Compact from the user menu (`<html data-density="compact">`), driving table row and card padding.

**Patient safety wording:** an empty allergy list reads "Allergies: none recorded" — never "No known allergies" unless documented.

## Tokens (`frontend/src/index.css`)

CSS variables in OKLCH on `:root` and `.dark`, exposed to Tailwind via `@theme inline`:

| Token | Use |
|---|---|
| `background`, `card`, `popover`, `muted`, `border`, `input` | surfaces |
| `foreground`, `muted-foreground` | text |
| `primary`, `accent` | actions, selection |
| `success`, `warning`, `destructive` (+ `-soft`) | status |
| `ai`, `ai-soft` | anything AI-generated |
| `sidebar*` | navigation chrome |

Dark mode: `.dark` class on `<html>`, toggled from the user menu (light / dark / system), applied before first paint in `index.html`.

## Components

Primitives (`components/ui`): `Button` (variants default, secondary, outline, ghost, soft, destructive, success, link; `loading` prop), `Input`, `Textarea`, `NativeSelect`, `Label`, `Field` (label + error + hint with aria wiring), `Card*`, `Badge`, `Dialog`/`SheetContent` (drawer), `DropdownMenu*`, `Popover*`, `Tooltip`, `Tabs*`, `Table*`, `Checkbox`, `Switch`, `Avatar`, `Skeleton`, `Kbd`.

Patterns (`components/common`): `PageHeader`, `EmptyState`, `ErrorState`, `LoadingRows`, `Stat`, `KeyValue`, `AppointmentStatusBadge`, `AIBadge`, `SimulatedBadge`, `useConfirm()` (incl. required-reason), `useUnsavedChanges()`, `FormDialog` (spec-driven), `Icd10Picker`.

Rule: new screens compose these; don't create look-alike variants.

## Clinical usability rules (implemented)

- **Patient identity** is always shown as *name · sex · DOB (age) · MRN* in search results, pickers, queues and banners to prevent wrong-patient selection.
- **Persistent banner** on charts and encounters (sticky) with allergies; severity colored, life-threatening outlined. Users without clinical access see "clinical access required" instead of a misleading "no allergies".
- **Draft vs signed** notes look different (editable fields + Draft badge vs read-only text + lock + signer/time). Addenda are visually separate.
- **AI content** is always marked with the violet AI badge; signing such notes requires an explicit attestation checkbox.
- **Confirmations** for destructive or irreversible actions (cancel, no-show, entered-in-error, sign).
- **Unsaved changes** guard on registration and the note editor (route blocker + `beforeunload`).
- **Keyboard**: ⌘K or `/` opens patient search; ⌘S saves the note; tables rows are focusable and open with Enter.
- **Simulated integrations** carry a `Simulated` badge; the header shows "Synthetic data" when the org is flagged synthetic.
- Abnormal vitals are shown in red with clinic-standard reference ranges.

## Layout

App shell: collapsible sidebar (role-filtered nav, org/clinic switcher), sticky top bar (breadcrumbs, synthetic-data flag, search, notifications, user menu). On < 1024px the sidebar becomes a drawer. Content max-width 1440px.

## Accessibility

Radix primitives for focus management; visible focus rings; `aria-invalid`/`aria-describedby` on fields; status not conveyed by color alone (labels + dots); `prefers-reduced-motion` honored.
