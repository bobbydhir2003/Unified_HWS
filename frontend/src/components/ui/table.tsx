import * as React from "react";
import { cn } from "@/lib/utils";

/** Data tables. Row height and cell padding follow the density setting (Comfortable / Compact). Numbers: add `num`. */
export function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div className="relative w-full overflow-x-auto scrollbar-thin">
      <table className={cn("w-full caption-bottom text-table", className)} {...props} />
    </div>
  );
}
export function THead({ className, ...props }: React.ComponentProps<"thead">) {
  return <thead className={cn("sticky top-0 z-[1] bg-subtle [&_tr]:border-b", className)} {...props} />;
}
export function TBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}
export function TR({ className, ...props }: React.ComponentProps<"tr">) {
  return <tr className={cn("border-b transition-colors data-[clickable=true]:cursor-pointer data-[clickable=true]:hover:bg-muted/60 data-[selected=true]:bg-accent/60", className)} {...props} />;
}
export function TH({ className, ...props }: React.ComponentProps<"th">) {
  return <th className={cn("h-9 whitespace-nowrap px-(--cell-x) text-left align-middle text-label font-medium text-muted-foreground", className)} {...props} />;
}
export function TD({ className, ...props }: React.ComponentProps<"td">) {
  return <td className={cn("px-(--cell-x) py-(--row-y) align-middle", className)} {...props} />;
}
