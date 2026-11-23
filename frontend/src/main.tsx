/* © 2026 Sidra Riaz Awan. All rights reserved. HMS Workflows — unified hospital management system. */
import "./index.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, Outlet, RouterProvider, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { EmptyState } from "@/components/common";
import { AppShell } from "@/components/layout/AppShell";
import { TooltipProvider } from "@/components/ui/menu";
import { AcceptInvitePage, ForgotPasswordPage, ResetPasswordPage } from "@/features/auth/AuthPages";
import { ApiError } from "@/lib/api";
import { AuthProvider, useAuth } from "@/lib/auth";

// Feature pages load on demand (route-level code splitting).
const PublicPages = () => import("@/features/public/PublicPages");
const HomePage = lazy(() => PublicPages().then((m) => ({ default: m.HomePage })));
const PlatformPage = lazy(() => PublicPages().then((m) => ({ default: m.PlatformPage })));
const AiAutomationPage = lazy(() => PublicPages().then((m) => ({ default: m.AiAutomationPage })));
const SolutionsPage = lazy(() => PublicPages().then((m) => ({ default: m.SolutionsPage })));
const PublicAboutPage = lazy(() => PublicPages().then((m) => ({ default: m.PublicAboutPage })));
const PublicLoginPage = lazy(() => PublicPages().then((m) => ({ default: m.PublicLoginPage })));
const AccountPage = lazy(() => import("@/features/account/AccountPage").then((m) => ({ default: m.AccountPage })));
const AuditPage = lazy(() => import("@/features/admin/AdminPages").then((m) => ({ default: m.AuditPage })));
const OrganizationsPage = lazy(() => import("@/features/admin/AdminPages").then((m) => ({ default: m.OrganizationsPage })));
const OutboxPage = lazy(() => import("@/features/admin/AdminPages").then((m) => ({ default: m.OutboxPage })));
const SystemPage = lazy(() => import("@/features/admin/AdminPages").then((m) => ({ default: m.SystemPage })));
const ClinicsPage = lazy(() => import("@/features/admin/ClinicsPages").then((m) => ({ default: m.ClinicsPage })));
const SchedulingSetupPage = lazy(() => import("@/features/admin/ClinicsPages").then((m) => ({ default: m.SchedulingSetupPage })));
const StaffPage = lazy(() => import("@/features/admin/StaffPage").then((m) => ({ default: m.StaffPage })));
const RoleHome = lazy(() => import("@/features/dashboard/RoleHome").then((m) => ({ default: m.RoleHome })));
const DocumentReview = lazy(() => import("@/features/documents/DocumentReview").then((m) => ({ default: m.DocumentReview })));
const DocumentsPage = lazy(() => import("@/features/documents/DocumentsPage").then((m) => ({ default: m.DocumentsPage })));
const OrdersPage = lazy(() => import("@/features/orders/OrdersPages").then((m) => ({ default: m.OrdersPage })));
const MessagesPage = lazy(() => import("@/features/messages/MessagesPage").then((m) => ({ default: m.MessagesPage })));
const VideoVisit = lazy(() => import("@/features/telehealth/VideoVisit").then((m) => ({ default: m.VideoVisit })));
const BillingPage = lazy(() => import("@/features/billing/BillingPage").then((m) => ({ default: m.BillingPage })));
const AIMonitoringPage = lazy(() => import("@/features/ai/AIPages").then((m) => ({ default: m.AIMonitoringPage })));
const AutomationPage = lazy(() => import("@/features/ai/AIPages").then((m) => ({ default: m.AutomationPage })));
const ReceptionistPage = lazy(() => import("@/features/ai/AIPages").then((m) => ({ default: m.ReceptionistPage })));
const CommandCenter = lazy(() => import("@/features/command/CommandCenter").then((m) => ({ default: m.CommandCenter })));
const AgentStudio = lazy(() => import("@/features/ai/AgentStudio").then((m) => ({ default: m.AgentStudio })));
const HelpPage = lazy(() => import("@/features/help/HelpPage").then((m) => ({ default: m.HelpPage })));
const InsightsPage = lazy(() => import("@/features/insights/InsightsPages").then((m) => ({ default: m.InsightsPage })));
const AIGovernancePage = lazy(() => import("@/features/ai/AgentStudio").then((m) => ({ default: m.AIGovernancePage })));
const AIWorkspace = lazy(() => import("@/features/ai/AIWorkspace").then((m) => ({ default: m.AIWorkspace })));
const OrSchedulePage = lazy(() => import("@/features/ops/OrRosterPages").then((m) => ({ default: m.OrSchedulePage })));
const RosterPage = lazy(() => import("@/features/ops/OrRosterPages").then((m) => ({ default: m.RosterPage })));
const RevenuePage = lazy(() => import("@/features/revenue/RevenuePage").then((m) => ({ default: m.RevenuePage })));
const RadiologyPage = lazy(() => import("@/features/radiology/RadiologyPage").then((m) => ({ default: m.RadiologyPage })));
const EquipmentPage = lazy(() => import("@/features/pharmacy/EquipmentPage").then((m) => ({ default: m.EquipmentPage })));
const LabPage = lazy(() => import("@/features/lab/LabPage").then((m) => ({ default: m.LabPage })));
const PharmacyPage = lazy(() => import("@/features/pharmacy/PharmacyPage").then((m) => ({ default: m.PharmacyPage })));
const EdBoard = lazy(() => import("@/features/ed/EdBoard").then((m) => ({ default: m.EdBoard })));
const BedBoard = lazy(() => import("@/features/inpatient/BedBoard").then((m) => ({ default: m.BedBoard })));
const InpatientsPage = lazy(() => import("@/features/inpatient/InpatientPages").then((m) => ({ default: m.InpatientsPage })));
const InpatientDetail = lazy(() => import("@/features/inpatient/InpatientPages").then((m) => ({ default: m.InpatientDetail })));
const NursingPage = lazy(() => import("@/features/inpatient/InpatientPages").then((m) => ({ default: m.NursingPage })));
const WorklistPage = lazy(() => import("@/features/ops/WorklistPage").then((m) => ({ default: m.WorklistPage })));
const MonitorsPage = lazy(() => import("@/features/ops/MonitorsPage").then((m) => ({ default: m.MonitorsPage })));
const InsuranceGuardianPage = lazy(() => import("@/features/insurance/InsuranceGuardian").then((m) => ({ default: m.InsuranceGuardianPage })));
const AISettingsPage = lazy(() => import("@/features/admin/AISettingsPage").then((m) => ({ default: m.AISettingsPage })));
const FacilitiesPage = lazy(() => import("@/features/admin/FacilitiesPage").then((m) => ({ default: m.FacilitiesPage })));
const TasksPage = lazy(() => import("@/features/ai/AIPages").then((m) => ({ default: m.TasksPage })));
const AnalyticsPage = lazy(() => import("@/features/analytics/AnalyticsPage").then((m) => ({ default: m.AnalyticsPage })));
const EncounterPage = lazy(() => import("@/features/encounters/EncounterPage").then((m) => ({ default: m.EncounterPage })));
const EncountersList = lazy(() => import("@/features/encounters/EncountersList").then((m) => ({ default: m.EncountersList })));
const PatientChart = lazy(() => import("@/features/patients/PatientChart").then((m) => ({ default: m.PatientChart })));
const NewPatientPage = lazy(() => import("@/features/patients/PatientForm").then((m) => ({ default: m.NewPatientPage })));
const PatientsList = lazy(() => import("@/features/patients/PatientsList").then((m) => ({ default: m.PatientsList })));
const PortalHome = lazy(() => import("@/features/portal/PortalHome").then((m) => ({ default: m.PortalHome })));
const FrontDesk = lazy(() => import("@/features/schedule/FrontDesk").then((m) => ({ default: m.FrontDesk })));
const SchedulePage = lazy(() => import("@/features/schedule/SchedulePage").then((m) => ({ default: m.SchedulePage })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: true,
      retry: (n, err) => !(err instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(err.status)) && n < 2,
    },
  },
});

function Splash() {
  return (
    <div className="grid min-h-dvh place-items-center">
      <div className="flex flex-col items-center gap-3 text-muted-foreground">
        <span className="size-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <span className="text-table">Loading workspace…</span>
      </div>
    </div>
  );
}

function RequireAuth() {
  const { status, me, membership } = useAuth();
  const loc = useLocation();
  if (status === "loading") return <Splash />;
  // Signed-out visitors at "/" get the public homepage (with its sign-in form); everything else requires sign-in.
  if (status === "anonymous") return loc.pathname === "/" ? <Suspense fallback={<Splash />}><HomePage /></Suspense> : <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (me?.mfa_enrollment_required && loc.pathname !== "/account") return <Navigate to="/account?mfa=required" replace />;
  if (!membership && !me?.user.is_superadmin) {
    return <EmptyState icon={ShieldAlert} title="No active organization" description="Your account isn't linked to an organization. Contact your administrator." className="min-h-dvh" />;
  }
  return <Outlet />;
}

/** /modules (the old Modules page) → /platform, mapping old per-module anchors to the matching capability area. */
const MODULE_ANCHORS: Record<string, string> = {
  patients: "clinical-care", scheduling: "clinical-care", ehr: "clinical-care", portal: "clinical-care", "group-clinical": "clinical-care",
  acute: "hospital-operations", beds: "hospital-operations", "group-operations": "hospital-operations",
  pharmacy: "diagnostics-pharmacy", diagnostics: "diagnostics-pharmacy", inventory: "diagnostics-pharmacy", "group-diagnostics": "diagnostics-pharmacy",
  revenue: "revenue", "group-revenue": "revenue", ai: "coordination", automation: "coordination", command: "coordination",
  analytics: "coordination", admin: "coordination", "group-ai": "coordination", "group-analytics": "coordination",
};
function ModulesRedirect() {
  const { hash } = useLocation();
  const key = decodeURIComponent(hash.replace(/^#/, ""));
  return <Navigate to={{ pathname: "/platform", hash: key ? `#${MODULE_ANCHORS[key] ?? key}` : "" }} replace />;
}

function PublicOnly() {
  const { status } = useAuth();
  if (status === "loading") return <Splash />;
  if (status === "authenticated") return <Navigate to="/" replace />;
  return <Outlet />;
}

function Perm({ perm, children }: { perm: string; children: React.ReactNode }) {
  const { can } = useAuth();
  if (!can(perm)) return <EmptyState icon={ShieldAlert} title="You don't have access to this page" description="Ask your clinic administrator if you need this permission." />;
  return <>{children}</>;
}

function Home() {
  const { membership } = useAuth();
  if (membership?.roles.length === 1 && membership.roles[0] === "patient") return <Navigate to="/portal" replace />;
  return <RoleHome />;
}

function StaffOnly() {
  const { membership } = useAuth();
  if (membership?.roles.length === 1 && membership.roles[0] === "patient") return <Navigate to="/portal" replace />;
  return <Outlet />;
}

const router = createBrowserRouter([
  {
    element: <PublicOnly />,
    children: [
      { path: "/login", element: <Suspense fallback={<Splash />}><PublicLoginPage /></Suspense> },
      { path: "/forgot-password", element: <ForgotPasswordPage /> },
    ],
  },
  { path: "/reset-password", element: <ResetPasswordPage /> },
  { path: "/about", element: <Suspense fallback={<Splash />}><PublicAboutPage /></Suspense> },
  { path: "/platform", element: <Suspense fallback={<Splash />}><PlatformPage /></Suspense> },
  { path: "/modules", element: <ModulesRedirect /> },
  { path: "/ai-automation", element: <Suspense fallback={<Splash />}><AiAutomationPage /></Suspense> },
  { path: "/solutions", element: <Suspense fallback={<Splash />}><SolutionsPage /></Suspense> },
  { path: "/accept-invite", element: <AcceptInvitePage /> },
  {
    element: <RequireAuth />,
    children: [
      { path: "/portal/*", element: <Suspense fallback={<Splash />}><PortalHome /></Suspense> },
      {
        element: <AppShell />,
        handle: { crumb: "Home" },
        path: "/",
        children: [
          { index: true, element: <Home /> },
          { path: "account", element: <AccountPage />, handle: { crumb: "Account" } },
          {
            element: <StaffOnly />,
            children: [
              { path: "front-desk", element: <Perm perm="schedule:read"><FrontDesk /></Perm>, handle: { crumb: "Front desk" } },
              { path: "schedule", element: <Perm perm="schedule:read"><SchedulePage /></Perm>, handle: { crumb: "Schedule" } },
              {
                path: "patients", handle: { crumb: "Patients" },
                children: [
                  { index: true, element: <Perm perm="patients:read"><PatientsList /></Perm> },
                  { path: "new", element: <Perm perm="patients:write"><NewPatientPage /></Perm>, handle: { crumb: "Register patient" } },
                  { path: ":patientId/*", element: <Perm perm="patients:read"><PatientChart /></Perm>, handle: { crumb: "Chart" } },
                ],
              },
              { path: "messages", element: <Perm perm="messages:use"><MessagesPage /></Perm>, handle: { crumb: "Messages" } },
              { path: "telehealth/:appointmentId", element: <Perm perm="clinical:read"><VideoVisit /></Perm>, handle: { crumb: "Video visit" } },
              { path: "analytics", element: <Perm perm="analytics:read"><AnalyticsPage /></Perm>, handle: { crumb: "Analytics" } },
              { path: "command", element: <Perm perm="cases:read"><CommandCenter /></Perm>, handle: { crumb: "Command Center" } },
              { path: "help", element: <HelpPage />, handle: { crumb: "Help & About" } },
              { path: "insights", element: <Perm perm="analytics:read"><InsightsPage /></Perm>, handle: { crumb: "Insights" } },
              { path: "agents", element: <Perm perm="ai:use"><AgentStudio /></Perm>, handle: { crumb: "Agent Studio" } },
              { path: "admin/ai-governance", element: <Perm perm="ai:manage"><AIGovernancePage /></Perm>, handle: { crumb: "AI governance" } },
              { path: "ai", element: <Perm perm="ai:use"><AIWorkspace /></Perm>, handle: { crumb: "AI assistants" } },
              { path: "or", element: <OrSchedulePage />, handle: { crumb: "Operating rooms" } },
              { path: "roster", element: <Perm perm="roster:self"><RosterPage /></Perm>, handle: { crumb: "Roster" } },
              { path: "revenue", element: <Perm perm="billing:read"><RevenuePage /></Perm>, handle: { crumb: "Claims & authorizations" } },
              { path: "radiology", element: <Perm perm="radiology:work"><RadiologyPage /></Perm>, handle: { crumb: "Radiology" } },
              { path: "equipment", element: <Perm perm="inventory:read"><EquipmentPage /></Perm>, handle: { crumb: "Equipment" } },
              { path: "lab", element: <Perm perm="clinical:read"><LabPage /></Perm>, handle: { crumb: "Laboratory" } },
              { path: "pharmacy", element: <Perm perm="inventory:read"><PharmacyPage /></Perm>, handle: { crumb: "Pharmacy & inventory" } },
              { path: "ed", element: <Perm perm="adt:read"><EdBoard /></Perm>, handle: { crumb: "Emergency" } },
              { path: "beds", element: <Perm perm="adt:read"><BedBoard /></Perm>, handle: { crumb: "Bed board" } },
              { path: "nursing", element: <Perm perm="adt:read"><NursingPage /></Perm>, handle: { crumb: "Nursing" } },
              {
                path: "inpatients", handle: { crumb: "Inpatients" },
                children: [
                  { index: true, element: <Perm perm="adt:read"><InpatientsPage /></Perm> },
                  { path: ":stayId", element: <Perm perm="adt:read"><InpatientDetail /></Perm>, handle: { crumb: "Stay" } },
                ],
              },
              { path: "worklist", element: <Perm perm="cases:read"><WorklistPage /></Perm>, handle: { crumb: "My work" } },
              { path: "insurance", element: <Perm perm="cases:read"><InsuranceGuardianPage /></Perm>, handle: { crumb: "Insurance Guardian" } },
              { path: "automation/monitors", element: <Perm perm="cases:read"><MonitorsPage /></Perm>, handle: { crumb: "Monitors & rules" } },
              { path: "admin/ai-settings", element: <Perm perm="org:manage"><AISettingsPage /></Perm>, handle: { crumb: "AI settings" } },
              { path: "admin/facilities", element: <Perm perm="clinic:manage"><FacilitiesPage /></Perm>, handle: { crumb: "Facilities" } },
              { path: "tasks", element: <Perm perm="patients:read"><TasksPage /></Perm>, handle: { crumb: "Tasks" } },
              { path: "automation", element: <Perm perm="messages:use"><AutomationPage /></Perm>, handle: { crumb: "Automation studio" } },
              { path: "receptionist", element: <Perm perm="schedule:write"><ReceptionistPage /></Perm>, handle: { crumb: "AI receptionist" } },
              { path: "admin/ai", element: <Perm perm="clinic:manage"><AIMonitoringPage /></Perm>, handle: { crumb: "AI monitoring" } },
              { path: "billing", element: <Perm perm="billing:read"><BillingPage /></Perm>, handle: { crumb: "Billing" } },
              { path: "orders", element: <Perm perm="clinical:read"><OrdersPage /></Perm>, handle: { crumb: "Orders" } },
              {
                path: "documents", handle: { crumb: "Documents" },
                children: [
                  { index: true, element: <Perm perm="documents:read"><DocumentsPage /></Perm> },
                  { path: ":documentId", element: <Perm perm="documents:read"><DocumentReview /></Perm>, handle: { crumb: "Review" } },
                ],
              },
              {
                path: "encounters", handle: { crumb: "Visits" },
                children: [
                  { index: true, element: <Perm perm="clinical:read"><EncountersList /></Perm> },
                  { path: ":encounterId", element: <Perm perm="clinical:read"><EncounterPage /></Perm>, handle: { crumb: "Visit" } },
                ],
              },
              { path: "admin/staff", element: <Perm perm="users:manage"><StaffPage /></Perm>, handle: { crumb: "Staff & roles" } },
              { path: "admin/clinics", element: <Perm perm="clinic:manage"><ClinicsPage /></Perm>, handle: { crumb: "Clinics" } },
              { path: "admin/scheduling", element: <Perm perm="clinic:manage"><SchedulingSetupPage /></Perm>, handle: { crumb: "Scheduling setup" } },
              { path: "admin/audit", element: <Perm perm="audit:read"><AuditPage /></Perm>, handle: { crumb: "Audit log" } },
              { path: "admin/outbox", element: <Perm perm="users:manage"><OutboxPage /></Perm>, handle: { crumb: "Message outbox" } },
              { path: "admin/system", element: <Perm perm="clinic:manage"><SystemPage /></Perm>, handle: { crumb: "System status" } },
              { path: "admin/organizations", element: <Perm perm="org:manage"><OrganizationsPage /></Perm>, handle: { crumb: "Organizations" } },
              { path: "*", element: <EmptyState title="Page not found" description="The page you're looking for doesn't exist." /> },
            ],
          },
        ],
      },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <TooltipProvider>
          <RouterProvider router={router} />
          <Toaster position="bottom-center" richColors closeButton toastOptions={{ className: "font-sans" }} />
        </TooltipProvider>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
