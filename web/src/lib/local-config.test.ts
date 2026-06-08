import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fetchLocalConfig,
  saveLocalConfig,
  testLocalConfig,
} from "./local-config";

describe("local-config client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns null when /local/config is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        text: async () => "Not Found",
      })
    );

    await expect(fetchLocalConfig()).resolves.toBeNull();
  });

  it("loads and saves local cloud config", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          cloudApiBaseUrl: null,
          configured: false,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          cloudApiBaseUrl: "https://cloud.example",
          configured: true,
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchLocalConfig()).resolves.toEqual({
      cloudApiBaseUrl: null,
      configured: false,
    });

    await expect(saveLocalConfig("https://cloud.example")).resolves.toEqual({
      cloudApiBaseUrl: "https://cloud.example",
      configured: true,
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/local/config",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ cloudApiBaseUrl: "https://cloud.example" }),
      })
    );
  });

  it("tests local cloud connectivity", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(testLocalConfig()).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith(
      "/local/config/test",
      expect.objectContaining({ method: "POST" })
    );
  });
});
