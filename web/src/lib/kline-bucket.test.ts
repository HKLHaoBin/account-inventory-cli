import { describe, expect, it } from "vitest";
import { countBuckets, resolveAutoBucket } from "./kline-bucket";

const MS_HOUR = 60 * 60 * 1000;
const MS_DAY = 24 * MS_HOUR;

describe("resolveAutoBucket", () => {
  it("uses hour for spans up to two days", () => {
    const fromMs = Date.parse("2024-01-01T00:00:00");
    const toMs = fromMs + 2 * MS_DAY;
    expect(resolveAutoBucket(fromMs, toMs)).toBe("hour");
  });

  it("uses day for spans up to 120 days", () => {
    const fromMs = Date.parse("2024-01-01T00:00:00");
    const toMs = fromMs + 120 * MS_DAY;
    expect(resolveAutoBucket(fromMs, toMs)).toBe("day");
  });

  it("uses week for spans up to two years", () => {
    const fromMs = Date.parse("2022-01-01T00:00:00");
    const toMs = fromMs + 730 * MS_DAY;
    expect(resolveAutoBucket(fromMs, toMs)).toBe("week");
  });

  it("uses month for spans beyond two years", () => {
    const fromMs = Date.parse("2020-01-01T00:00:00");
    const toMs = Date.parse("2024-01-01T00:00:00");
    expect(resolveAutoBucket(fromMs, toMs)).toBe("month");
  });

  it("coarsens buckets when count exceeds 500", () => {
    const fromMs = Date.parse("2024-01-01T00:00:00");
    const toMs = fromMs + 60 * MS_DAY;
    expect(countBuckets(fromMs, toMs, "hour")).toBeGreaterThan(500);
    expect(resolveAutoBucket(fromMs, toMs)).toBe("day");
  });
});

describe("countBuckets", () => {
  it("counts inclusive bucket boundaries", () => {
    const fromMs = Date.parse("2024-01-01T00:00:00");
    const toMs = Date.parse("2024-01-02T00:00:00");
    expect(countBuckets(fromMs, toMs, "day")).toBe(2);
  });
});
