import { writeAppClipboardText } from "@/lib/api";
import { ClipboardCopyError } from "@/lib/clipboard";

export const HISTORY_COPY_FAILURE_ROW_MESSAGE =
  "操作已完成，复制失败，请手动复制";

export type AppClipboardCopyOutcome = {
  ok: boolean;
  manualCopyText: string | null;
  reason?: string;
};

export async function runHistoryQuickAction<T extends { clipboardText: string }>(
  action: () => Promise<T>,
  onReload: () => void
): Promise<void> {
  const payload = await action();
  onReload();
  await writeAppClipboardText(payload.clipboardText);
}

export function historyQuickActionRowError(
  error: unknown,
  businessFailureMessage: string
): string {
  if (error instanceof ClipboardCopyError) {
    return HISTORY_COPY_FAILURE_ROW_MESSAGE;
  }
  return error instanceof Error ? error.message : businessFailureMessage;
}
export type HistoryManualCopyKind = "line" | "quick-action" | "export-all";

export function resolveHistoryManualCopyRetry(options: {
  kind: HistoryManualCopyKind;
  text: string;
  retryTextCopy: (text: string) => void | Promise<void>;
  retryExportAll: () => void | Promise<void>;
}): () => void | Promise<void> {
  if (options.kind === "export-all") {
    return options.retryExportAll;
  }
  const { text } = options;
  return () => options.retryTextCopy(text);
}

export function createTextCopyRetry(
  text: string,
  runCopy: (value: string) => Promise<AppClipboardCopyOutcome> = runAppClipboardCopy
): () => Promise<AppClipboardCopyOutcome> {
  return () => runCopy(text);
}

export async function runAppClipboardCopy(
  text: string
): Promise<AppClipboardCopyOutcome> {
  try {
    await writeAppClipboardText(text);
    return { ok: true, manualCopyText: null };
  } catch (error) {
    if (error instanceof ClipboardCopyError) {
      return {
        ok: false,
        manualCopyText: error.text,
        reason: error.reason,
      };
    }
    return {
      ok: false,
      manualCopyText: text,
      reason: error instanceof Error ? error.message : "复制失败",
    };
  }
}
