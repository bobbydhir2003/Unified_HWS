"""Static presentation profile of each HMS Assist agent (department, suggested prompts, what it never does, default task
role). What an agent CAN do is never taken from here: capabilities shown to a user are derived at request time from the
agent's allowed tools AND the user's permissions (see services/assist.capabilities)."""

PROFILES: dict[str, dict] = {
    "insurance_guardian": {
        "department": "Insurance & registration", "default_role": "insurance_specialist",
        "prompts": {"case": ["Explain this case", "Why is the payer unreachable?", "Show the latest payer-check evidence",
                             "What should we do next?", "Prepare a follow-up task", "Draft an insurance information request",
                             "What happened with my previous proposal?"],
                    "patient": ["What is this patient's coverage state?", "Show recent eligibility checks", "Re-check eligibility"],
                    "workspace": ["Summarize open coverage issues, most urgent first", "Which visits are at risk this week?"]},
        "never": ["Confirm coverage on a payer's behalf (payer checks are simulated)", "Override coverage holds", "Approve its own proposals"],
    },
    "pharmacy_watchdog": {
        "department": "Pharmacy", "default_role": "pharmacist",
        "prompts": {"case": ["Explain this stock alert", "What is the reorder recommendation?", "Is there an open purchase request?",
                             "Prepare a follow-up task for a pharmacist"],
                    "inventory_item": ["How many days of supply are left?", "Show recent purchase requests", "Prepare a follow-up task"],
                    "workspace": ["Summarize stock and expiry risks today", "Which items need pharmacy review first?"]},
        "never": ["Prescribe, verify, dispense, administer or waste medication", "Receive or adjust stock", "Approve or place purchases"],
    },
    "discharge_coordination": {
        "department": "Inpatient & discharge", "default_role": "nurse",
        "prompts": {"stay": ["What is this discharge waiting on?", "Who owns each open item?", "Prepare a coordination task"],
                    "case": ["Explain this discharge delay", "Prepare a coordination task"],
                    "workspace": ["Summarize discharges waiting today", "Which discharges are blocked on nursing?"]},
        "never": ["Decide clinical readiness", "Order or complete a discharge", "Approve discharge instructions"],
    },
    "hospital_operations": {
        "department": "Command Center", "default_role": "hospital_admin",
        "prompts": {"case": ["Explain this case", "What is it waiting on?", "Add a note to the case", "Prepare a follow-up task"],
                    "workspace": ["Explain today's bottlenecks", "What changed in the last 7 days?", "Which cases are overdue?"]},
        "never": ["Assign beds, transfer or discharge patients", "Change clinical records", "Resolve cases on its own"],
    },
    "claims_review": {
        "department": "Billing & claims", "default_role": "billing",
        "prompts": {"case": ["Why is this claim on hold?", "What information is missing?", "Prepare a billing review task"],
                    "claim": ["Summarize this claim", "List the open findings", "Re-scrub this claim", "Prepare a billing review task"],
                    "workspace": ["Which claims need attention and why?", "Summarize claims on hold"]},
        "never": ["Invent or change codes", "Edit, submit, void or appeal claims", "Contact payers"],
    },
    "patient_communication": {
        "department": "Patient messages", "default_role": "receptionist",
        "prompts": {"message_thread": ["Summarize this conversation", "Draft an administrative reply", "What is the patient asking for?"],
                    "patient": ["Draft an insurance reminder", "Draft an appointment reminder"],
                    "case": ["Draft a message to the patient about this case"],
                    "workspace": ["Which patients may need an administrative reminder?"]},
        "never": ["Send any message without staff approval", "Give clinical advice", "Message restricted charts"],
    },
    "staff_scheduling": {
        "department": "Staff roster", "default_role": "hospital_admin",
        "prompts": {"case": ["Explain this staffing gap", "Who could cover it?", "Prepare a task for the staffing manager"],
                    "workspace": ["Which departments are short in the next 48 hours?", "Who could cover the first gap?"]},
        "never": ["Assign, cancel or swap shifts", "Override credential, rest or hour limits", "Approve time off"],
    },
    "doctor_assistant": {
        "department": "Patient chart", "default_role": None,
        "prompts": {"patient": ["Summarize this patient's history", "List current medications", "What allergies are recorded?",
                                "What happened at the last visit?", "Show recent lab results"],
                    "workspace": ["What can you help me with?", "What appointments do I have today?", "How can I find my unfinished encounters?",
                                  "Explain the difference between a draft and a signed note"]},
        "never": ["Diagnose, prescribe or order", "Sign or change documentation", "Use information outside this chart"],
    },
    "medical_scribe": {
        "department": "Encounter documentation", "default_role": None,
        "prompts": {"scribe_session": ["Where in the transcript does the plan come from?", "What did the patient say about symptoms?",
                                       "Shorten the assessment section"]},
        "never": ["Apply the draft to the note or sign it", "Record without consent", "Add facts that are not in the transcript"],
    },
    "document_intelligence": {
        "department": "Document review", "default_role": "receptionist",
        "prompts": {"document": ["Why was it classified this way?", "Do the identifiers match a patient?", "What is uncertain in this extraction?",
                                 "Prepare a routing task"]},
        "never": ["File, reject or merge documents", "Change patient records from unverified extraction"],
    },
}
