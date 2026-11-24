"""Built-in order catalogs (subset). Behind `search_*` so a licensed source (e.g. RxNorm/First Databank, LOINC,
lab compendium) can replace them without touching callers. Codes shown are illustrative for development."""

MEDICATIONS = [
    # name, strengths, form, route, default sig, drug class (for allergy checks)
    ("Amoxicillin", ["250 mg", "500 mg", "875 mg"], "capsule", "oral", "1 capsule by mouth three times daily", "penicillin"),
    ("Amoxicillin-clavulanate", ["500-125 mg", "875-125 mg"], "tablet", "oral", "1 tablet by mouth twice daily", "penicillin"),
    ("Penicillin V potassium", ["250 mg", "500 mg"], "tablet", "oral", "1 tablet by mouth four times daily", "penicillin"),
    ("Cephalexin", ["250 mg", "500 mg"], "capsule", "oral", "1 capsule by mouth four times daily", "cephalosporin"),
    ("Azithromycin", ["250 mg", "500 mg"], "tablet", "oral", "500 mg on day 1, then 250 mg daily for 4 days", "macrolide"),
    ("Doxycycline", ["100 mg"], "capsule", "oral", "1 capsule by mouth twice daily", "tetracycline"),
    ("Sulfamethoxazole-trimethoprim", ["800-160 mg"], "tablet", "oral", "1 tablet by mouth twice daily", "sulfonamide"),
    ("Nitrofurantoin", ["100 mg"], "capsule", "oral", "1 capsule by mouth twice daily", "nitrofuran"),
    ("Ciprofloxacin", ["250 mg", "500 mg"], "tablet", "oral", "1 tablet by mouth twice daily", "fluoroquinolone"),
    ("Lisinopril", ["5 mg", "10 mg", "20 mg", "40 mg"], "tablet", "oral", "1 tablet by mouth once daily", "ace_inhibitor"),
    ("Losartan", ["25 mg", "50 mg", "100 mg"], "tablet", "oral", "1 tablet by mouth once daily", "arb"),
    ("Amlodipine", ["2.5 mg", "5 mg", "10 mg"], "tablet", "oral", "1 tablet by mouth once daily", "ccb"),
    ("Hydrochlorothiazide", ["12.5 mg", "25 mg"], "tablet", "oral", "1 tablet by mouth once daily", "thiazide"),
    ("Metoprolol succinate", ["25 mg", "50 mg", "100 mg"], "tablet", "oral", "1 tablet by mouth once daily", "beta_blocker"),
    ("Atorvastatin", ["10 mg", "20 mg", "40 mg", "80 mg"], "tablet", "oral", "1 tablet by mouth nightly", "statin"),
    ("Rosuvastatin", ["5 mg", "10 mg", "20 mg"], "tablet", "oral", "1 tablet by mouth daily", "statin"),
    ("Metformin", ["500 mg", "850 mg", "1000 mg"], "tablet", "oral", "1 tablet by mouth twice daily with meals", "biguanide"),
    ("Glipizide", ["5 mg", "10 mg"], "tablet", "oral", "1 tablet by mouth daily before breakfast", "sulfonylurea"),
    ("Levothyroxine", ["25 mcg", "50 mcg", "75 mcg", "100 mcg"], "tablet", "oral", "1 tablet by mouth daily on an empty stomach", "thyroid"),
    ("Omeprazole", ["20 mg", "40 mg"], "capsule", "oral", "1 capsule by mouth daily before breakfast", "ppi"),
    ("Sertraline", ["25 mg", "50 mg", "100 mg"], "tablet", "oral", "1 tablet by mouth daily", "ssri"),
    ("Escitalopram", ["5 mg", "10 mg", "20 mg"], "tablet", "oral", "1 tablet by mouth daily", "ssri"),
    ("Albuterol HFA", ["90 mcg/actuation"], "inhaler", "inhaled", "2 puffs every 4-6 hours as needed for wheezing", "beta_agonist"),
    ("Fluticasone nasal", ["50 mcg/spray"], "spray", "nasal", "2 sprays each nostril daily", "steroid_nasal"),
    ("Cetirizine", ["10 mg"], "tablet", "oral", "1 tablet by mouth daily", "antihistamine"),
    ("Ibuprofen", ["400 mg", "600 mg", "800 mg"], "tablet", "oral", "1 tablet by mouth every 8 hours as needed with food", "nsaid"),
    ("Naproxen", ["250 mg", "500 mg"], "tablet", "oral", "1 tablet by mouth twice daily as needed with food", "nsaid"),
    ("Acetaminophen", ["325 mg", "500 mg"], "tablet", "oral", "1-2 tablets by mouth every 6 hours as needed", "analgesic"),
    ("Cyclobenzaprine", ["5 mg", "10 mg"], "tablet", "oral", "1 tablet by mouth at bedtime as needed", "muscle_relaxant"),
    ("Benzonatate", ["100 mg", "200 mg"], "capsule", "oral", "1 capsule by mouth three times daily as needed for cough", "antitussive"),
    ("Prednisone", ["5 mg", "10 mg", "20 mg"], "tablet", "oral", "As directed (taper)", "corticosteroid"),
    ("Ondansetron", ["4 mg", "8 mg"], "tablet", "oral", "1 tablet by mouth every 8 hours as needed for nausea", "antiemetic"),
    ("Codeine-acetaminophen", ["30-300 mg"], "tablet", "oral", "1 tablet by mouth every 6 hours as needed", "opioid"),
    # Inpatient demonstration formulary (synthetic environment only; not a clinical formulary). High-alert classes need a witness.
    ("Heparin", ["5,000 units"], "injection", "subcutaneous", "5,000 units subcutaneously every 8 hours", "anticoagulant"),
    ("Insulin regular", ["4 units", "6 units", "8 units"], "injection", "subcutaneous", "per sliding scale before meals", "insulin"),
    ("Morphine", ["2 mg", "4 mg"], "injection", "intravenous", "2 mg IV every 4 hours as needed for severe pain", "opioid"),
    ("Ondansetron IV", ["4 mg"], "injection", "intravenous", "4 mg IV every 8 hours as needed for nausea", "antiemetic"),
    ("Ceftriaxone", ["1 g", "2 g"], "injection", "intravenous", "1 g IV every 24 hours", "cephalosporin"),
]

# Allergy substance keyword → drug classes it implies (basic cross-reactivity; not a substitute for a full DDI/allergy database)
ALLERGY_CLASSES = {
    "penicillin": {"penicillin", "cephalosporin"}, "amoxicillin": {"penicillin", "cephalosporin"},
    "sulfa": {"sulfonamide"}, "codeine": {"opioid"}, "nsaid": {"nsaid"}, "ibuprofen": {"nsaid"}, "aspirin": {"nsaid"},
    "cephalexin": {"cephalosporin"}, "macrolide": {"macrolide"}, "azithromycin": {"macrolide"},
}

LABS = [
    # code (LOINC-style), name, specimen, components: (name, unit, low, high, typical_low, typical_high)
    ("24323-8", "Comprehensive metabolic panel", "Serum", [
        ("Glucose", "mg/dL", 70, 99, 72, 160), ("BUN", "mg/dL", 7, 20, 8, 28), ("Creatinine", "mg/dL", 0.6, 1.3, 0.6, 1.6),
        ("Sodium", "mmol/L", 135, 145, 133, 146), ("Potassium", "mmol/L", 3.5, 5.1, 3.4, 5.4), ("ALT", "U/L", 7, 56, 10, 80)]),
    ("24320-4", "Basic metabolic panel", "Serum", [
        ("Glucose", "mg/dL", 70, 99, 72, 160), ("BUN", "mg/dL", 7, 20, 8, 28), ("Creatinine", "mg/dL", 0.6, 1.3, 0.6, 1.6),
        ("Sodium", "mmol/L", 135, 145, 133, 146), ("Potassium", "mmol/L", 3.5, 5.1, 3.4, 5.4)]),
    ("58410-2", "Complete blood count (CBC)", "Whole blood", [
        ("WBC", "10^3/uL", 4.0, 11.0, 3.8, 13.0), ("Hemoglobin", "g/dL", 12.0, 17.5, 10.8, 17.0), ("Platelets", "10^3/uL", 150, 400, 140, 420)]),
    ("57698-3", "Lipid panel", "Serum", [
        ("Total cholesterol", "mg/dL", 0, 199, 150, 260), ("LDL cholesterol", "mg/dL", 0, 129, 70, 190),
        ("HDL cholesterol", "mg/dL", 40, 100, 32, 75), ("Triglycerides", "mg/dL", 0, 149, 70, 260)]),
    ("4548-4", "Hemoglobin A1c", "Whole blood", [("Hemoglobin A1c", "%", 4.0, 5.6, 5.0, 9.5)]),
    ("3016-3", "TSH", "Serum", [("TSH", "mIU/L", 0.4, 4.0, 0.3, 6.5)]),
    ("24356-8", "Urinalysis", "Urine", [("Specific gravity", "", 1.005, 1.030, 1.005, 1.030), ("pH", "", 4.5, 8.0, 5.0, 7.5)]),
    ("94500-6", "SARS-CoV-2 RNA (PCR)", "Nasopharyngeal swab", [("SARS-CoV-2 RNA", "", None, None, None, None)]),
    ("78012-2", "Rapid strep A antigen", "Throat swab", [("Strep A antigen", "", None, None, None, None)]),
]

IMAGING = [
    ("71046", "XR chest, 2 views"), ("73562", "XR knee, 3 views"), ("72100", "XR lumbar spine, 2-3 views"),
    ("74177", "CT abdomen/pelvis with contrast"), ("70450", "CT head without contrast"), ("72148", "MRI lumbar spine without contrast"),
    ("76700", "US abdomen, complete"), ("77067", "Screening mammogram, bilateral"), ("93306", "Echocardiogram, complete"),
]

SPECIALISTS = [
    ("Cardiology", "Dr. Helen Abara", "Riverside Cardiology Associates (synthetic)", "(555) 301-2000"),
    ("Cardiology", "Dr. Marco Ruiz", "Harborview Heart Center (synthetic)", "(555) 301-2100"),
    ("Dermatology", "Dr. Aiko Tanaka", "Clearview Dermatology (synthetic)", "(555) 302-3000"),
    ("Endocrinology", "Dr. Samuel Osei", "Bayside Endocrine Clinic (synthetic)", "(555) 303-4000"),
    ("Gastroenterology", "Dr. Leila Haddad", "Port Harbor GI (synthetic)", "(555) 304-5000"),
    ("Orthopedics", "Dr. Ben Kowalski", "Northshore Orthopedics (synthetic)", "(555) 305-6000"),
    ("Physical therapy", "Movewell PT team", "Movewell Physical Therapy (synthetic)", "(555) 306-7000"),
    ("Psychiatry", "Dr. Nadia Petrova", "Lighthouse Behavioral Health (synthetic)", "(555) 307-8000"),
    ("Pulmonology", "Dr. Owen Fairbanks", "Coastal Lung Specialists (synthetic)", "(555) 308-9000"),
    ("Neurology", "Dr. Priya Raman", "Harbor Neurology (synthetic)", "(555) 309-1000"),
]


def search_medications(q: str):
    ql = q.lower()
    return [{"name": n, "strengths": s, "form": f, "route": r, "default_sig": sig, "drug_class": c}
            for n, s, f, r, sig, c in MEDICATIONS if ql in n.lower()][:15]


def medication(name: str):
    return next((m for m in search_medications(name) if m["name"].lower() == name.lower()), None)


def search_labs(q: str):
    ql = q.lower()
    return [{"code": c, "name": n, "specimen": sp, "components": [x[0] for x in comps]}
            for c, n, sp, comps in LABS if ql in n.lower() or ql in c][:15]


def lab(code: str):
    return next(((c, n, sp, comps) for c, n, sp, comps in LABS if c == code), None)


def search_imaging(q: str):
    ql = q.lower()
    return [{"code": c, "name": n} for c, n in IMAGING if ql in n.lower() or ql in c][:15]


def imaging(code: str):
    return next(({"code": c, "name": n} for c, n in IMAGING if c == code), None)


def specialists(specialty: str | None = None):
    return [{"specialty": s, "name": n, "organization": o, "phone": p} for s, n, o, p in SPECIALISTS
            if not specialty or s.lower() == specialty.lower()]
