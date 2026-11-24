import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, OctagonX } from "lucide-react";
import { toast } from "sonner";
import { LoadingRows, toastError, useConfirm } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { get, put } from "@/lib/api";

type Owner = { platform: { ai_disabled: boolean; key_configured: boolean }; note: string };

/** Platform owner (platform Super Admin only): the emergency switch for all platform AI. */
export function OwnerAICard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["ai", "owner"], queryFn: () => get<Owner>("/admin/ai-owner") });
  const { confirm, dialog } = useConfirm();
  if (q.isLoading) return <Card><CardContent><LoadingRows rows={2} /></CardContent></Card>;
  if (!q.data) return null;
  const o = q.data;
  const refresh = (d: Owner) => { qc.setQueryData(["ai", "owner"], d); qc.invalidateQueries({ queryKey: ["ai", "settings"] }); };
  return (
    <Card data-testid="owner-ai-card">
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2"><OctagonX className="size-4" />Platform AI controls</CardTitle>
        {o.platform.ai_disabled ? <Badge variant="danger">All AI off</Badge> : <Badge variant="neutral">On</Badge>}
      </CardHeader>
      <CardContent className="space-y-3 text-table">
        <p className="text-muted-foreground">{o.note}</p>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
          <p className="flex items-center gap-2"><Lock className="size-4" />All platform AI: {o.platform.ai_disabled ? <strong className="text-destructive">switched off</strong> : "on"}</p>
          <Button size="sm" variant={o.platform.ai_disabled ? "outline" : "destructive"} onClick={async () => {
            const off = !o.platform.ai_disabled;
            if (off && !(await confirm({ title: "Switch off all AI?", description: "Every AI feature shows its labelled simulation until you switch it back on. Rules, tasks and notifications keep working.", confirmLabel: "Switch off", destructive: true }))) return;
            try { refresh(await put<Owner>("/admin/ai-owner/platform", { ai_disabled: off })); toast.success(off ? "All AI switched off" : "AI switched back on"); } catch (e) { toastError(e); }
          }}>{o.platform.ai_disabled ? "Switch AI back on" : "Emergency: switch off all AI"}</Button>
        </div>
      </CardContent>
      {dialog}
    </Card>
  );
}
