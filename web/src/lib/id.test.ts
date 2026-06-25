import { afterEach, describe, expect, it, vi } from "vitest";
import { generateId } from "./id";

describe("generateId", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses crypto.randomUUID when available", () => {
    vi.stubGlobal("crypto", {
      randomUUID: vi.fn().mockReturnValue("uuid-from-crypto"),
    });

    expect(generateId()).toBe("uuid-from-crypto");
  });

  it("falls back when randomUUID is unavailable", () => {
    vi.stubGlobal("crypto", {});

    const id = generateId();

    expect(id).toMatch(/^id-[a-z0-9]+-[a-z0-9]+$/);
  });
});
