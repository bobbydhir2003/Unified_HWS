"""Synthetic development dataset. All people, records and identifiers are fictional.

Usage:  python -m app.seed          (no-op if already seeded)
        python -m app.seed --reset  (truncate everything and reseed)
"""

import random
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from app.core.db import SessionLocal, engine
from app.core.security import hash_password, now
from app.models import (
    Allergy,
    Appointment,
    AppointmentType,
    Base,
    Clinic,
    ClinicalNote,
    ClinicalNoteVersion,
    ClinicalTemplate,
    Encounter,
    EncounterDiagnosis,
    HistoryEntry,
    Membership,
    MembershipRole,
    Organization,
    Patient,
    PatientInsurance,
    PatientMedication,
    Problem,
    ProviderAvailability,
    ProviderProfile,
    User,
    VitalSigns,
)

DEV_PASSWORD = "Undeclared!2026"
rng = random.Random(20261119)

FIRST_F = ["Ava", "Sofia", "Maya", "Isabella", "Grace", "Lena", "Priya", "Hana", "Chloe", "Nora", "Elena", "Amara",
           "Zoe", "Leah", "Mei", "Fatima", "Ruth", "Iris", "Clara", "Dana"]
FIRST_M = ["Liam", "Noah", "Mateo", "Ethan", "Lucas", "Omar", "Arjun", "Kenji", "Samuel", "Theo", "Jonah", "Elias",
           "Marcus", "Diego", "Felix", "Isaac", "Tomas", "Ravi", "Owen", "Caleb"]
LAST = ["Alvarez", "Brennan", "Castillo", "Delacroix", "Eastwood", "Fairbanks", "Goldberg", "Haddad", "Ibarra",
        "Jablonski", "Kowalczyk", "Lindqvist", "Moreau", "Nakamura", "Oyelaran", "Petrov", "Quintero", "Ramaswamy",
        "Sorensen", "Thibault", "Underwood", "Vasquez", "Whitlock", "Xiong", "Yamada", "Zielinski", "Ashford", "Brightwater"]
STREETS = ["Maple Ave", "Harbor St", "Cedar Ln", "Beacon Rd", "Orchard Way", "Willow Ct", "Granite Pl", "Juniper Dr"]
PAYERS = [("Bluebay Health (synthetic)", "PPO Gold"), ("Meridian Care (synthetic)", "HMO Select"),
          ("Northstar Mutual (synthetic)", "EPO Standard"), ("Federal Senior Plan (synthetic)", "Part B")]

CHRONIC = [("I10", "Essential (primary) hypertension", "Lisinopril", "10 mg", "daily"),
           ("E11.9", "Type 2 diabetes mellitus without complications", "Metformin", "500 mg", "twice daily"),
           ("E78.5", "Hyperlipidemia, unspecified", "Atorvastatin", "20 mg", "nightly"),
           ("J45.909", "Unspecified asthma, uncomplicated", "Albuterol HFA", "90 mcg, 2 puffs", "every 4–6 h as needed"),
           ("E03.9", "Hypothyroidism, unspecified", "Levothyroxine", "75 mcg", "daily"),
           ("K21.9", "Gastro-esophageal reflux disease without esophagitis", "Omeprazole", "20 mg", "daily"),
           ("F41.1", "Generalized anxiety disorder", "Sertraline", "50 mg", "daily")]
ALLERGENS = [("Penicillin", "medication", "Hives", "moderate"), ("Sulfa drugs", "medication", "Rash", "mild"),
             ("Peanuts", "food", "Anaphylaxis", "life_threatening"), ("Latex", "environmental", "Contact dermatitis", "mild"),
             ("Codeine", "medication", "Nausea, vomiting", "moderate"), ("Shellfish", "food", "Throat swelling", "severe")]
ACUTE = [("J06.9", "Acute upper respiratory infection, unspecified", "Cough and congestion for 4 days"),
         ("M54.50", "Low back pain, unspecified", "Low back pain after lifting"),
         ("N39.0", "Urinary tract infection, site not specified", "Burning with urination"),
         ("R51.9", "Headache, unspecified", "Recurring headaches"),
         ("L30.9", "Dermatitis, unspecified", "Itchy rash on forearms")]


def user(db, email, first, last, title=None, superadmin=False) -> User:
    u = User(email=email, first_name=first, last_name=last, title=title, is_superadmin=superadmin,
             password_hash=hash_password(DEV_PASSWORD))
    db.add(u)
    db.flush()
    return u


def member(db, u: User, org: Organization, *roles: str) -> Membership:
    m = Membership(user_id=u.id, organization_id=org.id, all_clinics=True)
    db.add(m)
    db.flush()
    for r in roles:
        m.roles.append(MembershipRole(role=r))
    return m


def provider(db, u: User, org: Organization, specialty, creds, color, npi) -> ProviderProfile:
    p = ProviderProfile(organization_id=org.id, user_id=u.id, specialty=specialty, credentials=creds, color=color, npi=npi)
    db.add(p)
    db.flush()
    return p


def availability(db, org, prov, clinic, weekdays, blocks=((8, 0, 12, 0), (13, 0, 17, 0))):
    for wd in weekdays:
        for sh, sm, eh, em in blocks:
            db.add(ProviderAvailability(organization_id=org.id, provider_id=prov.id, clinic_id=clinic.id, weekday=wd,
                                        start_time=time(sh, sm), end_time=time(eh, em)))


def make_patient(db, org, clinic, prov, mrn_seq, *, first=None, last=None, sex=None, dob=None) -> Patient:
    sex = sex or rng.choice(["female", "male"])
    first = first or rng.choice(FIRST_F if sex == "female" else FIRST_M)
    last = last or rng.choice(LAST)
    dob = dob or date(rng.randint(1942, 2018), rng.randint(1, 12), rng.randint(1, 28))
    p = Patient(
        organization_id=org.id, mrn=f"UD{mrn_seq}", first_name=first, last_name=last, date_of_birth=dob, sex_at_birth=sex,
        email=f"{first.lower()}.{last.lower()}{mrn_seq % 97}@example.com",
        phone=f"(555) {rng.randint(200, 899)}-{rng.randint(1000, 9999)}",
        address_line1=f"{rng.randint(10, 9999)} {rng.choice(STREETS)}", city="Port Harbor", state="MA",
        postal_code=f"02{rng.randint(100, 999)}", preferred_language=rng.choice(["English"] * 6 + ["Spanish", "Portuguese"]),
        emergency_contact_name=f"{rng.choice(FIRST_F + FIRST_M)} {last}", emergency_contact_relation=rng.choice(["Spouse", "Parent", "Sibling"]),
        emergency_contact_phone=f"(555) {rng.randint(200, 899)}-{rng.randint(1000, 9999)}",
        primary_clinic_id=clinic.id, primary_provider_id=prov.id,
    )
    db.add(p)
    db.flush()
    payer, plan = rng.choice(PAYERS)
    db.add(PatientInsurance(organization_id=org.id, patient_id=p.id, payer_name=payer, plan_name=plan,
                            member_id=f"SYN{rng.randint(10000000, 99999999)}", group_number=f"G{rng.randint(1000, 9999)}",
                            subscriber_name=p.full_name, effective_date=date(2024, 1, 1)))
    return p


def chart(db, org, p: Patient, recorder: User):
    for code, desc, med, dose, freq in rng.sample(CHRONIC, k=rng.choice([0, 1, 1, 2, 3])):
        db.add(Problem(organization_id=org.id, patient_id=p.id, code=code, description=desc, is_chronic=True,
                       onset_date=date(rng.randint(2010, 2023), rng.randint(1, 12), 1), recorded_by_id=recorder.id))
        db.add(PatientMedication(organization_id=org.id, patient_id=p.id, name=med, dose=dose, route="oral" if "HFA" not in med else "inhaled",
                                 frequency=freq, indication=desc.split(",")[0], source="reported", recorded_by_id=recorder.id,
                                 start_date=date(rng.randint(2015, 2024), rng.randint(1, 12), 1)))
    for sub, cat, rxn, sev in rng.sample(ALLERGENS, k=rng.choice([0, 0, 1, 1, 2])):
        db.add(Allergy(organization_id=org.id, patient_id=p.id, substance=sub, category=cat, reaction=rxn, severity=sev,
                       recorded_by_id=recorder.id))
    db.add(HistoryEntry(organization_id=org.id, patient_id=p.id, category="social",
                        condition=rng.choice(["Never smoker", "Former smoker (quit 2015)", "Current smoker, 1/2 ppd"]),
                        details=rng.choice(["Drinks socially", "No alcohol", "Exercises 3x/week"]), recorded_by_id=recorder.id))
    if rng.random() < 0.6:
        db.add(HistoryEntry(organization_id=org.id, patient_id=p.id, category="family",
                            condition=rng.choice(["Coronary artery disease", "Type 2 diabetes", "Breast cancer", "Hypertension"]),
                            relation=rng.choice(["Mother", "Father", "Sibling", "Grandparent"]), recorded_by_id=recorder.id))
    if rng.random() < 0.3:
        db.add(HistoryEntry(organization_id=org.id, patient_id=p.id, category="surgical",
                            condition=rng.choice(["Appendectomy", "Cholecystectomy", "ACL repair", "Tonsillectomy"]),
                            occurred_on=str(rng.randint(1995, 2022)), recorded_by_id=recorder.id))


def past_visit(db, org, clinic, prov: ProviderProfile, p: Patient, appt_type, when: datetime, nurse: User):
    code, desc, cc = rng.choice(ACUTE)
    a = Appointment(organization_id=org.id, clinic_id=clinic.id, patient_id=p.id, provider_id=prov.id,
                    appointment_type_id=appt_type.id, start_at=when, end_at=when + timedelta(minutes=appt_type.duration_minutes),
                    status="checked_out", reason=cc, checked_in_at=when - timedelta(minutes=10),
                    roomed_at=when - timedelta(minutes=3), checked_out_at=when + timedelta(minutes=35), room="Exam 2")
    db.add(a)
    db.flush()
    e = Encounter(organization_id=org.id, clinic_id=clinic.id, patient_id=p.id, provider_id=prov.id, appointment_id=a.id,
                  status="completed", chief_complaint=cc, started_at=when, completed_at=when + timedelta(minutes=30),
                  follow_up="Return if symptoms worsen or in 2 weeks if not improving")
    db.add(e)
    db.flush()
    db.add(EncounterDiagnosis(organization_id=org.id, encounter_id=e.id, code=code, description=desc, rank=1))
    sbp, dbp = rng.randint(110, 148), rng.randint(68, 92)
    db.add(VitalSigns(organization_id=org.id, patient_id=p.id, encounter_id=e.id, measured_at=when - timedelta(minutes=2),
                      systolic=sbp, diastolic=dbp, heart_rate=rng.randint(60, 96), respiratory_rate=rng.randint(12, 18),
                      temperature_c=round(rng.uniform(36.4, 37.6), 1), spo2=rng.randint(95, 100),
                      height_cm=rng.randint(152, 190), weight_kg=rng.randint(52, 105), pain_score=rng.randint(0, 5),
                      recorded_by_id=nurse.id))
    content = {
        "subjective": f"Chief complaint: {cc}.\nPatient reports onset several days ago. Denies fever, chest pain or shortness of breath.",
        "objective": f"BP {sbp}/{dbp}. Alert, well-appearing, no acute distress. Exam otherwise unremarkable for the presenting complaint.",
        "assessment": f"{desc} ({code}).",
        "plan": "Supportive care and return precautions reviewed. Follow up in 2 weeks if not improving.",
    }
    n = ClinicalNote(organization_id=org.id, encounter_id=e.id, patient_id=p.id, author_id=prov.user_id, title="Progress note",
                     status="draft", current_version=2, content=content)
    db.add(n)
    db.flush()
    db.add(ClinicalNoteVersion(organization_id=org.id, note_id=n.id, version=1, content=content, source="manual", created_by_id=prov.user_id))
    db.add(ClinicalNoteVersion(organization_id=org.id, note_id=n.id, version=2, content=content, source="sign", created_by_id=prov.user_id))
    db.flush()
    n.status, n.signed_at, n.signed_by_id = "signed", when + timedelta(minutes=40), prov.user_id
    db.flush()


TEMPLATES = [
    ("Acute visit (SOAP)", "Family Medicine", {
        "subjective": "Chief complaint:\nHPI (onset, location, duration, character, aggravating/relieving factors, severity):\nROS:",
        "objective": "Vitals reviewed.\nGeneral:\nHEENT:\nCardiovascular:\nRespiratory:\nAbdomen:\nSkin:",
        "assessment": "", "plan": "Treatment:\nPatient education:\nFollow-up:"}),
    ("Chronic care follow-up", "Internal Medicine", {
        "subjective": "Follow-up for chronic conditions.\nMedication adherence:\nSide effects:\nInterval history:",
        "objective": "Vitals reviewed.\nPertinent exam:\nRecent labs:", "assessment": "",
        "plan": "Medications:\nLabs ordered:\nLifestyle counseling:\nReturn visit:"}),
    ("Annual wellness exam", "Family Medicine", {
        "subjective": "Annual exam. Concerns today:\nDiet/exercise:\nSleep:\nMood (PHQ-2):\nPreventive history:",
        "objective": "Vitals and BMI reviewed.\nComplete exam:", "assessment": "Encounter for general adult medical examination.",
        "plan": "Age-appropriate screenings:\nImmunizations:\nCounseling:\nReturn in 12 months."}),
]


def seed_history(db, org, providers: dict, lab_user):
    """Synthetic lab and billing history so analytics, care gaps and A/R have realistic shape."""
    from app.data.cpt_common import CPT_DEFAULTS
    from app.models import Charge, Claim, ClaimEvent, Invoice, PatientInsurance, Payment

    fees = {c: (d, cents) for c, d, cents in CPT_DEFAULTS}
    today = now()
    # --- labs: A1c for diabetics, lipids for hyperlipidemia ---
    for prob in db.scalars(select(Problem).where(Problem.organization_id == org.id, Problem.status == "active")).all():
        pat = db.get(Patient, prob.patient_id)
        prov = providers.get(pat.primary_provider_id)
        if not prov:
            continue
        if prob.code and prob.code.startswith("E11"):
            draws = rng.choice([[400], [300, 120], [210, 30], []])  # some patients overdue / never tested
            level = rng.uniform(6.4, 10.2)
            for ago in draws:
                level = max(5.8, level + rng.uniform(-0.8, 0.5))
                _lab(db, org, pat, prov, lab_user, "4548-4", "Hemoglobin A1c", [("Hemoglobin A1c", "%", round(level, 1), "4.0-5.6", 5.6)], today - timedelta(days=ago))
        if prob.code and prob.code.startswith("E78") and rng.random() < 0.6:
            ago = rng.choice([90, 200, 500])
            ldl = rng.randint(85, 185)
            _lab(db, org, pat, prov, lab_user, "57698-3", "Lipid panel", [("LDL cholesterol", "mg/dL", ldl, "0-129", 129),
                                                                          ("HDL cholesterol", "mg/dL", rng.randint(35, 70), "40-100", 100)], today - timedelta(days=ago))
    db.flush()
    # --- billing for completed visits older than 10 days ---
    seq_c, seq_i = 1000, 1000
    encs = db.scalars(select(Encounter).where(Encounter.organization_id == org.id, Encounter.status == "completed",
                                              Encounter.started_at < today - timedelta(days=10)).order_by(Encounter.started_at)).all()
    for e in encs:
        ins = db.scalar(select(PatientInsurance).where(PatientInsurance.patient_id == e.patient_id, PatientInsurance.priority == "primary"))
        code = rng.choice(["99213", "99213", "99214"])
        desc, price = fees[code]
        dx = [d.code for d in e.diagnoses][:1] or ["Z00.00"]
        seq_c += 1
        roll = rng.random()
        status = "paid" if roll < 0.75 else "denied" if roll < 0.85 else "accepted"
        sub = e.started_at + timedelta(days=2)
        c = Claim(organization_id=org.id, claim_number=f"CLM-{sub:%y}-{seq_c}", patient_id=e.patient_id, encounter_id=e.id, insurance_id=ins.id,
                  payer_name=ins.payer_name, member_id=ins.member_id, rendering_provider_id=e.provider_id, service_date=e.started_at.date(),
                  status=status, total_charge_cents=price, scrub_errors=[], clearinghouse_ref=f"SIM-837-HIST{seq_c}", submitted_at=sub, submission_count=1)
        c.created_at = sub
        db.add(c)
        db.flush()
        db.add(Charge(organization_id=org.id, encounter_id=e.id, patient_id=e.patient_id, claim_id=c.id, code=code, description=desc, units=1,
                      unit_price_cents=price, amount_cents=price, diagnosis_codes=dx, status="billed"))
        db.add(ClaimEvent(organization_id=org.id, claim_id=c.id, event="submitted", details={"simulated": True}, created_at=sub))
        if status == "paid":
            adj = sub + timedelta(days=rng.randint(10, 28))
            allowed = round(price * 0.78)
            resp = round(allowed * 0.2)
            c.allowed_cents, c.paid_cents, c.patient_responsibility_cents, c.adjustment_cents, c.adjudicated_at = allowed, allowed - resp, resp, price - allowed, adj
            pay = Payment(organization_id=org.id, patient_id=e.patient_id, claim_id=c.id, source="insurance", method="eft_simulated", amount_cents=allowed - resp,
                          reference=f"ERA-HIST{seq_c}", idempotency_key=f"seed-era-{c.id}")
            pay.created_at = adj
            db.add(pay)
            db.add(ClaimEvent(organization_id=org.id, claim_id=c.id, event="paid", details={"simulated": True}, created_at=adj))
            seq_i += 1
            paid_by_patient = rng.random() < 0.6
            inv = Invoice(organization_id=org.id, number=f"INV-{adj:%y}-{seq_i}", patient_id=e.patient_id, claim_id=c.id, encounter_id=e.id,
                          description=f"Patient responsibility for visit {e.started_at:%b %d, %Y}", status="paid" if paid_by_patient else "open",
                          total_cents=resp, balance_cents=0 if paid_by_patient else resp, due_date=(adj + timedelta(days=30)).date())
            inv.issued_at = adj
            db.add(inv)
            db.flush()
            if paid_by_patient:
                pp = Payment(organization_id=org.id, patient_id=e.patient_id, invoice_id=inv.id, claim_id=c.id, source="patient", method=rng.choice(["card_simulated", "cash", "check"]),
                             amount_cents=resp, idempotency_key=f"seed-pp-{inv.id}")
                pp.created_at = adj + timedelta(days=rng.randint(3, 25))
                db.add(pp)
        elif status == "denied":
            adj = sub + timedelta(days=12)
            c.denial_code, c.denial_reason, c.adjudicated_at, c.allowed_cents = "CO-16", "Claim lacks information needed for adjudication", adj, 0
            db.add(ClaimEvent(organization_id=org.id, claim_id=c.id, event="denied", details={"code": "CO-16", "simulated": True}, created_at=adj))
    org.settings = {**org.settings, "claim_seq": seq_c, "invoice_seq": seq_i}


def _lab(db, org, pat, prov, user, code, title, comps, when):
    from app.models import LabResult, Order

    o = Order(organization_id=org.id, patient_id=pat.id, order_type="lab", status="completed", title=title, code=code, details={"code": code},
              ordered_by_id=prov.user_id, signed_by_id=prov.user_id, signed_at=when - timedelta(days=2), transmitted_at=when - timedelta(days=2),
              transmission={"channel": "Lab interface (simulated)", "reference": "SIM-LAB-HIST", "simulated": True, "destination": "Default partner (simulated)"},
              resulted_at=when, results_reviewed_by_id=prov.user_id, results_reviewed_at=when + timedelta(days=1), released_to_patient_at=when + timedelta(days=1))
    o.created_at = when - timedelta(days=2)
    db.add(o)
    db.flush()
    for name, unit, val, rr, hi in comps:
        lo = float(rr.split("-")[0])
        flag = "high" if val > hi else "low" if val < lo else "normal"
        db.add(LabResult(organization_id=org.id, order_id=o.id, patient_id=pat.id, name=name, value=str(val), unit=unit, reference_range=rr,
                         flag=flag, resulted_at=when, source="simulated"))


def seed(reset: bool = False) -> None:
    if reset:
        with engine.begin() as c:
            tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
            c.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    db = SessionLocal()
    try:
        if db.scalar(select(Organization.id).where(Organization.slug == "harborview")):
            print("Already seeded (use --reset to reseed).")
            return

        superadmin = user(db, "admin@undeclared.dev", "Platform", "Admin", superadmin=True)

        # ---- Org 1: Harborview Family Medicine ----
        org = Organization(name="Harborview Health", slug="harborview",
                           settings={"synthetic_data": True, "mrn_seq": 100000, "fax_webhook_secret": "dev-fax-secret-harborview", "voice_webhook_secret": "dev-voice-secret-harborview"})
        db.add(org)
        db.flush()
        tz = "America/New_York"
        downtown = Clinic(organization_id=org.id, name="Harborview Downtown", code="HDT", timezone=tz, phone="(555) 201-4400",
                          address_line1="120 Beacon Rd", city="Port Harbor", state="MA", postal_code="02110",
                          rooms=["Exam 1", "Exam 2", "Exam 3", "Procedure"])
        north = Clinic(organization_id=org.id, name="Harborview Northside", code="HNS", timezone=tz, phone="(555) 201-4500",
                       address_line1="88 Orchard Way", city="Port Harbor", state="MA", postal_code="02128", rooms=["Exam A", "Exam B"])
        db.add_all([downtown, north])
        db.flush()

        admin_u = user(db, "clinicadmin@harborview.dev", "Jordan", "Blake")
        chen_u = user(db, "dr.chen@harborview.dev", "Maya", "Chen", "MD")
        okafor_u = user(db, "dr.okafor@harborview.dev", "Daniel", "Okafor", "DO")
        nurse_u = user(db, "nurse.rivera@harborview.dev", "Lucia", "Rivera", "RN")
        front_u = user(db, "frontdesk@harborview.dev", "Sam", "Patel")
        billing_u = user(db, "billing@harborview.dev", "Morgan", "Lee")
        member(db, superadmin, org, "super_admin")
        member(db, admin_u, org, "clinic_admin")
        member(db, chen_u, org, "doctor")
        member(db, okafor_u, org, "doctor", "clinic_admin")  # multi-role example
        member(db, nurse_u, org, "nurse")
        member(db, front_u, org, "receptionist")
        member(db, billing_u, org, "billing")
        chen = provider(db, chen_u, org, "Family Medicine", "MD", "blue", "1234567893")
        okafor = provider(db, okafor_u, org, "Internal Medicine", "DO", "violet", "1245319599")
        availability(db, org, chen, downtown, range(0, 5))
        availability(db, org, okafor, downtown, (0, 2, 4))
        availability(db, org, okafor, north, (1, 3))

        types = {name: AppointmentType(organization_id=org.id, name=name, duration_minutes=d, color=c, is_telehealth=t)
                 for name, d, c, t in [("New patient", 40, "emerald", False), ("Follow-up", 20, "blue", False),
                                       ("Annual physical", 40, "amber", False), ("Sick visit", 20, "rose", False),
                                       ("Telehealth follow-up", 20, "cyan", True)]}
        db.add_all(types.values())
        from app.data.cpt_common import CPT_DEFAULTS
        from app.models import FeeScheduleItem

        for code, desc, cents in CPT_DEFAULTS:
            db.add(FeeScheduleItem(organization_id=org.id, code=code, description=desc, price_cents=cents))
        from app.services.automation import install_all

        install_all(db, org.id, enabled=True)
        for name, spec, content in TEMPLATES:
            db.add(ClinicalTemplate(organization_id=org.id, name=name, specialty=spec, content=content))
        db.flush()

        patients = []
        seq = 100000
        for i in range(44):
            seq += 1
            prov = chen if i % 3 else okafor
            p = make_patient(db, org, downtown if i % 4 else north, prov, seq)
            chart(db, org, p, nurse_u)
            patients.append(p)
        # Portal patient with a known login
        seq += 1
        portal_u = user(db, "patient@harborview.dev", "Elena", "Moreau")
        member(db, portal_u, org, "patient")
        portal_p = make_patient(db, org, downtown, chen, seq, first="Elena", last="Moreau", sex="female", dob=date(1986, 4, 12))
        portal_p.email, portal_p.portal_user_id = "patient@harborview.dev", portal_u.id
        chart(db, org, portal_p, nurse_u)
        patients.append(portal_p)
        # Restricted (VIP) chart example
        seq += 1
        vip = make_patient(db, org, downtown, okafor, seq, first="Victor", last="Ashford", sex="male", dob=date(1971, 9, 3))
        vip.is_restricted = True
        patients.append(vip)
        # Near-duplicate pair for duplicate detection demo
        seq += 1
        make_patient(db, org, downtown, chen, seq, first="Jonathan", last="Brennan", sex="male", dob=date(1990, 2, 14))
        org.settings = {**org.settings, "mrn_seq": seq}
        db.flush()

        # Past visits (signed notes)
        zone = ZoneInfo(tz)
        today = now().astimezone(zone).date()
        for p in rng.sample(patients[:-1], 30):
            for _ in range(rng.randint(1, 3)):
                d = today - timedelta(days=rng.randint(3, 120))
                while d.weekday() > 4:
                    d -= timedelta(days=1)
                when = datetime.combine(d, time(rng.choice([8, 9, 10, 11, 13, 14, 15, 16]), rng.choice([0, 20, 40])), zone)
                prov = chen if p.primary_provider_id == chen.id else okafor
                clash = db.scalar(select(Appointment.id).where(
                    Appointment.provider_id == prov.id, Appointment.start_at < when + timedelta(minutes=20),
                    Appointment.end_at > when))
                if not clash:
                    past_visit(db, org, downtown, prov, p, types["Sick visit"], when, nurse_u)

        # Today + next 10 business days
        slots_today = [(8, 0), (8, 20), (8, 40), (9, 0), (9, 40), (10, 20), (11, 0), (13, 0), (13, 40), (14, 20), (15, 0), (15, 40), (16, 20)]
        pool = [p for p in patients if p is not vip]
        for day_off in range(0, 15):
            d = today + timedelta(days=day_off)
            if d.weekday() > 4:
                continue
            for prov, clinic in ((chen, downtown), (okafor, downtown if d.weekday() in (0, 2, 4) else north)):
                chosen = slots_today if day_off == 0 else rng.sample(slots_today, rng.randint(4, 8))
                for (h, m) in sorted(chosen):
                    t = rng.choice([types["Follow-up"], types["Sick visit"], types["Annual physical"], types["New patient"],
                                    types["Telehealth follow-up"]])
                    start = datetime.combine(d, time(h, m), zone)
                    end = start + timedelta(minutes=t.duration_minutes)
                    if db.scalar(select(Appointment.id).where(Appointment.provider_id == prov.id, Appointment.start_at < end,
                                                              Appointment.end_at > start, Appointment.status != "cancelled")):
                        continue
                    p = rng.choice(pool)
                    if db.scalar(select(Appointment.id).where(Appointment.patient_id == p.id, Appointment.start_at < end,
                                                              Appointment.end_at > start)):
                        continue
                    status = "scheduled"
                    if day_off == 0:
                        local_now = now().astimezone(zone)
                        if start < local_now - timedelta(minutes=40):
                            status = rng.choice(["checked_out", "checked_out", "no_show"])
                        elif start < local_now + timedelta(minutes=30):
                            status = rng.choice(["checked_in", "roomed"])
                        else:
                            status = rng.choice(["scheduled", "confirmed"])
                    elif rng.random() < 0.4:
                        status = "confirmed"
                    a = Appointment(organization_id=org.id, clinic_id=clinic.id, patient_id=p.id, provider_id=prov.id,
                                    appointment_type_id=t.id, start_at=start, end_at=end, status=status,
                                    mode="telehealth" if t.is_telehealth else "in_person",
                                    reason=rng.choice([c for _, _, c in ACUTE] + ["Medication review", "Blood pressure check", "Annual exam"]),
                                    booked_by_id=front_u.id)
                    if status in ("checked_in", "roomed", "checked_out"):
                        a.checked_in_at = start - timedelta(minutes=12)
                    if status in ("roomed",):
                        a.roomed_at, a.room = start - timedelta(minutes=4), rng.choice(clinic.rooms)
                    if status == "checked_out":
                        # Earlier today: a completed, signed visit.
                        past_visit(db, org, clinic, prov, p, t, start, nurse_u)
                        continue
                    db.add(a)
                    db.flush()

        seed_history(db, org, {chen.id: chen, okafor.id: okafor}, nurse_u)

        # ---- Hospital (Milestone A/B): structure + department-scoped staff ----
        from app.seed_hospital import seed_hospital

        hstaff = {
            "hospitaladmin": member(db, user(db, "hospitaladmin@harborview.dev", "Avery", "Grant"), org, "hospital_admin"),
            "pharmacist": member(db, user(db, "pharmacist@harborview.dev", "Noah", "Fischer", "PharmD"), org, "pharmacist"),
            "lab": member(db, user(db, "lab@harborview.dev", "Imani", "Brooks", "MLS"), org, "lab_tech"),
            "radiology": member(db, user(db, "radiology@harborview.dev", "Elena", "Sato", "MD"), org, "radiologist", "radiology_tech"),
            "bedmanager": member(db, user(db, "bedmanager@harborview.dev", "Chris", "Morgan", "RN"), org, "bed_manager"),
            "insurance": member(db, user(db, "insurance@harborview.dev", "Riley", "Nguyen"), org, "insurance_specialist"),
            "nurse_ms": member(db, user(db, "nurse.kim@harborview.dev", "Grace", "Kim", "RN"), org, "nurse"),
        }
        ed_doc_u = user(db, "dr.santos@harborview.dev", "Rafael", "Santos", "MD")
        hstaff["ed_doc"] = member(db, ed_doc_u, org, "doctor")
        provider(db, ed_doc_u, org, "Emergency Medicine", "MD", "rose", "1356432980")
        seed_hospital(db, org, [downtown, north], hstaff)

        # ---- Org 2: Lakeside Pediatrics (tenant isolation) ----
        org2 = Organization(name="Lakeside Pediatrics", slug="lakeside", settings={"synthetic_data": True, "mrn_seq": 500000})
        db.add(org2)
        db.flush()
        lake_clinic = Clinic(organization_id=org2.id, name="Lakeside Main", code="LKM", timezone="America/Chicago", rooms=["Room 1", "Room 2"])
        db.add(lake_clinic)
        db.flush()
        lake_u = user(db, "dr.lake@lakeside.dev", "Priya", "Lakshmanan", "MD")
        member(db, lake_u, org2, "doctor", "clinic_admin")
        lake_prov = provider(db, lake_u, org2, "Pediatrics", "MD", "emerald", "1679576722")
        availability(db, org2, lake_prov, lake_clinic, range(0, 5))
        db.add(AppointmentType(organization_id=org2.id, name="Well child", duration_minutes=30, color="emerald"))
        for i in range(8):
            p = make_patient(db, org2, lake_clinic, lake_prov, 500001 + i, dob=date(rng.randint(2010, 2024), rng.randint(1, 12), 5))
            chart(db, org2, p, lake_u)
        org2.settings = {**org2.settings, "mrn_seq": 500008}

        db.commit()
        print("Seeded synthetic data. Dev password for all accounts:", DEV_PASSWORD)
    finally:
        db.close()


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
