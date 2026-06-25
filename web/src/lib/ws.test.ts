import { afterEach, describe, expect, it, vi } from "vitest";
import { clipboardLoadedStatus, getClipboardWsUrl, isClipboardMessage } from "./ws";

describe("clipboard websocket helpers", () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_WS_URL;
    vi.unstubAllGlobals();
  });

  it("accepts simplified cloud clipboard messages", () => {
    expect(
      isClipboardMessage({
        source: "clipboard",
        text: "user----pass\nuser2----pass2",
      })
    ).toBe(true);
  });

  it("accepts legacy local clipboard messages", () => {
    expect(
      isClipboardMessage({
        source: "clipboard",
        text: "user----pass",
        validLines: ["user----pass"],
        rejectedCount: 0,
      })
    ).toBe(true);
  });

  it("builds line-based clipboard status text", () => {
    expect(
      clipboardLoadedStatus("user----pass\n\nuser2----pass2\n")
    ).toBe("已从剪贴板载入 2 行");
  });

  it("uses NEXT_PUBLIC_WS_URL when provided", () => {
    process.env.NEXT_PUBLIC_WS_URL = "ws://127.0.0.1:8000/ws/clipboard";
    expect(getClipboardWsUrl()).toBe("ws://127.0.0.1:8000/ws/clipboard");
  });

  it("uses loopback default during SSR", () => {
    expect(getClipboardWsUrl()).toBe("ws://127.0.0.1:8000/ws/clipboard");
  });

  it("derives websocket url from browser location", () => {
    vi.stubGlobal("window", {
      location: {
        protocol: "http:",
        host: "192.168.1.10:8000",
      },
    });

    expect(getClipboardWsUrl()).toBe("ws://192.168.1.10:8000/ws/clipboard");
  });
});
