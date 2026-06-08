"use client";

import { Card, CardContent } from "@/components/ui/card";
import { ClipboardCopyFallback } from "@/components/clipboard/clipboard-copy-fallback";
import { OutboundCopyButton } from "@/components/outbound/outbound-copy-button";

interface OutboundCopyPanelProps {
  clipboardText: string;
  copying: boolean;
  copied: boolean;
  copyFailed: boolean;
  onCopy: () => void | Promise<void>;
  onManualCopySuccess?: () => void;
  successTitle?: string;
  failedTitle?: string;
  className?: string;
}

export function OutboundCopyPanel({
  clipboardText,
  copying,
  copied,
  copyFailed,
  onCopy,
  onManualCopySuccess,
  successTitle = "账号已出库，可重新复制",
  failedTitle = "已出库，自动复制失败，请手动复制",
  className,
}: OutboundCopyPanelProps) {
  if (!clipboardText) {
    return null;
  }

  return (
    <Card
      className={
        className ??
        "border-emerald-200 bg-emerald-50 dark:border-emerald-900/40 dark:bg-emerald-950/30"
      }
    >
      <CardContent className="space-y-3 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm font-medium text-emerald-700 dark:text-emerald-300">
            {copyFailed ? failedTitle : successTitle}
          </p>
          <OutboundCopyButton
            size="sm"
            clipboardText={clipboardText}
            copying={copying}
            copied={copied}
            onCopy={onCopy}
          />
        </div>
        <ClipboardCopyFallback
          visible={copyFailed}
          text={clipboardText}
          onRetry={onCopy}
          onCopied={onManualCopySuccess}
        />
      </CardContent>
    </Card>
  );
}
