"""Additive synthetic data for newer modules. Safe on an existing database: each section runs only if its data is
absent (never deletes or resets). Usage: `uv run python -m app.seed_extend`. Also called by app.seed on fresh seeds."""

import random
import sys
from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import now
from app.models import (
    Clinic,
    InpatientStay,
    InventoryItem,
    InventoryLot,
    Location,
    Order,
    Organization,
    ProviderProfile,
    StockBalance,
    StockMovement,
    Supplier,
)

MEDS = [  # sku, name, form, strength, unit, controlled, reorder_point, reorder_qty, unit_cost_cents, daily_use
    ("RX-CEF1G", "Ceftriaxone", "vial", "1 g", "vial", False, 30, 60, 450, 4),
    ("RX-ENOX40", "Enoxaparin", "syringe", "40 mg/0.4 mL", "syringe", False, 40, 80, 1200, 6),
    ("RX-GLAR", "Insulin glargine", "pen", "100 units/mL", "pen", False, 10, 20, 3900, 1),
    ("RX-ONDA4", "Ondansetron", "tablet", "4 mg", "tablet", False, 50, 200, 35, 5),
    ("RX-APAP500", "Acetaminophen", "tablet", "500 mg", "tablet", False, 200, 1000, 5, 30),
    ("RX-MORPH2", "Morphine sulfate", "vial", "2 mg/mL", "vial", True, 20, 40, 300, 3),
    ("RX-FURO40", "Furosemide", "tablet", "40 mg", "tablet", False, 40, 100, 12, 3),
    ("RX-HEP5K", "Heparin", "vial", "5,000 units/mL", "vial", False, 25, 50, 250, 3),
]
SUPPLIES = [
    ("SP-GLOVE-M", "Nitrile exam gloves (M)", "box", 30, 100, 900, 4),
    ("SP-IVKIT", "IV start kit", "kit", 40, 120, 650, 6),
    ("SP-SYR10", "Syringe 10 mL", "each", 300, 1000, 15, 25),
    ("SP-GAUZE", "Gauze 4×4 (sterile, 10-pack)", "pack", 60, 200, 120, 5),
]


def _move(db, org, lot, loc, kind, qty, at, bal):
    db.add(StockMovement(organization_id=org.id, item_id=lot.item_id, lot_id=lot.id, location_id=loc.id, kind=kind, quantity=qty,
                         balance_after=bal, at=at, reason="Synthetic history" if kind != "receive" else None))


def _stock(db, org, item, loc, lot_number, expiry, start_qty, daily_use, rng, days=28):
    lot = InventoryLot(organization_id=org.id, item_id=item.id, lot_number=lot_number, expiry_date=expiry)
    db.add(lot)
    db.flush()
    bal = start_qty
    _move(db, org, lot, loc, "receive", start_qty, now() - timedelta(days=days + 2), bal)
    for d in range(days, 0, -1):
        use = max(0, int(rng.gauss(daily_use, daily_use * 0.3))) if daily_use else 0
        use = min(use, bal)
        if use:
            bal -= use
            _move(db, org, lot, loc, "dispense", use, now() - timedelta(days=d, hours=rng.randint(0, 20)), bal)
    db.add(StockBalance(organization_id=org.id, location_id=loc.id, lot_id=lot.id, item_id=item.id, quantity=bal))
    return lot


def seed_inventory(db, org: Organization, hosp: Clinic) -> bool:
    if db.scalar(select(InventoryItem.id).where(InventoryItem.organization_id == org.id).limit(1)):
        return False
    rng = random.Random(23)
    locs = {x.code: x for x in db.scalars(select(Location).where(Location.facility_id == hosp.id, Location.kind.in_(("storage", "area"))))}
    s1 = Supplier(organization_id=org.id, name="Northeast Pharma Distributors (synthetic)", lead_time_days=3, email="orders@nepd.example.com")
    s2 = Supplier(organization_id=org.id, name="Harbor Medical Supply (synthetic)", lead_time_days=2, email="orders@harborms.example.com")
    db.add_all([s1, s2])
    db.flush()
    today = date.today()
    items = {}
    for sku, name, form, strength, unit, ctl, rp, rq, cost, use in MEDS:
        it = InventoryItem(organization_id=org.id, kind="medication", name=name, sku=sku, form=form, strength=strength, unit=unit, is_controlled=ctl,
                           reorder_point=rp, reorder_qty=rq, unit_cost_cents=cost, preferred_supplier_id=s1.id, category="Medication")
        db.add(it)
        db.flush()
        items[sku] = (it, use)
    for sku, name, unit, rp, rq, cost, use in SUPPLIES:
        it = InventoryItem(organization_id=org.id, kind="supply", name=name, sku=sku, unit=unit, reorder_point=rp, reorder_qty=rq, unit_cost_cents=cost,
                           preferred_supplier_id=s2.id, category="Medical supplies")
        db.add(it)
        db.flush()
        items[sku] = (it, use)
    main, w4b, icu, ed, sup = (locs.get(c) for c in ("RX-MAIN", "RX-4B", "RX-ICU", "RX-ED", "SUPPLY"))
    for sku, (it, use) in items.items():
        if it.kind == "supply":
            start = it.reorder_point * 2 + use * 28
            if sku == "SP-IVKIT":  # watchdog demo: low stock
                start = use * 28 + it.reorder_point // 2
            _stock(db, org, it, sup, f"{sku}-24A", today + timedelta(days=700), start, use, rng)
            continue
        start = it.reorder_point * 3 + use * 28
        if sku == "RX-ENOX40":  # watchdog demo: below reorder point
            start = use * 28 + 18
        _stock(db, org, it, main, f"{sku[3:]}-L{rng.randint(1000, 9999)}", today + timedelta(days=rng.randint(120, 500)), start, use, rng)
        if ed:
            _stock(db, org, it, ed, f"{sku[3:]}-E{rng.randint(1000, 9999)}", today + timedelta(days=rng.randint(60, 300)), it.reorder_point // 2 + 5, 0, rng)
    # Expiry demos: insulin expiring in 5 days on 4B, ondansetron in 20 days, heparin expired 3 days ago in ICU.
    _stock(db, org, items["RX-GLAR"][0], w4b, "GLAR-X5521", today + timedelta(days=5), 12, 0, rng)
    _stock(db, org, items["RX-ONDA4"][0], w4b, "ONDA-X7710", today + timedelta(days=20), 60, 0, rng)
    _stock(db, org, items["RX-HEP5K"][0], icu, "HEP-X3302", today - timedelta(days=3), 4, 0, rng)
    db.flush()
    return True


def seed_med_orders(db, org: Organization) -> int:
    """Signed medication orders for a few admitted patients (pharmacist verification queue)."""
    if db.scalar(select(Order.id).where(Order.organization_id == org.id, Order.order_type == "medication",
                                        Order.notes == "Synthetic inpatient order").limit(1)):
        return 0
    stays = db.scalars(select(InpatientStay).where(InpatientStay.organization_id == org.id, InpatientStay.status == "admitted").limit(4)).all()
    def med(name, strength, form, route, freq, sig, drug_class, **kw):
        return (f"{name} {strength}", {"name": name, "strength": strength, "dose": strength, "form": form, "route": route, "frequency": freq,
                                       "sig": sig, "quantity": 1, "refills": 0, "setting": "inpatient", "drug_class": drug_class, **kw})

    meds = [med("Ceftriaxone", "1 g", "injection", "intravenous", "daily", "1 g IV every 24 hours", "cephalosporin"),
            med("Heparin", "5,000 units", "injection", "subcutaneous", "q8h", "5,000 units subcutaneously every 8 hours", "anticoagulant"),
            med("Ondansetron IV", "4 mg", "injection", "intravenous", "prn", "4 mg IV every 8 hours as needed for nausea", "antiemetic",
                prn_interval_hours=8, prn_reason="nausea"),
            med("Morphine", "2 mg", "injection", "intravenous", "prn", "2 mg IV every 4 hours as needed for severe pain", "opioid",
                prn_interval_hours=4, prn_reason="severe pain")]
    n = 0
    for s, (title, details) in zip(stays, meds, strict=False):
        prov = db.get(ProviderProfile, s.attending_provider_id) if s.attending_provider_id else None
        if not prov:
            continue
        t = now() - timedelta(minutes=20 + 15 * n)
        db.add(Order(organization_id=org.id, patient_id=s.patient_id, encounter_id=s.encounter_id, order_type="medication", status="pending_verification",
                     title=title, details=details, transmission={"channel": "pharmacy_verification_queue", "simulated": False},
                     safety_warnings=[{"type": "screening_incomplete", "severity": "info",
                                       "message": "Drug–drug interaction screening is NOT available (no licensed drug knowledge base)."}], ordered_by_id=prov.user_id, signed_by_id=prov.user_id, signed_at=t, notes="Synthetic inpatient order"))
        n += 1
    db.flush()
    return n


def seed_second_pharmacist(db, org: Organization, hosp: Clinic) -> bool:
    """Two-person rule demo (waste/negative adjustments need a second pharmacist; lab results a second technologist)."""
    from app.seed import em, user

    _staff(db, org, hosp, em("lab2"), "Marcus", "Bell", "MLS", "lab_tech", "LAB")
    from app.models import (
        Department,
        Membership,
        MembershipClinic,
        MembershipDepartment,
        MembershipRole,
        User,
    )

    if db.scalar(select(User.id).where(User.email == em("pharmacist2"))):
        return False
    u = user(db, em("pharmacist2"), "Priya", "Raman", "PharmD")
    m = Membership(user_id=u.id, organization_id=org.id, all_clinics=False)
    db.add(m)
    db.flush()
    m.roles.append(MembershipRole(role="pharmacist"))
    m.clinics.append(MembershipClinic(clinic_id=hosp.id))
    dept = db.scalar(select(Department.id).where(Department.facility_id == hosp.id, Department.code == "PHARM"))
    if dept:
        m.departments.append(MembershipDepartment(department_id=dept))
    db.flush()
    return True


def seed_lab_orders(db, org: Organization) -> int:
    """Signed in-house lab orders for admitted patients, awaiting collection (lab worklist demo)."""
    from app.data.catalogs import LABS

    if db.scalar(select(Order.id).where(Order.organization_id == org.id, Order.order_type == "lab", Order.notes == "Synthetic inpatient lab").limit(1)):
        return 0
    stays = db.scalars(select(InpatientStay).where(InpatientStay.organization_id == org.id, InpatientStay.status == "admitted")
                       .order_by(InpatientStay.admitted_at).limit(5)).all()
    picks = [LABS[1], LABS[2], LABS[0], LABS[2], LABS[1]]
    n = 0
    for s, (code, name, _spec, _comps) in zip(stays, picks, strict=False):
        prov = db.get(ProviderProfile, s.attending_provider_id) if s.attending_provider_id else None
        if not prov:
            continue
        db.add(Order(organization_id=org.id, patient_id=s.patient_id, encounter_id=s.encounter_id, order_type="lab", status="signed",
                     priority="stat" if n == 0 else "routine", title=name, code=code, details={"specimen": _spec}, ordered_by_id=prov.user_id,
                     signed_by_id=prov.user_id, signed_at=now() - timedelta(minutes=30 + 20 * n), notes="Synthetic inpatient lab"))
        n += 1
    db.flush()
    return n


def _staff(db, org, hosp, email, first, last, title, role, dept_code) -> bool:
    from app.models import (
        Department,
        Membership,
        MembershipClinic,
        MembershipDepartment,
        MembershipRole,
        User,
    )
    from app.seed import user

    if db.scalar(select(User.id).where(User.email == email)):
        return False
    u = user(db, email, first, last, title)
    m = Membership(user_id=u.id, organization_id=org.id, all_clinics=False)
    db.add(m)
    db.flush()
    m.roles.append(MembershipRole(role=role))
    m.clinics.append(MembershipClinic(clinic_id=hosp.id))
    dept = db.scalar(select(Department.id).where(Department.facility_id == hosp.id, Department.code == dept_code))
    if dept:
        m.departments.append(MembershipDepartment(department_id=dept))
    db.flush()
    return True


def seed_imaging_orders(db, org: Organization) -> int:
    if db.scalar(select(Order.id).where(Order.organization_id == org.id, Order.order_type == "imaging", Order.notes == "Synthetic inpatient imaging").limit(1)):
        return 0
    stays = db.scalars(select(InpatientStay).where(InpatientStay.organization_id == org.id, InpatientStay.status == "admitted")
                       .order_by(InpatientStay.admitted_at.desc()).limit(3)).all()
    picks = [("71046", "XR chest, 2 views", "stat", "Hypoxia — evaluate for pneumonia or effusion"),
             ("70450", "CT head without contrast", "urgent", "Fall with confusion — rule out bleed"),
             ("76700", "US abdomen, complete", "routine", "Elevated LFTs — evaluate gallbladder")]
    n = 0
    for s, (code, title, prio, q) in zip(stays, picks, strict=False):
        prov = db.get(ProviderProfile, s.attending_provider_id) if s.attending_provider_id else None
        if not prov:
            continue
        db.add(Order(organization_id=org.id, patient_id=s.patient_id, encounter_id=s.encounter_id, order_type="imaging", status="signed", priority=prio,
                     title=title, code=code, details={"code": code, "laterality": "n/a", "contrast": False, "clinical_question": q},
                     ordered_by_id=prov.user_id, signed_by_id=prov.user_id, signed_at=now() - timedelta(minutes=40 + 25 * n), notes="Synthetic inpatient imaging"))
        n += 1
    db.flush()
    return n


def seed_roster(db, org: Organization, hosp: Clinic) -> int:
    """Synthetic staff + 3 days of shifts meeting minimums (one deliberate gap), skills, and OR cases tomorrow."""
    from app.models import Department, Patient, Shift, StaffSkill, SurgicalCase, User
    from app.seed import em
    from app.services import rostering as RS

    if db.scalar(select(Shift.id).where(Shift.organization_id == org.id).limit(1)):
        return 0
    people = {"MS": [("Ana", "Lopez"), ("Ben", "Ortiz"), ("Cara", "Singh"), ("Dev", "Rao"), ("Eli", "Moss"), ("Fay", "Chu"), ("Gus", "Hale")],
              "ICU": [("Hana", "Ito"), ("Ivan", "Petrov"), ("Jade", "Kerr"), ("Kai", "Lund"), ("Lea", "Voss")],
              "ED": [("Mia", "Dorsey"), ("Nils", "Berg"), ("Oona", "Pike"), ("Pia", "Ruiz"), ("Quinn", "Shaw")]}
    for code, names in people.items():
        for first, last in names:
            _staff(db, org, hosp, em(f"rn.{first.lower()}.{last.lower()}"), first, last, "RN", "nurse", code)
    db.flush()
    for u in db.scalars(select(User).where(User.email.like(em("rn.%")))):
        db.add(StaffSkill(organization_id=org.id, user_id=u.id, skill="BLS", expires_on=date.today() + timedelta(days=400)))
        if u.last_name in ("Ito", "Petrov", "Kerr", "Lund", "Voss", "Dorsey", "Berg"):
            db.add(StaffSkill(organization_id=org.id, user_id=u.id, skill="ACLS", expires_on=date.today() + timedelta(days=300)))
    depts = {d.code: d for d in db.scalars(select(Department).where(Department.facility_id == hosp.id))}
    today = now().astimezone(__import__("zoneinfo").ZoneInfo(hosp.timezone)).date()
    n = 0
    for d in range(0, 3):
        for name in ("day", "night"):
            for code in ("MS", "ICU", "ED"):
                dept = depts[code]
                start, end = RS.window(hosp, today + timedelta(days=d), name)
                need = RS.requirements(dept).get("nurse", {}).get(name, 0)
                if code == "MS" and d == 1 and name == "night":
                    need -= 1  # deliberate coverage gap for the staffing monitor demo
                for c in RS.suggest(db, org.id, dept, "nurse", start, end, limit=need):
                    db.add(Shift(organization_id=org.id, facility_id=hosp.id, department_id=dept.id, user_id=c["user_id"], role="nurse", start_at=start, end_at=end))
                    db.flush()
                    n += 1
    # ED physician coverage (day/night) with the two ED-capable doctors
    docs = [u for u in db.scalars(select(User).where(User.email.in_((em("dr.santos"), em("dr.okafor")))))]
    for d in range(0, 3):
        for i, name in enumerate(("day", "night")):
            start, end = RS.window(hosp, today + timedelta(days=d), name)
            u = docs[i % len(docs)]
            ok, _r, _ = RS.check_candidate(db, u.id, start, end)
            if ok:
                db.add(Shift(organization_id=org.id, facility_id=hosp.id, department_id=depts["ED"].id, user_id=u.id, role="doctor", start_at=start, end_at=end))
                db.flush()
                n += 1
    # OR cases tomorrow
    rooms = db.scalars(select(Location).where(Location.facility_id == hosp.id, Location.kind == "or_room").order_by(Location.sort_order)).all()
    surgeon = db.scalar(select(ProviderProfile).join(User).where(User.email == em("dr.okafor")))
    pts = db.scalars(select(Patient).where(Patient.organization_id == org.id, Patient.is_temporary.is_(False), Patient.is_restricted.is_(False)).limit(3)).all()
    base = datetime.combine(today + timedelta(days=1), time(7, 30), __import__("zoneinfo").ZoneInfo(hosp.timezone))
    for i, (proc, code, mins) in enumerate([("Laparoscopic cholecystectomy", "47562", 90), ("Total knee arthroplasty", "27447", 150),
                                            ("Inguinal hernia repair", "49505", 75)]):
        if i >= len(pts) or not rooms or not surgeon:
            break
        start = base + timedelta(minutes=(mins + 30) * i) if i < 2 else base
        room = rooms[0] if i < 2 else rooms[1]
        sur = surgeon if i < 2 else db.scalar(select(ProviderProfile).join(User).where(User.email == em("dr.chen")))
        db.add(SurgicalCase(organization_id=org.id, facility_id=hosp.id, or_room_id=room.id, patient_id=pts[i].id, surgeon_provider_id=sur.id, procedure=proc,
                            procedure_code=code, start_at=start, end_at=start + timedelta(minutes=mins), blocked_until=start + timedelta(minutes=mins + 30)))
        db.flush()
    return n


def seed_equipment(db, org: Organization, hosp: Clinic) -> int:
    from app.models import Equipment, InventoryItem, StockPar

    if db.scalar(select(Equipment.id).where(Equipment.organization_id == org.id).limit(1)):
        return 0
    locs = {x.code: x for x in db.scalars(select(Location).where(Location.facility_id == hosp.id))}
    today = date.today()
    rows = [("Infusion pump", "IP-0412", "4B", 180, 170), ("Infusion pump", "IP-0413", "4B", 180, 20), ("Defibrillator", "DF-0101", "ED", 90, 95),
            ("Ventilator", "VT-0301", "ICU", 180, 60), ("Patient monitor", "PM-0307", "ICU", 365, 400), ("Anesthesia machine", "AM-0001", "OR", 180, 176),
            ("Portable X-ray", "XR-0002", "RAD-IMG", 365, 30)]
    for name, tag, loc, interval, days_since in rows:
        last = today - timedelta(days=days_since)
        db.add(Equipment(organization_id=org.id, facility_id=hosp.id, location_id=locs[loc].id if loc in locs else None, name=name, asset_tag=tag,
                         manufacturer="Synthetic Medical Co.", maintenance_interval_days=interval, last_maintenance_on=last,
                         next_maintenance_due=last + timedelta(days=interval)))
    items = {i.sku: i for i in db.scalars(select(InventoryItem).where(InventoryItem.organization_id == org.id))}
    for code, sku, par in [("RX-4B", "RX-ONDA4", 40), ("RX-ICU", "RX-HEP5K", 20), ("RX-ED", "RX-MORPH2", 30), ("RX-ED", "RX-APAP500", 100)]:
        if code in locs and sku in items:
            db.add(StockPar(organization_id=org.id, location_id=locs[code].id, item_id=items[sku].id, par_level=par))
    db.flush()
    return len(rows)


def extend_org(db, org: Organization) -> list[str]:
    """All additive hospital modules for one organization ."""
    done: list[str] = []
    hosp = db.scalar(select(Clinic).where(Clinic.organization_id == org.id, Clinic.facility_type == "hospital"))
    if not hosp:
        return done
    if seed_second_pharmacist(db, org, hosp):
        done.append("second pharmacist")
    if seed_inventory(db, org, hosp):
        done.append("inventory")
    if seed_med_orders(db, org):
        done.append("medication orders")
    if seed_lab_orders(db, org):
        done.append("lab orders")
    if seed_imaging_orders(db, org):
        done.append("imaging orders")
    if seed_roster(db, org, hosp):
        done.append("roster + OR cases")
    if seed_equipment(db, org, hosp):
        done.append("equipment + par levels")
    return done


def extend(db) -> list[str]:
    done = []
    for org in db.scalars(select(Organization).where(Organization.slug == "harborview")):
        done += extend_org(db, org)
    return done


if __name__ == "__main__":
    session = SessionLocal()
    try:
        added = extend(session)
        session.commit()
        if added:
            from app.engine.monitors import run_all

            run_all(session)
            session.commit()
        print("Added:", ", ".join(added) if added else "nothing (already present)")
    finally:
        session.close()
    sys.exit(0)
