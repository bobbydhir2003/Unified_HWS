import * as React from "react";
import { cn } from "@/lib/utils";
import { Label } from "./input";

type Props = {
  label: React.ReactNode;
  error?: string;
  hint?: React.ReactNode;
  required?: boolean;
  className?: string;
  children: React.ReactElement<{ id?: string; "aria-invalid"?: boolean; "aria-describedby"?: string }>;
};

/** Label + control + error/hint with correct aria wiring. */
export function Field({ label, error, hint, required, className, children }: Props) {
  const id = React.useId();
  const msgId = `${id}-msg`;
  const child = React.cloneElement(children, {
    id: children.props.id ?? id,
    "aria-invalid": !!error || undefined,
    "aria-describedby": error || hint ? msgId : undefined,
  });
  return (
    <div className={cn("grid gap-1.5", className)}>
      <Label htmlFor={children.props.id ?? id}>
        {label}
        {required && <span className="ml-0.5 text-destructive" aria-hidden>*</span>}
      </Label>
      {child}
      {error ? (
        <p id={msgId} role="alert" className="text-xs text-destructive">{error}</p>
      ) : hint ? (
        <p id={msgId} className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
