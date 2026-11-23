import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

/** Neutral tags and status pills. All text/background pairs meet 4.5:1 in light and dark. Pair colour with an icon or word. */
export const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-label font-medium whitespace-nowrap [&_svg]:size-3",
  {
    variants: {
      variant: {
        neutral: "border-border bg-muted text-muted-foreground",
        primary: "border-primary/20 bg-accent text-accent-foreground",
        success: "border-success/25 bg-success-soft text-success",
        warning: "border-warning/30 bg-warning-soft text-warning-foreground",
        danger: "border-destructive/25 bg-destructive-soft text-destructive",
        info: "border-primary/20 bg-info-soft text-accent-foreground",
        ai: "border-ai/25 bg-ai-soft text-ai",
        outline: "border-control text-foreground",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export function Badge({ className, variant, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
