import type { KlineBucket } from "@/types/account";

const MS_HOUR = 60 * 60 * 1000;
const MS_DAY = 24 * MS_HOUR;
const TWO_DAYS = 2 * MS_DAY;
const ONE_HUNDRED_TWENTY_DAYS = 120 * MS_DAY;
const TWO_YEARS = 730 * MS_DAY;
const MAX_BUCKETS = 500;

const BUCKET_ORDER: KlineBucket[] = ["hour", "day", "week", "month"];

function startOfHour(date: Date): Date {
  return new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
    date.getHours(),
    0,
    0,
    0
  );
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate(), 0, 0, 0, 0);
}

function startOfWeekMonday(date: Date): Date {
  const result = startOfDay(date);
  const weekday = result.getDay();
  const diff = weekday === 0 ? -6 : 1 - weekday;
  result.setDate(result.getDate() + diff);
  return result;
}

function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1, 0, 0, 0, 0);
}

function floorToBucketMs(ms: number, bucket: KlineBucket): number {
  const date = new Date(ms);
  switch (bucket) {
    case "hour":
      return startOfHour(date).getTime();
    case "day":
      return startOfDay(date).getTime();
    case "week":
      return startOfWeekMonday(date).getTime();
    case "month":
      return startOfMonth(date).getTime();
  }
}

function advanceBucketMs(ms: number, bucket: KlineBucket): number {
  const date = new Date(ms);
  switch (bucket) {
    case "hour":
      return ms + MS_HOUR;
    case "day":
      return ms + MS_DAY;
    case "week":
      return ms + 7 * MS_DAY;
    case "month":
      return new Date(date.getFullYear(), date.getMonth() + 1, 1, 0, 0, 0, 0).getTime();
  }
}

export function countBuckets(
  fromMs: number,
  toMs: number,
  bucket: KlineBucket
): number {
  if (toMs < fromMs) return 0;

  let current = floorToBucketMs(fromMs, bucket);
  const last = floorToBucketMs(toMs, bucket);
  let count = 0;

  while (current <= last) {
    count += 1;
    if (count > MAX_BUCKETS) return count;
    current = advanceBucketMs(current, bucket);
  }

  return count;
}

function baseAutoBucket(fromMs: number, toMs: number): KlineBucket {
  const span = Math.max(0, toMs - fromMs);
  if (span <= TWO_DAYS) return "hour";
  if (span <= ONE_HUNDRED_TWENTY_DAYS) return "day";
  if (span <= TWO_YEARS) return "week";
  return "month";
}

function coarsenBucket(bucket: KlineBucket): KlineBucket | null {
  const index = BUCKET_ORDER.indexOf(bucket);
  if (index < 0 || index >= BUCKET_ORDER.length - 1) return null;
  return BUCKET_ORDER[index + 1];
}

export function resolveAutoBucket(fromMs: number, toMs: number): KlineBucket {
  let bucket = baseAutoBucket(fromMs, toMs);
  while (countBuckets(fromMs, toMs, bucket) > MAX_BUCKETS) {
    const next = coarsenBucket(bucket);
    if (!next) break;
    bucket = next;
  }
  return bucket;
}
