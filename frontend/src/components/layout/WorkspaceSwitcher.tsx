import { BriefcaseMedical, Check, ChevronDown } from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/menu";
import { useAuth } from "@/lib/auth";
import { ROLE_LABELS, type Role } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Header role switcher ("workspaces"). One signed-in person chooses which hospital role they are working in; the sidebar,
 * dashboard and actions follow, and the server enforces that role on every request (X-Acting-Role). Shown only to people
 * the server lists workspaces for: a platform Super Admin (all 14 roles) or someone holding several roles.
 */
export function WorkspaceSwitcher({ className }: { className?: string }) {
  const { baseMembership, workspace, workspaces, switchWorkspace } = useAuth();
  const navigate = useNavigate();
  if (!baseMembership || workspaces.length < 2) return null;
  // With no selection the person works with their own roles; a single own role reads as that workspace.
  const own = baseMembership.roles;
  const current: Role | null = workspace ?? (own.length === 1 ? own[0] : null);
  const label = current ? ROLE_LABELS[current] : "All my roles";
  const choose = (role: Role | null) => {
    switchWorkspace(role && own.length === 1 && own[0] === role ? null : role);
    navigate(role === "patient" ? "/portal" : "/", { replace: true });
  };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button data-testid="workspace-switcher" aria-label={`Workspace: ${label}. Switch workspace`}
          className={cn("flex h-9 min-w-0 max-w-28 shrink items-center gap-1.5 rounded-md border border-control bg-card px-2 text-left sm:max-w-none sm:gap-2 sm:px-2.5 text-table hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50", className)}>
          <BriefcaseMedical className="size-4 shrink-0 text-primary" aria-hidden />
          <span className="hidden text-muted-foreground lg:inline">Workspace:</span>
          <span className="min-w-0 truncate font-semibold text-heading" data-testid="workspace-current">{label}</span>
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-[70vh] w-64 overflow-y-auto">
        <DropdownMenuLabel>Work as</DropdownMenuLabel>
        {own.length > 1 && (
          <>
            <DropdownMenuItem onSelect={() => choose(null)}>
              <span className="flex-1">All my roles</span>
              {current === null && <Check className="!text-primary" />}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
          </>
        )}
        {workspaces.map((w) => (
          <DropdownMenuItem key={w.role} onSelect={() => choose(w.role)} data-testid={`workspace-${w.role}`}>
            <span className="flex-1 truncate">{w.label}</span>
            {current === w.role && <Check className="!text-primary" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
