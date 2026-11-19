import { ArrowLeft, Scale, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth";
import { CODE_SET_NOTICES, COPYRIGHT_NOTICE, PRODUCT_DESCRIPTION, PRODUCT_NAME, THIRD_PARTY } from "@/lib/legal";

/** About & legal — public (also reachable from the sign-in page). */
export function AboutPage() {
  const { status } = useAuth();
  return (
    <div className="mx-auto max-w-3xl space-y-4 px-4 py-8">
      <Link to={status === "authenticated" ? "/" : "/login"} className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" />Back</Link>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{PRODUCT_NAME}</h1>
        <p className="text-[13.5px] text-muted-foreground">{PRODUCT_DESCRIPTION} · version {import.meta.env.VITE_APP_VERSION ?? "development"}</p>
      </div>
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Scale className="size-4" />Copyright</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-[13.5px]">
          <p className="font-medium">{COPYRIGHT_NOTICE}</p>
          <p className="text-muted-foreground">This application's original source code, design and documentation are protected by copyright. No license is granted except as agreed in writing with the copyright holder.</p>
        </CardContent>
      </Card>
      <Card className="border-warning/40">
        <CardHeader><CardTitle className="flex items-center gap-2"><ShieldAlert className="size-4 text-warning" />Use limitations</CardTitle></CardHeader>
        <CardContent className="space-y-1 text-[13.5px] text-muted-foreground">
          <p>Development build for synthetic data only. It is not HIPAA-certified, not ONC-certified and not validated for clinical use.</p>
          <p>Integrations labeled “simulated” (payers, pharmacies, labs, PACS, messaging) do not connect to real systems. AI output is a draft that requires human review.</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Third-party software</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-[13.5px]">
          <p className="text-muted-foreground">Open-source components remain under their own licenses and copyrights, which are not affected by the notice above. Full license texts ship with each package.</p>
          <ul className="grid gap-x-6 gap-y-1 sm:grid-cols-2">{THIRD_PARTY.map((t) => <li key={t.name} className="flex justify-between gap-3"><span>{t.name}</span><span className="text-muted-foreground">{t.license}</span></li>)}</ul>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Clinical code sets</CardTitle></CardHeader>
        <CardContent><ul className="list-disc space-y-1 pl-5 text-[13px] text-muted-foreground">{CODE_SET_NOTICES.map((n) => <li key={n}>{n}</li>)}</ul></CardContent>
      </Card>
      <p className="pt-2 text-center text-[11.5px] text-muted-foreground">{COPYRIGHT_NOTICE}</p>
    </div>
  );
}
