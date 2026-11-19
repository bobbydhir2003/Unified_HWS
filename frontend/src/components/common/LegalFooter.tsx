import { Link } from "react-router-dom";
import { COPYRIGHT_NOTICE } from "@/lib/legal";
import { cn } from "@/lib/utils";

/** Unobtrusive copyright line used by every layout (staff shell, portal, sign-in). */
export function LegalFooter({ className, linkTo = "/about" }: { className?: string; linkTo?: string }) {
  return (
    <footer className={cn("flex flex-wrap items-center justify-center gap-x-3 gap-y-1 px-4 py-4 text-[11.5px] text-muted-foreground", className)}>
      <span>{COPYRIGHT_NOTICE}</span>
      <span aria-hidden>·</span>
      <Link to={linkTo} className="hover:text-foreground hover:underline">About &amp; legal</Link>
    </footer>
  );
}
