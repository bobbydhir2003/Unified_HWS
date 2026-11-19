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


def seed_inpatients(db, org, hosp, attendings: list, patients: list) -> None:
    """Synthetic census: ~55% of inpatient beds occupied with back-dated history, a few discharges ordered,
    beds in cleaning/blocked, and pending admissions."""
    import random
    from datetime import date, timedelta

    from sqlalchemy import select

    from app.core.security import now
    from app.models import AdtEvent, BedAssignment, BedStatusEvent, InpatientStay, Location

    rng = random.Random(7)
    beds = db.scalars(select(Location).where(Location.facility_id == hosp.id, Location.kind == "bed")
                      .order_by(Location.code)).all()
    ward_beds = [b for b in beds if not b.code.startswith("ED-")]
    pool = iter(patients)
    reasons = ["Community-acquired pneumonia", "CHF exacerbation", "Cellulitis of lower leg", "COPD exacerbation", "Post-op hip arthroplasty",
               "Diabetic ketoacidosis", "Sepsis, urinary source", "Acute kidney injury", "Small bowel obstruction", "GI bleed"]
    for b in ward_beds:
        r = rng.random()
        if r < 0.55:
            p = next(pool)
            los_h = rng.randint(6, 120)
            admitted = now() - timedelta(hours=los_h)
            icu = b.code.startswith("ICU")
            s = InpatientStay(organization_id=org.id, facility_id=hosp.id, department_id=b.department_id, requested_department_id=b.department_id,
                              patient_id=p.id, attending_provider_id=rng.choice(attendings).id, status="admitted",
                              admit_source=rng.choice(["ed", "ed", "direct", "elective"]), level_of_care="icu" if icu else "med_surg",
                              reason=rng.choice(reasons), requested_at=admitted - timedelta(minutes=rng.randint(30, 240)), admitted_at=admitted,
                              expected_discharge_date=(admitted + timedelta(days=rng.randint(2, 6))).date(),
                              isolation="contact" if rng.random() < 0.1 else None)
            db.add(s)
            db.flush()
            db.add(BedAssignment(organization_id=org.id, stay_id=s.id, bed_id=b.id, patient_id=p.id, start_at=admitted, reason="admit"))
            from app.services.adt import ensure_encounter

            ensure_encounter(db, s)
            db.add(AdtEvent(organization_id=org.id, stay_id=s.id, patient_id=p.id, kind="admission_requested", at=s.requested_at, note=s.reason))
            db.add(AdtEvent(organization_id=org.id, stay_id=s.id, patient_id=p.id, kind="admitted", to_bed_id=b.id, at=admitted))
            b.bed_status, b.bed_status_changed_at = "occupied", admitted
            if s.expected_discharge_date <= date.today() and rng.random() < 0.6:
                s.status, s.discharge_ordered_at, s.discharge_disposition = "discharge_ordered", now() - timedelta(minutes=rng.randint(20, 300)), "home"
                db.add(AdtEvent(organization_id=org.id, stay_id=s.id, patient_id=p.id, kind="discharge_ordered", at=s.discharge_ordered_at, note="home"))
                from app.services.discharge import ensure_plan, fan_out

                plan = ensure_plan(db, s)
                fan_out(db, s, plan)
        elif r < 0.62:
            since = now() - timedelta(minutes=rng.randint(15, 140))
            b.bed_status, b.bed_status_changed_at = "cleaning", since
            db.add(BedStatusEvent(organization_id=org.id, bed_id=b.id, from_status="occupied", to_status="cleaning", reason="patient discharged", at=since))
        elif r < 0.64:
            b.bed_status, b.bed_status_reason, b.bed_status_changed_at = "blocked", "Broken bed rail — maintenance requested", now() - timedelta(hours=5)
    for mins, reason, loc in [(150, "Pneumonia, hypoxic — needs med-surg bed", "med_surg"), (35, "Chest pain, rule out MI — telemetry", "telemetry")]:
        p = next(pool)
        req = now() - timedelta(minutes=mins)
        s = InpatientStay(organization_id=org.id, facility_id=hosp.id, patient_id=p.id, attending_provider_id=attendings[0].id, status="pending",
                          admit_source="ed", level_of_care=loc, reason=reason, requested_at=req)
        db.add(s)
        db.flush()
        db.add(AdtEvent(organization_id=org.id, stay_id=s.id, patient_id=p.id, kind="admission_requested", at=req, note=reason))
    db.flush()


def seed_ed(db, org, hosp, ed_doc, nurse_user_id, patients: list) -> None:
    """Synthetic ED census: waiting, triaged, roomed (seen), one unidentified trauma, one boarding admission, recent departures."""
    import random
    from datetime import timedelta

    from sqlalchemy import select

    from app.core.security import now
    from app.models import EdVisit, Encounter, InpatientStay, Location, Patient, TriageAssessment

    rng = random.Random(11)
    bays = db.scalars(select(Location).where(Location.facility_id == hosp.id, Location.code.like("ED-%"), Location.kind == "bed")
                      .order_by(Location.sort_order)).all()
    bay_iter = iter(bays)
    pool = iter(patients)

    def visit(p, minutes_ago, complaint, *, esi=None, roomed=False, seen=False, mode="walk_in"):
        arr = now() - timedelta(minutes=minutes_ago)
        v = EdVisit(organization_id=org.id, facility_id=hosp.id, patient_id=p.id, arrival_at=arr, arrival_mode=mode, chief_complaint=complaint,
                    status="waiting")
        db.add(v)
        db.flush()
        if esi:
            v.esi_level, v.triaged_at, v.status = esi, arr + timedelta(minutes=rng.randint(3, 12)), "triaged"
            db.add(TriageAssessment(organization_id=org.id, ed_visit_id=v.id, patient_id=p.id, esi_level=esi, complaint=complaint,
                                    recorded_by_id=nurse_user_id, at=v.triaged_at))
        if roomed:
            bay = next(bay_iter)
            v.bed_id, v.roomed_at, v.status, v.nurse_user_id = bay.id, arr + timedelta(minutes=20), "roomed", nurse_user_id
            bay.bed_status, bay.bed_status_changed_at = "occupied", v.roomed_at
        if seen:
            v.provider_id, v.provider_seen_at = ed_doc.id, arr + timedelta(minutes=rng.randint(15, 45))
            e = Encounter(organization_id=org.id, clinic_id=hosp.id, patient_id=p.id, provider_id=ed_doc.id, encounter_type="emergency",
                          status="in_progress", chief_complaint=complaint, started_at=v.provider_seen_at)
            db.add(e)
            db.flush()
            v.encounter_id = e.id
        return v

    visit(next(pool), 8, "Ankle injury after fall")
    visit(next(pool), 35, "Abdominal pain, vomiting", esi=3)
    visit(next(pool), 25, "Laceration to hand", esi=4)
    visit(next(pool), 70, "Chest pain radiating to left arm", esi=2, roomed=True, seen=True, mode="ambulance")
    visit(next(pool), 50, "Shortness of breath", esi=3, roomed=True)
    # Unidentified trauma patient (temporary identity until reconciled).
    tmp = Patient(organization_id=org.id, mrn="UD199901", first_name="Unidentified", last_name="Male 1119-TRMA", date_of_birth=__import__("datetime").date(1985, 1, 1),
                  sex_at_birth="male", is_temporary=True)
    db.add(tmp)
    db.flush()
    visit(tmp, 40, "Motor vehicle collision, unresponsive at scene", esi=1, roomed=True, seen=True, mode="ambulance")
    # Link the oldest pending admission to an ED visit that is now boarding.
    stay = db.scalar(select(InpatientStay).where(InpatientStay.facility_id == hosp.id, InpatientStay.status == "pending")
                     .order_by(InpatientStay.requested_at).limit(1))
    if stay:
        v = visit(stay.patient, int((now() - stay.requested_at).total_seconds() // 60) + 150, stay.reason, esi=3, roomed=True, seen=True)
        v.status, v.stay_id, v.disposition_at = "boarding", stay.id, stay.requested_at
        stay.ed_visit_id = v.id
    # Recent departures for metrics.
    for mins, dispo in [(300, "discharged"), (420, "discharged"), (260, "lwbs"), (600, "discharged")]:
        v = visit(next(pool), mins, rng.choice(["Back pain", "Headache", "Sore throat", "Rash"]), esi=rng.choice([4, 5]), seen=dispo != "lwbs")
        v.status, v.disposition, v.disposition_at, v.departed_at = "departed", dispo, now() - timedelta(minutes=mins - 150), now() - timedelta(minutes=mins - 160)
    db.flush()
