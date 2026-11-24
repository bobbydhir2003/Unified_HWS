export type Role =
  | "super_admin" | "hospital_admin" | "clinic_admin" | "doctor" | "nurse" | "receptionist" | "billing" | "insurance_specialist"
  | "pharmacist" | "lab_tech" | "radiology_tech" | "radiologist" | "bed_manager" | "patient";

export const ROLE_LABELS: Record<Role, string> = {
  super_admin: "Super Admin",
  hospital_admin: "Hospital Administrator",
  clinic_admin: "Facility Admin",
  doctor: "Doctor",
  nurse: "Nurse / MA",
  receptionist: "Receptionist",
  billing: "Billing Specialist",
  insurance_specialist: "Insurance Specialist",
  pharmacist: "Pharmacist",
  lab_tech: "Laboratory Technologist",
  radiology_tech: "Radiology Technologist",
  radiologist: "Radiologist",
  bed_manager: "Bed Manager",
  patient: "Patient",
};

export const STAFF_ROLES: Role[] = ["hospital_admin", "clinic_admin", "doctor", "nurse", "receptionist", "billing", "insurance_specialist",
  "pharmacist", "lab_tech", "radiology_tech", "radiologist", "bed_manager"];

export type ClinicBrief = { id: string; name: string; code: string; timezone: string };

export type Membership = {
  organization_id: string;
  organization_name: string;
  roles: Role[];
  permissions: string[];
  clinics: ClinicBrief[];
  provider_id: string | null;
  patient_id: string | null;
};

export type User = {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  title: string | null;
  phone: string | null;
  is_superadmin: boolean;
  mfa_enabled: boolean;
  last_login_at: string | null;
  preferences: Record<string, unknown>;
};

export type Me = { user: User; memberships: Membership[]; mfa_enrollment_required: boolean; demo_hospital?: boolean };

export type Page<T> = { items: T[]; total: number; page: number; page_size: number };

export type Insurance = {
  id: string;
  priority: "primary" | "secondary" | "tertiary";
  payer_name: string;
  plan_name: string | null;
  member_id: string;
  group_number: string | null;
  subscriber_name: string | null;
  subscriber_relation: string;
  effective_date: string | null;
  termination_date: string | null;
  is_active: boolean;
  eligibility_status: string;
  eligibility_checked_at: string | null;
};

export type Patient = {
  id: string;
  mrn: string;
  first_name: string;
  middle_name: string | null;
  last_name: string;
  preferred_name: string | null;
  date_of_birth: string;
  sex_at_birth: "female" | "male" | "intersex" | "unknown";
  gender_identity: string | null;
  pronouns: string | null;
  email: string | null;
  phone: string | null;
  phone_alt: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  preferred_language: string;
  marital_status: string | null;
  emergency_contact_name: string | null;
  emergency_contact_relation: string | null;
  emergency_contact_phone: string | null;
  primary_clinic_id: string | null;
  primary_provider_id: string | null;
  notes: string | null;
  status: "active" | "inactive" | "deceased";
  is_restricted: boolean;
  has_portal_access: boolean;
  created_at: string;
  updated_at: string;
  insurances: Insurance[];
};

export type PatientListItem = Pick<
  Patient,
  "id" | "mrn" | "first_name" | "last_name" | "preferred_name" | "date_of_birth" | "sex_at_birth" | "phone" | "email" | "status" | "is_restricted"
> & { primary_provider_name: string | null; last_visit_at: string | null };

export type AppointmentType = { id: string; name: string; duration_minutes: number; color: string; is_telehealth: boolean; is_active: boolean };

export type Provider = {
  id: string;
  user_id: string;
  name: string;
  credentials: string | null;
  specialty: string | null;
  color: string;
  accepts_new_patients: boolean;
  availability: { clinic_id: string; weekday: number; start_time: string; end_time: string }[];
};

export type AppointmentStatus =
  | "scheduled" | "confirmed" | "checked_in" | "roomed" | "in_progress" | "completed" | "checked_out" | "cancelled" | "no_show";

export type Appointment = {
  id: string;
  patient: { id: string; name: string; mrn: string; date_of_birth: string; sex_at_birth: string; phone: string | null; is_restricted: boolean };
  provider: { id: string; name: string };
  clinic: { id: string; name: string };
  appointment_type: AppointmentType | null;
  start_at: string;
  end_at: string;
  status: AppointmentStatus;
  mode: "in_person" | "telehealth";
  reason: string | null;
  notes: string | null;
  room: string | null;
  cancel_reason: string | null;
  checked_in_at: string | null;
  roomed_at: string | null;
  checked_out_at: string | null;
  encounter_id: string | null;
  created_at: string;
};

export type Allergy = {
  id: string; substance: string; category: string; reaction: string | null;
  severity: "mild" | "moderate" | "severe" | "life_threatening"; status: string; onset_date: string | null; created_at: string;
};
export type Medication = {
  id: string; name: string; dose: string | null; route: string | null; frequency: string | null; indication: string | null;
  status: string; start_date: string | null; end_date: string | null; source: string; created_at: string;
};
export type Problem = {
  id: string; code: string | null; description: string; status: string; is_chronic: boolean;
  onset_date: string | null; resolved_date: string | null; encounter_id: string | null; created_at: string;
};
export type HistoryEntry = {
  id: string; category: "medical" | "surgical" | "family" | "social"; condition: string; relation: string | null;
  details: string | null; occurred_on: string | null; created_at: string;
};
export type Vitals = {
  id: string; encounter_id: string | null; measured_at: string; systolic: number | null; diastolic: number | null;
  heart_rate: number | null; respiratory_rate: number | null; temperature_c: string | null; spo2: number | null;
  height_cm: string | null; weight_kg: string | null; pain_score: number | null; bmi: number | null; recorded_by_id: string | null;
};
export type UserRef = { id: string; name: string };
export type NoteContent = { subjective: string; objective: string; assessment: string; plan: string };
export type Note = {
  id: string; encounter_id: string; patient_id: string; note_type: string; title: string; status: "draft" | "signed";
  current_version: number; content: NoteContent; has_ai_content: boolean; ai_reviewed: boolean; author: UserRef;
  signed_by: UserRef | null; signed_at: string | null; created_at: string; updated_at: string;
  addenda: { id: string; body: string; author: UserRef; created_at: string }[];
};
export type Diagnosis = { id: string; code: string; description: string; rank: number };
export type Encounter = {
  id: string; patient_id: string;
  patient: { id: string; name: string; mrn: string; date_of_birth: string; sex_at_birth: string };
  provider: UserRef; provider_id: string; clinic_id: string; appointment_id: string | null; encounter_type: string;
  status: "in_progress" | "completed" | "cancelled"; chief_complaint: string | null; follow_up: string | null;
  started_at: string; completed_at: string | null; diagnoses: Diagnosis[]; note_status: string | null;
};
export type EncounterDetail = Encounter & { notes: Note[]; vitals: Vitals[] };
export type Template = { id: string; name: string; note_type: string; specialty: string | null; content: NoteContent; is_active: boolean };
