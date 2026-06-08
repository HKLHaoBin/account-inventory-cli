"use client";

import { useRef } from "react";
import { Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { copyToClipboard } from "@/lib/clipboard";

interface ClipboardCopyFallbackProps {
  text: string;
  visible: boolean;
  reason?: string;
  onRetry?: () => void | Promise<void>;
  onCopied?: () => void;
}

export function ClipboardCopyFallback({
  text,
  visible,
  reason,
  onRetry,
  onCopied,
}: ClipboardCopyFallbackProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  if (!visible || !text.trim()) {
    return null;
  }

  async function handleManualCopy() {
    const result = await copyToClipboard(text);
    if (result.ok) {
      onCopied?.();
      return;
    }
    textareaRef.current?.focus();
    textareaRef.current?.select();
  }

  function handleSelectAll() {
    textareaRef.current?.focus();
    textareaRef.current?.select();
  }

  return (
    <div className="space-y-3 rounded-xl border border-amber-200 bg-amber-50 p-3 dark:border-amber-900/40 dark:bg-amber-950/20">
      <p className="text-sm text-amber-800 dark:text-amber-200">
        {reason || "自动复制失败，请手动复制以下内容"}
      </p>
      <Textarea
        ref={textareaRef}
        readOnly
        value={text}
        className="min-h-[96px] font-mono text-xs"
        onFocus={handleSelectAll}
      />
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={() => void handleManualCopy()}>
          <Copy className="h-4 w-4" />
          手动复制
        </Button>
        <Button size="sm" variant="outline" onClick={handleSelectAll}>
          全选文本
        </Button>
        {onRetry && (
          <Button size="sm" variant="ghost" onClick={() => void onRetry()}>
            重试自动复制
          </Button>
        )}
      </div>
    </div>
  );
}
