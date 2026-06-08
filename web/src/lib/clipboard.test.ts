import { afterEach, describe, expect, it, vi } from "vitest";
import { copyToClipboard } from "./clipboard";

describe("copyToClipboard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("returns success when navigator.clipboard.writeText succeeds", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    await expect(copyToClipboard("user----pass")).resolves.toEqual({ ok: true });
    expect(writeText).toHaveBeenCalledWith("user----pass");
  });

  it("falls back to execCommand when clipboard API is unavailable", async () => {
    vi.stubGlobal("navigator", {});
    const execCommand = vi.fn().mockReturnValue(true);
    vi.stubGlobal("document", {
      execCommand,
      body: {
        appendChild: vi.fn(),
        removeChild: vi.fn(),
      },
      createElement: vi.fn(() => ({
        value: "",
        style: {},
        setAttribute: vi.fn(),
        focus: vi.fn(),
        select: vi.fn(),
        setSelectionRange: vi.fn(),
      })),
    });

    await expect(copyToClipboard("legacy----copy")).resolves.toEqual({ ok: true });
    expect(execCommand).toHaveBeenCalledWith("copy");
  });

  it("returns failure with original text when all strategies fail", async () => {
    vi.stubGlobal("navigator", {
      clipboard: {
        writeText: vi.fn().mockRejectedValue(new Error("denied")),
      },
    });
    vi.stubGlobal("document", {
      execCommand: vi.fn().mockReturnValue(false),
      body: {
        appendChild: vi.fn(),
        removeChild: vi.fn(),
      },
      createElement: vi.fn(() => ({
        value: "",
        style: {},
        setAttribute: vi.fn(),
        focus: vi.fn(),
        select: vi.fn(),
        setSelectionRange: vi.fn(),
      })),
    });

    await expect(copyToClipboard("keep----me")).resolves.toEqual({
      ok: false,
      text: "keep----me",
      reason: "浏览器不允许自动复制，请手动复制",
    });
  });
});
