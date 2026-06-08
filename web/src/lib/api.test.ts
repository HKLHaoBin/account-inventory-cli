import { afterEach, describe, expect, it, vi } from "vitest";
import { ClipboardCopyError } from "./clipboard";

vi.mock("./clipboard", async () => {
  const actual = await vi.importActual<typeof import("./clipboard")>("./clipboard");
  return {
    ...actual,
    copyToClipboard: vi.fn(),
  };
});

import { copyToClipboard } from "./clipboard";
import { writeAppClipboardText } from "./api";

describe("writeAppClipboardText", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.mocked(copyToClipboard).mockReset();
  });

  it("calls ignore only after a successful copy", async () => {
    vi.mocked(copyToClipboard).mockResolvedValue({ ok: true });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await writeAppClipboardText("user----pass");

    expect(copyToClipboard).toHaveBeenCalledWith("user----pass");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/clipboard/ignore",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ text: "user----pass" }),
      })
    );
  });

  it("throws ClipboardCopyError and skips ignore when copy fails", async () => {
    vi.mocked(copyToClipboard).mockResolvedValue({
      ok: false,
      text: "user----pass",
      reason: "浏览器不允许自动复制，请手动复制",
    });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(writeAppClipboardText("user----pass")).rejects.toBeInstanceOf(
      ClipboardCopyError
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("requestJson cloud configuration errors", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("throws a friendly message for HTTP 428", async () => {
    const { fetchDashboard } = await import("./api");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 428,
        text: async () =>
          JSON.stringify({ detail: "请先配置数据库服务地址" }),
      })
    );

    await expect(fetchDashboard()).rejects.toThrow("请先配置数据库服务地址");
  });
});
