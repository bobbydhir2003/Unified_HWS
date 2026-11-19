import "./index.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, Outlet, RouterProvider, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { EmptyState } from "@/components/common";
import { AppShell } from "@/components/layout/AppShell";
import { TooltipProvider } from "@/components/ui/menu";
import { AccountPage } from "@/features/account/AccountPage";
import { AuditPage, OrganizationsPage, OutboxPage, SystemPage } from "@/features/admin/AdminPages";
import { ClinicsPage, SchedulingSetupPage } from "@/features/admin/ClinicsPages";
import { StaffPage } from "@/features/admin/StaffPage";
import { AcceptInvitePage, ForgotPasswordPage, LoginPage, ResetPasswordPage } from "@/features/auth/AuthPages";
import { Dashboard } from "@/features/dashboard/Dashboard";
import { DocumentReview } from "@/features/documents/DocumentReview";
import { DocumentsPage } from "@/features/documents/DocumentsPage";
import { OrdersPage } from "@/features/orders/OrdersPages";
import { MessagesPage } from "@/features/messages/MessagesPage";
import { VideoVisit } from "@/features/telehealth/VideoVisit";
import { EncounterPage } from "@/features/encounters/EncounterPage";
import { EncountersList } from "@/features/encounters/EncountersList";
import { PatientChart } from "@/features/patients/PatientChart";
import { NewPatientPage } from "@/features/patients/PatientForm";
import { PatientsList } from "@/features/patients/PatientsList";
import { PortalHome } from "@/features/portal/PortalHome";
import { FrontDesk } from "@/features/schedule/FrontDesk";
import { SchedulePage } from "@/features/schedule/SchedulePage";
import { ApiError } from "@/lib/api";
import { AuthProvider, useAuth } from "@/lib/auth";

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
        <span className="text-[13px]">Loading workspace…</span>
      </div>
    </div>
  );
}

function RequireAuth() {
  const { status, me, membership } = useAuth();
  const loc = useLocation();
  if (status === "loading") return <Splash />;
  if (status === "anonymous") return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (me?.mfa_enrollment_required && loc.pathname !== "/account") return <Navigate to="/account?mfa=required" replace />;
  if (!membership && !me?.user.is_superadmin) {
    return <EmptyState icon={ShieldAlert} title="No active organization" description="Your account isn't linked to an organization. Contact your administrator." className="min-h-dvh" />;
  }
  return <Outlet />;
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
  return <Dashboard />;
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
      { path: "/login", element: <LoginPage /> },
      { path: "/forgot-password", element: <ForgotPasswordPage /> },
    ],
  },
  { path: "/reset-password", element: <ResetPasswordPage /> },
  { path: "/accept-invite", element: <AcceptInvitePage /> },
  {
    element: <RequireAuth />,
    children: [
      { path: "/portal/*", element: <PortalHome /> },
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
