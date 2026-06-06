import { afterEach, describe, expect, it, vi } from "vitest";
import { buildPaginationQuery, fetchHistoryKline } from "./api";

describe("buildPaginationQuery for kline", () => {
  it("appends repeated ranges and keeps bucket=auto", () => {
    const query = buildPaginationQuery({
      from: "2024-01-01T00:00:00",
      to: "2024-02-01T00:00:00",
      bucket: "auto",
      q: "demo",
      ranges: ["2024-01-01..2024-01-07", "2024-01-10..2024-01-15"],
    });

    expect(query).toContain("from=2024-01-01T00%3A00%3A00");
    expect(query).toContain("to=2024-02-01T00%3A00%3A00");
    expect(query).toContain("bucket=auto");
    expect(query).toContain("q=demo");
    expect(query.match(/ranges=/g)?.length).toBe(2);
    expect(query).toContain("ranges=2024-01-01..2024-01-07");
    expect(query).toContain("ranges=2024-01-10..2024-01-15");
  });
});

describe("fetchHistoryKline", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requests /api/history/kline with serialized params", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        bucket: "day",
        from: "2024-01-01T00:00:00",
        to: "2024-02-01T00:00:00",
        candles: [],
        totals: {
          inboundCount: 0,
          outboundCount: 0,
          stockOutboundCount: 0,
          netChange: 0,
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await fetchHistoryKline({
      from: "2024-01-01T00:00:00",
      to: "2024-02-01T00:00:00",
      bucket: "auto",
      ranges: ["2024-01-01..2024-01-07", "2024-01-10..2024-01-15"],
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/history/kline?");
    expect(url).toContain("bucket=auto");
    expect(url.match(/ranges=/g)?.length).toBe(2);
    expect(init.headers).toMatchObject({
      "Content-Type": "application/json",
    });
  });

  it("forwards abort signal", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        bucket: "day",
        from: "2024-01-01T00:00:00",
        to: "2024-02-01T00:00:00",
        candles: [],
        totals: {
          inboundCount: 0,
          outboundCount: 0,
          stockOutboundCount: 0,
          netChange: 0,
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await fetchHistoryKline({ bucket: "day" }, { signal: controller.signal });

    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      signal: controller.signal,
    });
  });
});
