import { afterEach, describe, expect, it, vi } from "vitest";
import { ClipboardCopyError } from "./clipboard";

vi.mock("./api", () => ({
  writeAppClipboardText: vi.fn(),
}));

import { writeAppClipboardText } from "./api";
import {
  createTextCopyRetry,
  HISTORY_COPY_FAILURE_ROW_MESSAGE,
  historyQuickActionRowError,
  resolveHistoryManualCopyRetry,
  runHistoryQuickAction,
} from "./clipboard-actions";

describe("runHistoryQuickAction", () => {
  afterEach(() => {
    vi.mocked(writeAppClipboardText).mockReset();
  });

  it("reloads and copies after the business action succeeds", async () => {
    const onReload = vi.fn();
    const action = vi.fn().mockResolvedValue({ clipboardText: "user----pass" });
    vi.mocked(writeAppClipboardText).mockResolvedValue(undefined);

    await runHistoryQuickAction(action, onReload);

    expect(action).toHaveBeenCalledTimes(1);
    expect(onReload).toHaveBeenCalledTimes(1);
    expect(writeAppClipboardText).toHaveBeenCalledWith("user----pass");
  });

  it("still reloads when clipboard copy fails after business success", async () => {
    const onReload = vi.fn();
    const action = vi.fn().mockResolvedValue({ clipboardText: "user----pass" });
    vi.mocked(writeAppClipboardText).mockRejectedValue(
      new ClipboardCopyError("user----pass", "浏览器不允许自动复制，请手动复制")
    );

    await expect(
      runHistoryQuickAction(action, onReload)
    ).rejects.toBeInstanceOf(ClipboardCopyError);

    expect(action).toHaveBeenCalledTimes(1);
    expect(onReload).toHaveBeenCalledTimes(1);
    expect(writeAppClipboardText).toHaveBeenCalledWith("user----pass");
  });

  it("does not reload when the business action fails", async () => {
    const onReload = vi.fn();
    const action = vi.fn().mockRejectedValue(new Error("入库失败"));

    await expect(runHistoryQuickAction(action, onReload)).rejects.toThrow(
      "入库失败"
    );

    expect(onReload).not.toHaveBeenCalled();
    expect(writeAppClipboardText).not.toHaveBeenCalled();
  });
});

describe("historyQuickActionRowError", () => {
  it("uses copy-failure semantics for ClipboardCopyError", () => {
    const error = new ClipboardCopyError("user----pass", "浏览器不允许自动复制，请手动复制");

    expect(historyQuickActionRowError(error, "入库失败")).toBe(
      HISTORY_COPY_FAILURE_ROW_MESSAGE
    );
    expect(historyQuickActionRowError(error, "出库失败")).toBe(
      "操作已完成，复制失败，请手动复制"
    );
  });

  it("keeps business failure messages for non-copy errors", () => {
    expect(historyQuickActionRowError(new Error("账号不在库存中"), "入库失败")).toBe(
      "账号不在库存中"
    );
    expect(historyQuickActionRowError("boom", "出库失败")).toBe("出库失败");
  });
});

describe("resolveHistoryManualCopyRetry", () => {
  it("retries only the failed line text for single-row copy failures", async () => {
    const retryTextCopy = vi.fn();
    const retryExportAll = vi.fn();
    const lineText = "user----pass----note";

    await resolveHistoryManualCopyRetry({
      kind: "line",
      text: lineText,
      retryTextCopy,
      retryExportAll,
    })();

    expect(retryTextCopy).toHaveBeenCalledWith(lineText);
    expect(retryExportAll).not.toHaveBeenCalled();
  });

  it("retries quick-action clipboard text without re-running business APIs", async () => {
    const retryTextCopy = vi.fn();
    const retryExportAll = vi.fn();
    const clipboardText = "quick----action----text";

    await resolveHistoryManualCopyRetry({
      kind: "quick-action",
      text: clipboardText,
      retryTextCopy,
      retryExportAll,
    })();

    expect(retryTextCopy).toHaveBeenCalledWith(clipboardText);
    expect(retryExportAll).not.toHaveBeenCalled();
  });

  it("retries export-all instead of a single clipboard text", async () => {
    const retryTextCopy = vi.fn();
    const retryExportAll = vi.fn();

    await resolveHistoryManualCopyRetry({
      kind: "export-all",
      text: "entire export payload",
      retryTextCopy,
      retryExportAll,
    })();

    expect(retryExportAll).toHaveBeenCalledTimes(1);
    expect(retryTextCopy).not.toHaveBeenCalled();
  });
});

describe("createTextCopyRetry", () => {
  it("re-copies the same text on retry", async () => {
    const runCopy = vi.fn().mockResolvedValue({ ok: true, manualCopyText: null });
    const retry = createTextCopyRetry("row----text", runCopy);

    await retry();

    expect(runCopy).toHaveBeenCalledTimes(1);
    expect(runCopy).toHaveBeenCalledWith("row----text");
  });
});
