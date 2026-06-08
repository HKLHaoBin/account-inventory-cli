"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { HistoryFilters } from "@/components/history/HistoryFilters";
import { InventoryKlineChart } from "@/components/history/InventoryKlineChart";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchHistoryKline } from "@/lib/api";
import { subscribeDatabaseChanged } from "@/lib/database-events";
import {
  clampRangeToDataBounds,
  loadedRangeCovers,
  mergeLoadedRange,
  padVisibleRange,
  shouldExpandLoadedRange,
} from "@/lib/kline-range";
import {
  defaultTrendRangeMs,
  formatLocalDateTime,
  parseTimeToMs,
} from "@/lib/kline-time";
import { cn } from "@/lib/utils";
import type { DateRangeFilter, KlineBucket, KlinePayload } from "@/types/account";

type BucketMode = "auto" | KlineBucket;

type DataBounds = {
  dataFromMs: number | null;
  dataToMs: number | null;
  hasData: boolean;
};

const BUCKET_OPTIONS: { value: BucketMode; label: string }[] = [
  { value: "auto", label: "自动" },
  { value: "hour", label: "小时" },
  { value: "day", label: "天" },
  { value: "week", label: "周" },
  { value: "month", label: "月" },
];

function emptyLoadedRange(): { fromMs: number; toMs: number } {
  return { fromMs: 0, toMs: 0 };
}

function emptyDataBounds(): DataBounds {
  return { dataFromMs: null, dataToMs: null, hasData: true };
}

function boundsFromPayload(payload: KlinePayload): DataBounds {
  return {
    dataFromMs: payload.dataFrom ? parseTimeToMs(payload.dataFrom) : null,
    dataToMs: payload.dataTo ? parseTimeToMs(payload.dataTo) : null,
    hasData: payload.hasData,
  };
}

export default function HistoryTrendsPage() {
  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<number | null>(null);
  const loadedRangeRef = useRef(defaultTrendRangeMs());
  const dataBoundsRef = useRef<DataBounds>(emptyDataBounds());
  const skipNextZoomRef = useRef(false);
  const initialLoadRef = useRef(true);

  const [query, setQuery] = useState("");
  const [ranges, setRanges] = useState<DateRangeFilter[]>([]);
  const [bucketMode, setBucketMode] = useState<BucketMode>("auto");
  const [data, setData] = useState<KlinePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadToken, setReloadToken] = useState(0);
  const [shouldFit, setShouldFit] = useState(true);
  const [resetVersion, setResetVersion] = useState(0);
  const [pendingVisibleRange, setPendingVisibleRange] = useState<{
    fromMs: number;
    toMs: number;
  } | null>(null);
  const [pendingVisibleRangeVersion, setPendingVisibleRangeVersion] = useState(0);

  const rangeValues = useMemo(
    () => ranges.map((item) => item.value),
    [ranges]
  );

  const loadKline = useCallback(
    async (
      fromMs: number,
      toMs: number,
      options?: {
        fit?: boolean;
        resetPendingRange?: boolean;
        bucketOverride?: BucketMode;
        visibleRange?: { fromMs: number; toMs: number };
      }
    ) => {
      const bounds = dataBoundsRef.current;
      const clamped = clampRangeToDataBounds(fromMs, toMs, {
        dataFromMs: bounds.dataFromMs,
        dataToMs: bounds.dataToMs,
      });

      if (bounds.dataFromMs !== null && !bounds.hasData && !options?.fit) {
        return;
      }

      if (
        !options?.fit &&
        loadedRangeCovers(loadedRangeRef.current, clamped)
      ) {
        return;
      }

      if (options?.fit || options?.resetPendingRange) {
        setPendingVisibleRange(null);
      }

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const bucketSelection = options?.bucketOverride ?? bucketMode;

      setLoading(true);
      setError("");

      try {
        const payload = await fetchHistoryKline(
          {
            from: formatLocalDateTime(clamped.fromMs),
            to: formatLocalDateTime(clamped.toMs),
            bucket: bucketSelection,
            q: query,
            ranges: rangeValues,
          },
          { signal: controller.signal }
        );
        if (controller.signal.aborted) return;

        const payloadRange = {
          fromMs: parseTimeToMs(payload.from),
          toMs: parseTimeToMs(payload.to),
        };
        loadedRangeRef.current = mergeLoadedRange(
          loadedRangeRef.current,
          payloadRange
        );
        dataBoundsRef.current = boundsFromPayload(payload);
        setData(payload);

        if (options?.fit) {
          setShouldFit(true);
        } else if (options?.visibleRange) {
          setPendingVisibleRange(options.visibleRange);
          setPendingVisibleRangeVersion((value) => value + 1);
        }
      } catch (requestError) {
        if (controller.signal.aborted) return;
        setError(
          requestError instanceof Error ? requestError.message : "趋势数据读取失败"
        );
        setData(null);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    },
    [bucketMode, query, rangeValues]
  );

  const scheduleZoomLoad = useCallback(
    (visibleFromMs: number, visibleToMs: number) => {
      if (skipNextZoomRef.current) {
        skipNextZoomRef.current = false;
        return;
      }

      if (!dataBoundsRef.current.hasData) {
        return;
      }

      const visible = { fromMs: visibleFromMs, toMs: visibleToMs };
      if (!shouldExpandLoadedRange(visible, loadedRangeRef.current)) {
        return;
      }

      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
      }

      debounceRef.current = window.setTimeout(() => {
        const padded = padVisibleRange(visibleFromMs, visibleToMs, 0.2);
        const merged = mergeLoadedRange(loadedRangeRef.current, padded);
        const clamped = clampRangeToDataBounds(merged.fromMs, merged.toMs, {
          dataFromMs: dataBoundsRef.current.dataFromMs,
          dataToMs: dataBoundsRef.current.dataToMs,
        });

        if (loadedRangeCovers(loadedRangeRef.current, clamped)) {
          return;
        }

        void loadKline(clamped.fromMs, clamped.toMs, { visibleRange: visible });
      }, 300);
    },
    [loadKline]
  );

  const retry = useCallback(() => {
    setReloadToken((value) => value + 1);
  }, []);

  const handleResetView = useCallback(() => {
    const nextRange = defaultTrendRangeMs();
    loadedRangeRef.current = emptyLoadedRange();
    skipNextZoomRef.current = true;
    setResetVersion((value) => value + 1);
    void loadKline(nextRange.fromMs, nextRange.toMs, { fit: true });
  }, [loadKline]);

  useEffect(() => {
    loadedRangeRef.current = emptyLoadedRange();
    dataBoundsRef.current = emptyDataBounds();

    const defaultRange = defaultTrendRangeMs();
    const timer = window.setTimeout(() => {
      void loadKline(
        defaultRange.fromMs,
        defaultRange.toMs,
        {
          fit: initialLoadRef.current,
          resetPendingRange: true,
        }
      );
      initialLoadRef.current = false;
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadKline, reloadToken, query, rangeValues, bucketMode]);

  useEffect(
    () =>
      subscribeDatabaseChanged(() => {
        setReloadToken((value) => value + 1);
      }),
    []
  );

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!shouldFit) return;
    const timer = window.setTimeout(() => setShouldFit(false), 0);
    return () => window.clearTimeout(timer);
  }, [shouldFit, data, resetVersion]);

  const totals = data?.totals;

  return (
    <div className="space-y-4">
      <HistoryFilters
        query={query}
        ranges={ranges}
        onQueryChange={setQuery}
        onRangesChange={setRanges}
      />

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">粒度</span>
        {BUCKET_OPTIONS.map((option) => (
          <Button
            key={option.value}
            type="button"
            size="sm"
            variant={bucketMode === option.value ? "primary" : "outline"}
            onClick={() => setBucketMode(option.value)}
          >
            {option.label}
          </Button>
        ))}
        <Button type="button" size="sm" variant="secondary" onClick={handleResetView}>
          重置视图
        </Button>
      </div>

      {totals && (
        <div className="grid gap-2 sm:grid-cols-3">
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground">入库</p>
              <p className="text-lg font-semibold">{totals.inboundCount}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground">出库</p>
              <p className="text-lg font-semibold">{totals.outboundCount}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground">净变化</p>
              <p
                className={cn(
                  "text-lg font-semibold",
                  totals.netChange > 0 && "text-emerald-600",
                  totals.netChange < 0 && "text-red-600"
                )}
              >
                {totals.netChange > 0 ? "+" : ""}
                {totals.netChange}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {error && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
          <span>{error}</span>
          <Button type="button" size="sm" variant="outline" onClick={retry}>
            重试
          </Button>
        </div>
      )}

      <Card>
        <CardHeader className="p-4 pb-3 sm:p-6 sm:pb-4">
          <CardTitle className="text-base">库存趋势</CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0 sm:p-6 sm:pt-0">
          <InventoryKlineChart
            mode="interactive"
            data={data}
            loading={loading}
            shouldFit={shouldFit}
            pendingVisibleRange={pendingVisibleRange}
            pendingVisibleRangeVersion={pendingVisibleRangeVersion}
            onVisibleRangeChange={({ fromMs, toMs }) =>
              scheduleZoomLoad(fromMs, toMs)
            }
          />
        </CardContent>
      </Card>
    </div>
  );
}
