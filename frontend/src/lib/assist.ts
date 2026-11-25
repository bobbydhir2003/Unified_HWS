/**
 * HMS Assist — AI teammates for hospital workflows: the display family for the ten AI agents. Internal keys (and stored configurations) are unchanged
 * to avoid migration and compatibility risk; the previous names stay visible as a secondary label.
 */
export const ASSIST: Record<string, { name: string; previous: string; role: string }> = {
  insurance_guardian: { name: "HMS Assist · Coverage", previous: "Insurance Guardian", role: "Coverage problems before visits" },
  doctor_assistant: { name: "HMS Assist · Chart", previous: "Doctor Assistant", role: "Cited answers from one patient's chart" },
  medical_scribe: { name: "HMS Assist · Scribe", previous: "Medical Scribe", role: "Draft notes from consented visits" },
  document_intelligence: { name: "HMS Assist · Documents", previous: "Document Intelligence", role: "Classify and extract documents for review" },
  pharmacy_watchdog: { name: "HMS Assist · Pharmacy", previous: "Pharmacy Watchdog", role: "Stock alerts and pharmacy actions" },
  discharge_coordination: { name: "HMS Assist · Discharge", previous: "Discharge Coordination", role: "What still blocks a discharge" },
  hospital_operations: { name: "HMS Assist · Operations", previous: "Hospital Operations", role: "Operational bottlenecks" },
  claims_review: { name: "HMS Assist · Claims", previous: "Claims Review", role: "Possibly missing billing information" },
  patient_communication: { name: "HMS Assist · Patient Messages", previous: "Patient Communication", role: "Administrative patient messages" },
  staff_scheduling: { name: "HMS Assist · Staffing", previous: "Staff Scheduling", role: "Staffing gaps and eligible options" },
};

export function assistName(key: string | null | undefined, fallback?: string): string {
  return (key && ASSIST[key]?.name) || fallback || (key ? key.replace(/_/g, " ") : "AI assistant");
}
