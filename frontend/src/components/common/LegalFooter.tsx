import { Link } from "react-router-dom";
import { COPYRIGHT_NOTICE } from "@/lib/legal";
import { cn } from "@/lib/utils";

/** Unobtrusive copyright line used by every layout (staff shell, portal, sign-in). */
export function LegalFooter({ className, linkTo = "/about", stacked }: { className?: string; linkTo?: string; stacked?: boolean }) {
  if (stacked) {
    return (
      <footer className={cn("space-y-0.5 text-label text-muted-foreground", className)}>
        <p>{COPYRIGHT_NOTICE}</p>
        <Link to={linkTo} className="hover:text-foreground hover:underline">About &amp; legal</Link>
      </footer>
    );
  }
  return (
    <footer className={cn("flex flex-wrap items-center justify-center gap-x-3 gap-y-1 px-4 py-4 text-label text-muted-foreground", className)}>
      <span>{COPYRIGHT_NOTICE}</span>
      <span aria-hidden>·</span>
      <Link to={linkTo} className="hover:text-foreground hover:underline">About &amp; legal</Link>
    </footer>
  );
}
