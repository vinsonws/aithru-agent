import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { Markdown } from "@/components/Markdown";
import { ShieldQuestion, MessageCircleQuestion, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { approvalsApi, runsApi } from "@/lib/api";
import { useTranslation } from "react-i18next";
import type { InlineRequest } from "./useRunStream";

export function InlineRequestCard({ request }: { request: InlineRequest }) {
  const { t } = useTranslation("chat");
  const [reply, setReply] = React.useState("");
  const [comment, setComment] = React.useState("");

  const inputMutation = useMutation({
    mutationFn: (content: string) => runsApi.submitInput(request.runId, content),
  });

  const approvalMutation = useMutation({
    mutationFn: (decision: "approved" | "rejected"): Promise<unknown> => {
      if (request.kind === "external_approval") {
        return approvalsApi.resolveExternalApproval(request.runId, {
          decision,
          approval_id: request.approvalId,
          comment: comment || undefined,
        });
      }
      return approvalsApi.resolve(request.approvalId ?? request.id, {
        decision,
        comment: comment || undefined,
      });
    },
  });

  if (request.kind === "input") {
    return (
      <div className="rounded-md border border-warning/40 bg-warning/5 p-3">
        <div className="mb-2 flex items-center gap-2 text-sm font-medium text-warning">
          <MessageCircleQuestion className="h-4 w-4" />
          {t("inputRequestTitle")}
        </div>
        {request.prompt && (
          <div className="mb-2 text-sm text-foreground">
            <Markdown variant="chat">{request.prompt}</Markdown>
          </div>
        )}
        <p className="mb-2 text-xs text-muted-foreground">{t("inputRequestHint")}</p>
        <Textarea
          value={reply}
          onChange={(e) => setReply(e.target.value)}
          placeholder={t("replyPlaceholder")}
          className="mb-2"
        />
        <Button
          size="sm"
          disabled={!reply.trim() || inputMutation.isPending}
          onClick={() => reply.trim() && inputMutation.mutate(reply.trim())}
        >
          {t("send", { ns: "common" })}
        </Button>
      </div>
    );
  }

  // approval / external_approval
  return (
    <div className="rounded-md border border-warning/40 bg-warning/5 p-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-warning">
        {request.kind === "external_approval" ? (
          <ExternalLink className="h-4 w-4" />
        ) : (
          <ShieldQuestion className="h-4 w-4" />
        )}
        {t("approvalRequestTitle")}
        {request.toolName && (
          <span className="font-mono text-xs font-normal text-muted-foreground">{request.toolName}</span>
        )}
      </div>
      {request.prompt && (
        <div className="mb-2 text-sm text-foreground">
          <Markdown variant="chat">{request.prompt}</Markdown>
        </div>
      )}
      <p className="mb-2 text-xs text-muted-foreground">{t("approvalRequestHint")}</p>
      <Textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder={t("commentPlaceholder", { ns: "approvals" })}
        className="mb-2"
      />
      <div className="flex gap-2">
        <Button
          size="sm"
          disabled={approvalMutation.isPending}
          onClick={() => approvalMutation.mutate("approved")}
        >
          {t("approve")}
        </Button>
        <Button
          size="sm"
          variant="destructive"
          disabled={approvalMutation.isPending}
          onClick={() => approvalMutation.mutate("rejected")}
        >
          {t("reject")}
        </Button>
      </div>
    </div>
  );
}
