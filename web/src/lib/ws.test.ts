import { describe, expect, it } from "vitest";
import { clipboardLoadedStatus, isClipboardMessage } from "./ws";

describe("clipboard websocket helpers", () => {
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
});
