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
import {
  fetchDashboard,
  ignoreClipboardText,
  writeAppClipboardText,
} from "./api";
import {
  invalidateLocalCredentialsCache,
  fetchLocalCredentials,
} from "./local-config";
import {
  resolveRequestBase,
  resolveRequestTarget,
  resolveRequestUrl,
} from "./request-routing";

describe("writeAppClipboardText", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.mocked(copyToClipboard).mockReset();
    invalidateLocalCredentialsCache();
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
    expect(fetchMock).toHaveBeenLastCalledWith(
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

describe("request routing", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    invalidateLocalCredentialsCache();
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    delete process.env.NEXT_PUBLIC_LOCAL_API_BASE_URL;
  });

  it("routes clipboard ignore and runtime to local", () => {
    expect(resolveRequestTarget("/api/clipboard/ignore")).toBe("local");
    expect(resolveRequestTarget("/api/runtime/update-status")).toBe("local");
    expect(resolveRequestTarget("/local/config")).toBe("local");
    expect(resolveRequestTarget("/api/dashboard")).toBe("remote");
  });

  it("requests remote dashboard with cloud base url and token header", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          remoteAccessToken: "remote-secret",
          cloudApiBaseUrl: "https://cloud.example",
          configured: true,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ inventoryCount: 3 }),
      });
    vi.stubGlobal("fetch", fetchMock);

    await fetchDashboard();

    expect(fetchMock).toHaveBeenLastCalledWith(
      "https://cloud.example/api/dashboard",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Remote-Access-Token": "remote-secret",
        }),
      })
    );
  });

  it("keeps clipboard ignore on the local base even when cloud is configured", async () => {
    process.env.NEXT_PUBLIC_LOCAL_API_BASE_URL = "http://127.0.0.1:8000";
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await ignoreClipboardText("skip----pw");

    expect(fetchMock).toHaveBeenLastCalledWith(
      "http://127.0.0.1:8000/api/clipboard/ignore",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("throws before fetch when cloud client is unconfigured", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        remoteAccessToken: null,
        cloudApiBaseUrl: null,
        configured: false,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchDashboard()).rejects.toThrow("请先配置数据库服务地址");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/local/credentials", expect.any(Object));
  });

  it("resolves remote base from NEXT_PUBLIC_API_BASE_URL", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://env.example/";
    await expect(resolveRequestBase("/api/dashboard")).resolves.toBe(
      "https://env.example"
    );
  });

  it("resolves request url for local runtime paths", async () => {
    await expect(resolveRequestUrl("/api/runtime/update-status")).resolves.toBe(
      "/api/runtime/update-status"
    );
  });
});

describe("requestJson remote access errors", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    invalidateLocalCredentialsCache();
  });

  it("throws a friendly message for HTTP 401 remote access gate", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          remoteAccessToken: null,
          cloudApiBaseUrl: "https://cloud.example",
          configured: true,
        }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        text: async () =>
          JSON.stringify({ detail: "invalid remote access token" }),
      });
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchDashboard()).rejects.toThrow(
      "需要远程访问令牌，请先完成远程访问验证"
    );
  });
});

describe("fetchLocalCredentials cache", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    invalidateLocalCredentialsCache();
  });

  it("reuses cached credentials until invalidated", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        remoteAccessToken: "remote-secret",
        cloudApiBaseUrl: "https://cloud.example",
        configured: true,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchLocalCredentials()).resolves.toEqual({
      remoteAccessToken: "remote-secret",
      cloudApiBaseUrl: "https://cloud.example",
      configured: true,
    });
    await expect(fetchLocalCredentials()).resolves.toEqual({
      remoteAccessToken: "remote-secret",
      cloudApiBaseUrl: "https://cloud.example",
      configured: true,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    invalidateLocalCredentialsCache();
    await fetchLocalCredentials();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
