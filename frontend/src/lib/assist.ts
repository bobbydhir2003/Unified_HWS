/**
 * HMS Intelligence — the display identities of the ten department AI agents (marketing names, not trademark-cleared).
 * Internal keys (and stored configurations, conversations, approvals) are unchanged; only what people see changes.
 * The previous names stay visible as a secondary label in Agent Studio.
 */
export const ASSIST: Record<string, { name: string; role: string; previous: string; summary: string }> = {
  insurance_guardian: { name: "Aurelia", role: "Insurance & Coverage AI", previous: "Insurance Guardian", summary: "Coverage problems before visits" },
  pharmacy_watchdog: { name: "Veyra", role: "Pharmacy & Inventory AI", previous: "Pharmacy Watchdog", summary: "Stock alerts and pharmacy actions" },
  discharge_coordination: { name: "Elara", role: "Discharge Coordination AI", previous: "Discharge Coordination", summary: "What still blocks a discharge" },
  hospital_operations: { name: "Orion", role: "Hospital Operations AI", previous: "Hospital Operations", summary: "Operational bottlenecks" },
  claims_review: { name: "Valora", role: "Billing & Claims AI", previous: "Claims Review", summary: "Possibly missing billing information" },
  patient_communication: { name: "Liora", role: "Patient Communication AI", previous: "Patient Communication", summary: "Administrative patient messages" },
  staff_scheduling: { name: "Nexa", role: "Staff Scheduling AI", previous: "Staff Scheduling", summary: "Staffing gaps and eligible options" },
  doctor_assistant: { name: "Aster", role: "Patient Chart AI", previous: "Doctor Assistant", summary: "Cited answers from one patient's chart" },
  medical_scribe: { name: "Sonara", role: "Medical Scribe AI", previous: "Medical Scribe", summary: "Draft notes from consented visits" },
  document_intelligence: { name: "Lucent", role: "Document Intelligence AI", previous: "Document Intelligence", summary: "Classify and extract documents for review" },
};

export const INTELLIGENCE_NAME = "HMS Intelligence";

export function assistName(key: string | null | undefined, fallback?: string): string {
  return (key && ASSIST[key]?.name) || fallback || (key ? key.replace(/_/g, " ") : "AI assistant");
}

export function assistRole(key: string | null | undefined): string | undefined {
  return key ? ASSIST[key]?.role : undefined;
}
