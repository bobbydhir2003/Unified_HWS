"""Portal expansion: readiness reflects payer-verified coverage; only approved discharge instructions are shown;
outside-records uploads go to staff review; patient notification preferences are honored by delivery."""

import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.engine.notifications import deliver
from app.models import Patient


def test_readiness_and_preferences(as_user):
    pat = as_user("patient@harborview.dev")
    r = pat.get("/portal/readiness").json()
    assert r and all({"insurance", "intake"} <= {i["key"] for i in a["items"]} for a in r)
    prefs = pat.put("/portal/notification-preferences", json={"category": "insurance", "email": False, "sms": False, "portal": True}).json()
    assert next(p for p in prefs if p["category"] == "insurance")["email"] is False
    db = SessionLocal()
    try:
        p = db.scalar(select(Patient).where(Patient.email == "patient@harborview.dev"))
        d = deliver(db, p.organization_id, channel="email", dedupe=f"t:{uuid.uuid4()}", subject="x", body="y", category="insurance", patient_id=p.id)
        assert d.status == "suppressed" and "opted out" in d.status_reason
        db.rollback()
    finally:
        db.close()
    assert as_user("dr.chen@harborview.dev").get("/portal/readiness").status_code == 403


def test_stays_show_only_approved_instructions_and_upload(as_user):
    pat = as_user("patient@harborview.dev")
    for s in pat.get("/portal/stays").json():
        assert (s["instructions"] is None) == (s["instructions_approved_at"] is None)
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    r = pat.post("/portal/documents", files={"file": ("outside-labs.pdf", pdf, "application/pdf")})
    assert r.status_code == 201
    assert any(d["filename"] == "outside-labs.pdf" for d in pat.get("/portal/documents").json())
    tasks = as_user("nurse.rivera@harborview.dev").get("/tasks", params={"scope": "all"}).json()
    assert any(t["kind"] == "documents.portal_upload" for t in tasks)
