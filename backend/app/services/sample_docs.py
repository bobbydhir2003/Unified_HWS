"""Generate clearly-labelled SYNTHETIC clinical PDFs for demonstrating document intake (and simulated inbound fax).

`fidelity` controls identity noise so reviewers see confident, ambiguous and unmatched cases.
"""

import random
from datetime import date, timedelta

from fpdf import FPDF

from app.models import Patient

FACILITIES = ["Bayside Diagnostic Labs (synthetic)", "Northshore Imaging Center (synthetic)",
              "St. Calloway Regional Hospital (synthetic)", "Riverside Cardiology Associates (synthetic)"]


def _pdf(lines: list[str]) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(180, 0, 0)
    pdf.cell(0, 6, "SYNTHETIC SAMPLE - NOT REAL PATIENT DATA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    for line in lines:
        if line.startswith("# "):
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 10, line[2:], new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5.5, line or " ", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _identity(p: Patient | None, fidelity: str, rng: random.Random) -> tuple[str, str, str]:
    if p is None or fidelity == "unknown":
        return f"{rng.choice(['Corwin', 'Delphine', 'Ignatius'])} {rng.choice(['Vale', 'Marchetti', 'Okonkwo'])}", \
            f"{rng.randint(1,12):02d}/{rng.randint(1,28):02d}/{rng.randint(1950,2005)}", ""
    dob = p.date_of_birth.strftime("%m/%d/%Y")
    name = f"{p.first_name} {p.last_name}"
    mrn = p.mrn
    if fidelity == "ambiguous":
        name = f"{p.first_name[0]}. {p.last_name}"
        mrn = ""
        if rng.random() < 0.5:
            d = p.date_of_birth + timedelta(days=rng.choice([1, 30, 365]))
            dob = d.strftime("%m/%d/%Y")
    return name, dob, mrn


def make_sample(kind: str, patient: Patient | None, fidelity: str = "exact", seed: int | None = None) -> tuple[bytes, str, str]:
    rng = random.Random(seed)
    name, dob, mrn = _identity(patient, fidelity, rng)
    when = (date.today() - timedelta(days=rng.randint(0, 10))).strftime("%m/%d/%Y")
    fac = rng.choice(FACILITIES)
    head = [f"Facility: {fac}", f"Patient Name: {name}", f"DOB: {dob}"] + ([f"MRN: {mrn}"] if mrn else [])
    if kind == "lab_result":
        a1c = round(rng.uniform(5.2, 9.1), 1)
        ldl = rng.randint(70, 190)
        glu = rng.randint(80, 180)
        k = round(rng.uniform(3.4, 5.4), 1)
        cr = round(rng.uniform(0.6, 1.4), 2)
        lines = ["# Laboratory Report", *head, f"Collected: {when}", "",
                 f"Hemoglobin A1c: {a1c} % ({'H' if a1c > 5.6 else 'N'}) [ref 4.0-5.6]",
                 f"Glucose, fasting: {glu} mg/dL ({'H' if glu > 99 else 'N'}) [ref 70-99]",
                 f"LDL Cholesterol: {ldl} mg/dL ({'H' if ldl > 129 else 'N'}) [ref 0-129]",
                 f"Creatinine: {cr} mg/dL ({'H' if cr > 1.3 else 'N'}) [ref 0.6-1.3]",
                 f"Potassium: {k} mmol/L ({'L' if k < 3.5 else 'H' if k > 5.1 else 'N'}) [ref 3.5-5.1]", "",
                 "Comments: Results reviewed by laboratory. Clinical correlation recommended."]
        title = "lab-report.pdf"
    elif kind == "imaging_report":
        lines = ["# Radiology Report", *head, f"Report Date: {when}", "Exam: XR Chest, 2 views", "",
                 "Findings: Lungs are clear. No focal consolidation, effusion or pneumothorax. Heart size normal.", "",
                 "Impression: No acute cardiopulmonary abnormality."]
        title = "radiology-report.pdf"
    elif kind == "discharge_summary":
        lines = ["# Discharge Summary", *head, f"Admission Date: {when}", f"Discharge Date: {when}", "",
                 "Discharge Diagnosis: Community-acquired pneumonia, improving.", "",
                 "Hospital Course: Treated with IV antibiotics, transitioned to oral therapy, afebrile 48 hours.", "",
                 "Discharge Medications:", "- Amoxicillin 875 mg twice daily for 5 days", "- Acetaminophen 500 mg every 6 hours as needed", "",
                 "Follow-up: Primary care within 7 days."]
        title = "discharge-summary.pdf"
    else:
        kind = "referral"
        lines = ["# Referral", *head, f"Date of Referral: {when}", "Referring Provider: Dr. Helen Abara, Riverside Cardiology (synthetic)", "",
                 "Reason for Referral: Patient seen for palpitations; Holter monitor unremarkable. Returning to primary care for "
                 "ongoing blood pressure management.", "", "Please schedule follow-up within 2 weeks."]
        title = "referral-letter.pdf"
    return _pdf(lines), title, fac
