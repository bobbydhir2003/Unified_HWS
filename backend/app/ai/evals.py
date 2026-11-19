"""AI evaluation suites (C7). Run against SYNTHETIC labeled samples only — no patient data leaves the system.

- document_extraction_v1: the active document provider extracts fields from synthetic documents; each field is scored
  against the label (exact match after normalization; "absent" fields must come back null — no invented values).
- tool_gate_v1: the agent tool gate must refuse tools outside an agent's allow-list, tools the user lacks permission for,
  and malformed arguments. Read-only probes; never creates proposals.

Scores describe these samples only; they are not clinical validation."""

from __future__ import annotations

import time

from app.models import AIEvalRun

FIELDS = ("doc_type", "first_name", "last_name", "date_of_birth", "mrn", "document_date", "member_id")

# Synthetic documents (fictional people, fictional facilities). `None` = not present on the document → must be null.
DOC_SAMPLES: list[dict] = [
    {"id": "lab-01", "text": "LABORATORY REPORT\nPatient Name: Rivera, Ana\nDOB: 03/14/1980\nMRN: UD900101\nCollected: 2026-10-02\n"
                             "Hemoglobin: 10.9 g/dL (L) [ref 12.0-15.5]\nGlucose: 98 mg/dL (N) [ref 70-99]\n",
     "expect": {"doc_type": "lab_result", "first_name": "Ana", "last_name": "Rivera", "date_of_birth": "1980-03-14", "mrn": "UD900101",
                "document_date": "2026-10-02", "member_id": None}},
    {"id": "img-01", "text": "RADIOLOGY - IMAGING REPORT\nPatient: Marcus Webb\nDate of Birth: 1971-07-22\nReport Date: 09/30/2026\n"
                             "Exam: CT scan abdomen\nImpression: No acute abnormality.\n",
     "expect": {"doc_type": "imaging_report", "first_name": "Marcus", "last_name": "Webb", "date_of_birth": "1971-07-22", "mrn": None,
                "document_date": "2026-09-30", "member_id": None}},
    {"id": "ref-01", "text": "REFERRAL\nReferred by: Lakeside Family Practice\nPatient Name: Okafor, Grace\nDOB: 11/02/1964\n"
                             "Date of Referral: 10/15/2026\nReason for Referral: Evaluation of chronic knee pain.\n",
     "expect": {"doc_type": "referral", "first_name": "Grace", "last_name": "Okafor", "date_of_birth": "1964-11-02", "mrn": None,
                "document_date": "2026-10-15", "member_id": None}},
    {"id": "dc-01", "text": "DISCHARGE SUMMARY\nPatient Name: Lin, Wei\nDOB: 05/09/1955\nMRN: UD900188\nAdmission Date: 10/01/2026\n"
                            "Discharge Date: 10/04/2026\nHospital Course: Uncomplicated.\nDischarge Diagnosis: Community-acquired pneumonia.\n",
     "expect": {"doc_type": "discharge_summary", "first_name": "Wei", "last_name": "Lin", "date_of_birth": "1955-05-09", "mrn": "UD900188",
                "document_date": "2026-10-04", "member_id": None}},
    {"id": "card-01", "text": "Payer: Sample Health Plan\nPlan: Silver PPO\nMember Name: Jordan Blake\nMember ID: SHP448812\n"
                              "Group Number: 77120\nRX BIN: 610014\nEffective Date: 01/01/2026\n",
     "expect": {"doc_type": "insurance_card", "first_name": "Jordan", "last_name": "Blake", "date_of_birth": None, "mrn": None,
                "document_date": None, "member_id": "SHP448812"}},
    {"id": "rx-01", "text": "PRESCRIPTION\nPatient Name: Sam Patel\nDOB: 08/30/1990\nDate: 10/20/2026\nRx: Amoxicillin 500 mg\n"
                            "Sig: one capsule three times daily\nDispense: 30\nRefills: 0\n",
     "expect": {"doc_type": "prescription", "first_name": "Sam", "last_name": "Patel", "date_of_birth": "1990-08-30", "mrn": None,
                "document_date": "2026-10-20", "member_id": None}},
    # Hard case: identifiers absent — a correct extractor returns nulls instead of guessing.
    {"id": "corr-01", "text": "To whom it may concern,\nThank you for your letter regarding the upcoming community health fair.\n"
                              "We look forward to participating.\nKind regards, Front Office\n",
     "expect": {"doc_type": "correspondence", "first_name": None, "last_name": None, "date_of_birth": None, "mrn": None,
                "document_date": None, "member_id": None}},
    # Hard case: scanned image (no text layer).
    {"id": "scan-01", "text": "", "expect": {"doc_type": "other", "first_name": None, "last_name": None, "date_of_birth": None, "mrn": None,
                                              "document_date": None, "member_id": None}},
]


def _norm(v):
    return v.strip().lower() if isinstance(v, str) and v.strip() else (None if isinstance(v, str) else v)


def _actual(a) -> dict:
    return {"doc_type": a.doc_type, "first_name": a.patient.first_name, "last_name": a.patient.last_name, "date_of_birth": a.patient.date_of_birth,
            "mrn": a.patient.mrn, "document_date": a.document_date, "member_id": a.insurance_card.member_id if a.insurance_card else None}


def run_document_extraction(ctx) -> AIEvalRun:
    from app.ai.provider import AIError, get_provider

    provider = get_provider()
    per_field = {f: [0, 0] for f in FIELDS}
    invented = 0
    cases = []
    for s in DOC_SAMPLES:
        start = time.perf_counter()
        try:
            # Samples are synthetic by construction, so contains_phi=False is accurate here.
            got = _actual(provider.analyze_document(s["text"] or None, s["text"].encode(), "text/plain", contains_phi=False).data)
            err = None
        except AIError as e:
            got, err = {}, str(e)[:200]
        wrong = []
        for f in FIELDS:
            exp, act = _norm(s["expect"][f]), _norm(got.get(f))
            per_field[f][1] += 1
            if exp == act:
                per_field[f][0] += 1
            else:
                wrong.append({"field": f, "expected": s["expect"][f], "got": got.get(f)})
                if exp is None and act is not None:
                    invented += 1
        cases.append({"id": s["id"], "correct": len(FIELDS) - len(wrong), "total": len(FIELDS), "errors": wrong, "failure": err,
                      "latency_ms": int((time.perf_counter() - start) * 1000)})
    correct = sum(c for c, _ in per_field.values())
    total = sum(t for _, t in per_field.values())
    run = AIEvalRun(organization_id=ctx.org_id, suite="document_extraction_v1", provider=provider.name, model=getattr(provider, "model", None),
                    samples=len(DOC_SAMPLES), score=round(correct / total, 3), created_by_id=ctx.user.id, cases=cases,
                    metrics={"field_accuracy": {f: round(c / t, 3) for f, (c, t) in per_field.items()}, "invented_values": invented,
                             "failures": sum(1 for c in cases if c["failure"])})
    ctx.db.add(run)
    return run


def run_tool_gate(ctx) -> AIEvalRun:
    from app.agents import tools as T

    probes = [
        ("outside allow-list", "claims_review", ["get_claim_findings"], "get_inventory_item", {"item_id": "00000000-0000-0000-0000-000000000000"}, "not allowed"),
        ("unknown tool", "hospital_operations", ["get_operations_summary"], "delete_everything", {}, "not allowed"),
        ("malformed arguments", "hospital_operations", ["list_open_cases"], "list_open_cases", {"limit": "many"}, "invalid arguments"),
        ("extra arguments", "hospital_operations", ["list_open_cases"], "list_open_cases", {"limit": 3, "sql": "drop table"}, "invalid arguments"),
        ("proposal with bad arguments", "staff_scheduling", ["propose_task"], "propose_task", {}, "invalid arguments"),
    ]
    # Permission probe: a tool whose permission this user lacks (if any) must be refused.
    lacking = next((t for t in T.REGISTRY.values() if t.kind == "read" and not ctx.can(t.permission)), None)
    if lacking:
        probes.append(("user lacks permission", "hospital_operations", [lacking.name], lacking.name, {}, "permission denied"))
    cases, ok = [], 0
    for label, agent, allowed, tool, args, expect in probes:
        r = T.execute(ctx, agent, allowed, tool, args)
        passed = expect in str(r.get("error", ""))
        ok += passed
        cases.append({"id": label, "tool": tool, "passed": passed, "result": str(r)[:200]})
    run = AIEvalRun(organization_id=ctx.org_id, suite="tool_gate_v1", provider="none", model=None, samples=len(probes), score=round(ok / len(probes), 3),
                    created_by_id=ctx.user.id, cases=cases, metrics={"refused": ok, "probes": len(probes), "permission_probe": bool(lacking)})
    ctx.db.add(run)
    return run


SUITES = {"document_extraction_v1": run_document_extraction, "tool_gate_v1": run_tool_gate}
