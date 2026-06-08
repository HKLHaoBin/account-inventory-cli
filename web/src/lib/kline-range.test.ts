import { describe, expect, it } from "vitest";
import {
  clampRangeToDataBounds,
  loadedRangeCovers,
  mergeLoadedRange,
} from "./kline-range";

const DATA_FROM_MS = Date.parse("2026-06-01T09:00:00");
const DATA_TO_MS = Date.parse("2026-06-07T10:00:00");
const BOUNDS = { dataFromMs: DATA_FROM_MS, dataToMs: DATA_TO_MS };

describe("clampRangeToDataBounds", () => {
  it("keeps an in-range request unchanged", () => {
    const fromMs = Date.parse("2026-06-02T00:00:00");
    const toMs = Date.parse("2026-06-05T00:00:00");

    expect(clampRangeToDataBounds(fromMs, toMs, BOUNDS)).toEqual({
      fromMs,
      toMs,
    });
  });

  it("anchors a left out-of-bounds request to dataFrom", () => {
    const fromMs = Date.parse("2017-01-01T00:00:00");
    const toMs = Date.parse("2017-01-08T00:00:00");
    const requestSpan = toMs - fromMs;

    expect(clampRangeToDataBounds(fromMs, toMs, BOUNDS)).toEqual({
      fromMs: DATA_FROM_MS,
      toMs: Math.min(DATA_FROM_MS + requestSpan, DATA_TO_MS),
    });
  });

  it("anchors a right out-of-bounds request to dataTo", () => {
    const fromMs = Date.parse("2030-01-01T00:00:00");
    const toMs = Date.parse("2030-01-08T00:00:00");
    const requestSpan = toMs - fromMs;

    expect(clampRangeToDataBounds(fromMs, toMs, BOUNDS)).toEqual({
      fromMs: Math.max(DATA_TO_MS - requestSpan, DATA_FROM_MS),
      toMs: DATA_TO_MS,
    });
  });

  it("returns the full data range when request span exceeds data span", () => {
    expect(
      clampRangeToDataBounds(
        Date.parse("2017-01-01T00:00:00"),
        Date.parse("2018-01-01T00:00:00"),
        BOUNDS
      )
    ).toEqual({
      fromMs: DATA_FROM_MS,
      toMs: DATA_TO_MS,
    });
  });
});

describe("mergeLoadedRange", () => {
  it("returns next when current loaded range is empty", () => {
    expect(
      mergeLoadedRange(
        { fromMs: 0, toMs: 0 },
        { fromMs: 100, toMs: 200 }
      )
    ).toEqual({ fromMs: 100, toMs: 200 });
  });

  it("expands the loaded range to include both windows", () => {
    expect(
      mergeLoadedRange(
        { fromMs: 100, toMs: 300 },
        { fromMs: 50, toMs: 250 }
      )
    ).toEqual({ fromMs: 50, toMs: 300 });
  });
});

describe("loadedRangeCovers", () => {
  it("returns false for an empty loaded range", () => {
    expect(
      loadedRangeCovers(
        { fromMs: 0, toMs: 0 },
        { fromMs: 100, toMs: 200 }
      )
    ).toBe(false);
  });

  it("returns true when loaded range already covers the target", () => {
    expect(
      loadedRangeCovers(
        { fromMs: 100, toMs: 400 },
        { fromMs: 150, toMs: 250 }
      )
    ).toBe(true);
  });

  it("returns false when the target extends beyond loaded range", () => {
    expect(
      loadedRangeCovers(
        { fromMs: 100, toMs: 200 },
        { fromMs: 150, toMs: 250 }
      )
    ).toBe(false);
  });
});
