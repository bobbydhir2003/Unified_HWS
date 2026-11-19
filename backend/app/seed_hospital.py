"""Synthetic hospital structure for Harborview (Milestone A/B). Called from app.seed; all data is fictional."""

from app.models import Clinic, Department, Location, MembershipClinic, MembershipDepartment, Organization


def _loc(db, org, fac, dept, parent, kind, name, code, i=0, **attrs):
    loc = Location(organization_id=org.id, facility_id=fac.id, department_id=dept.id if dept else None,
                   parent_id=parent.id if parent else None, kind=kind, name=name, code=code, sort_order=i,
                   bed_status="available" if kind == "bed" else None, attributes=attrs)
    db.add(loc)
    db.flush()
    return loc


def _unit_with_rooms(db, org, fac, dept, code, name, rooms, beds_per_room, start=1):
    unit = _loc(db, org, fac, dept, None, "unit", name, code)
    for r in range(rooms):
        num = start + r
        room = _loc(db, org, fac, dept, unit, "room", f"Room {num}", f"{code}-{num}", r)
        for b in range(beds_per_room):
            letter = chr(65 + b)
            _loc(db, org, fac, dept, room, "bed", f"{num}{letter}", f"{code}-{num}{letter}", b)
    return unit


def seed_hospital(db, org: Organization, clinics: list[Clinic], users: dict) -> dict:
    """Creates Harborview General Hospital with departments, units, beds, and department-scoped staff."""
    for c in clinics:
        db.add(Department(organization_id=org.id, facility_id=c.id, name="Primary Care", code="PC", kind="outpatient"))
    hosp = Clinic(organization_id=org.id, name="Harborview General Hospital", code="HGH", timezone="America/New_York",
                  facility_type="hospital", phone="(555) 201-9000", address_line1="1 Harbor Medical Plaza", city="Port Harbor",
                  state="MA", postal_code="02114", rooms=[])
    db.add(hosp)
    db.flush()
    spec = [("ED", "Emergency Department", "emergency"), ("MS", "Medical-Surgical", "inpatient"), ("ICU", "Intensive Care", "icu"),
            ("SURG", "Surgical Services", "surgery"), ("PHARM", "Pharmacy", "pharmacy"), ("LAB", "Laboratory", "laboratory"),
            ("RAD", "Radiology", "radiology"), ("BILL", "Patient Financial Services", "billing"), ("ADMIN", "Administration", "administration"),
            ("EVS", "Environmental Services", "support")]
    depts = {}
    for code, name, kind in spec:
        d = Department(organization_id=org.id, facility_id=hosp.id, name=name, code=code, kind=kind)
        db.add(d)
        depts[code] = d
    db.flush()

    ed = _loc(db, org, hosp, depts["ED"], None, "unit", "Emergency Department", "ED")
    for i in range(1, 13):
        _loc(db, org, hosp, depts["ED"], ed, "bed", f"ED Bay {i}", f"ED-{i}", i)
    _loc(db, org, hosp, depts["ED"], ed, "area", "ED Waiting Room", "ED-WAIT", 99)
    _unit_with_rooms(db, org, hosp, depts["MS"], "4B", "Med-Surg 4B", rooms=10, beds_per_room=2, start=401)
    _unit_with_rooms(db, org, hosp, depts["MS"], "4C", "Med-Surg 4C", rooms=8, beds_per_room=1, start=421)
    _unit_with_rooms(db, org, hosp, depts["ICU"], "ICU", "Intensive Care Unit", rooms=8, beds_per_room=1, start=301)
    suite = _loc(db, org, hosp, depts["SURG"], None, "unit", "Surgical Suite", "OR")
    for i in range(1, 5):
        _loc(db, org, hosp, depts["SURG"], suite, "or_room", f"OR {i}", f"OR-{i}", i)
    pharm = _loc(db, org, hosp, depts["PHARM"], None, "area", "Main Pharmacy", "RX-MAIN")
    for code, name in [("RX-4B", "4B Medication Room"), ("RX-ICU", "ICU Medication Room"), ("RX-ED", "ED Medication Room")]:
        _loc(db, org, hosp, depts["PHARM"], pharm, "storage", name, code)
    _loc(db, org, hosp, depts["LAB"], None, "area", "Core Laboratory", "LAB-CORE")
    _loc(db, org, hosp, depts["RAD"], None, "area", "Imaging", "RAD-IMG")
    _loc(db, org, hosp, None, None, "storage", "Central Supply", "SUPPLY")

    # Department-scoped staff: hospital only, specific departments.
    for key, codes in [("pharmacist", ["PHARM"]), ("lab", ["LAB"]), ("radiology", ["RAD"]), ("nurse_ms", ["MS"]),
                       ("bedmanager", None), ("hospitaladmin", None), ("insurance", None), ("ed_doc", ["ED", "MS", "ICU"])]:
        m = users[key]
        if key in ("insurance",):
            continue  # insurance specialist covers every facility
        m.all_clinics = False
        m.clinics.append(MembershipClinic(clinic_id=hosp.id))
        for c in codes or []:
            m.departments.append(MembershipDepartment(department_id=depts[c].id))
    db.flush()
    return {"hospital": hosp, "departments": depts}


def seed_insurance_scenarios(db, org, clinic, provider, appt_type, portal_patient, others: list) -> None:
    """Deterministic Insurance Guardian demo cases (the payer is simulated: see SimulatedEligibility)."""
    from datetime import date, datetime, timedelta
    from zoneinfo import ZoneInfo

    from sqlalchemy import select

    from app.models import Appointment, PatientInsurance

    tz = ZoneInfo(clinic.timezone)

    def visit(p, days, hour=7, minute=0):
        d = date.today() + timedelta(days=days)
        start = datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz)
        a = Appointment(organization_id=org.id, clinic_id=clinic.id, patient_id=p.id, provider_id=provider.id,
                        appointment_type_id=appt_type.id, start_at=start, end_at=start + timedelta(minutes=20), status="scheduled",
                        mode="in_person", reason="Follow-up visit")
        db.add(a)
        return a

    def ins(p):
        return db.scalar(select(PatientInsurance).where(PatientInsurance.patient_id == p.id))

    # A. Portal patient: payer reports coverage inactive → patient asked to upload a new card.
    ins(portal_patient).member_id = "SYN44718230"
    visit(portal_patient, 4)
    # B. Stored end date approaching and no payer response confirms continuation → renewal reminder.
    #    (Pick a patient without upcoming visits, so no automatic eligibility check has run.)
    from app.core.security import now as _now

    future = set(db.scalars(select(Appointment.patient_id).where(Appointment.start_at > _now())))
    renew = next(p for p in others[4:] if p.id not in future)
    b = ins(renew)
    b.member_id, b.termination_date = "SYN55102349", date.today() + timedelta(days=20)
    # C. No insurance on file before a visit.
    ins(others[2]).is_active = False
    visit(others[2], 6, 7, 20)
    # D. Payer unavailable (error) for a visit in ~36 hours → staff task, high severity.
    ins(others[3]).member_id = "SYN66201178"
    visit(others[3], 2, 7, 40)
    db.flush()
