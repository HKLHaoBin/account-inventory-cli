"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTheme } from "next-themes";
import type { KlineCandle, KlinePayload } from "@/types/account";
import { cn } from "@/lib/utils";
import { parseTimeToMs } from "@/lib/kline-time";

export type KlineSeriesVisibility = {
  candlestick: boolean;
  inbound: boolean;
  outbound: boolean;
  netChange: boolean;
};

export type InventoryKlineChartHandle = {
  fitContent: () => void;
  getVisibleRangeMs: () => { fromMs: number; toMs: number } | null;
};

type ChartModule = typeof import("lightweight-charts");

type InventoryKlineChartProps = {
  mode: "compact" | "interactive";
  data: KlinePayload | null;
  seriesVisibility?: Partial<KlineSeriesVisibility>;
  onSeriesVisibilityChange?: (visibility: KlineSeriesVisibility) => void;
  onVisibleRangeChange?: (range: { fromMs: number; toMs: number }) => void;
  pendingVisibleRange?: { fromMs: number; toMs: number } | null;
  pendingVisibleRangeVersion?: number;
  shouldFit?: boolean;
  loading?: boolean;
  height?: number;
  showLegend?: boolean;
  className?: string;
};

const DEFAULT_VISIBILITY: KlineSeriesVisibility = {
  candlestick: true,
  inbound: true,
  outbound: true,
  netChange: true,
};

function mergeVisibility(
  partial?: Partial<KlineSeriesVisibility>
): KlineSeriesVisibility {
  return { ...DEFAULT_VISIBILITY, ...partial };
}

function isoToChartTime(iso: string): import("lightweight-charts").UTCTimestamp {
  return Math.floor(parseTimeToMs(iso) / 1000) as import("lightweight-charts").UTCTimestamp;
}

function getChartTheme(isDark: boolean) {
  return {
    layout: {
      background: { color: "transparent" },
      textColor: isDark ? "#94a3b8" : "#64748b",
    },
    grid: {
      vertLines: { color: isDark ? "#1e293b" : "#e2e8f0" },
      horzLines: { color: isDark ? "#1e293b" : "#e2e8f0" },
    },
    upColor: "#10b981",
    downColor: "#ef4444",
    inboundColor: "#10b981",
    outboundColor: "#ef4444",
    netLineColor: "#3b82f6",
  };
}

function buildSeriesData(candles: KlineCandle[]) {
  return {
    candlestick: candles.map((candle) => ({
      time: isoToChartTime(candle.time),
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
    })),
    inbound: candles.map((candle) => ({
      time: isoToChartTime(candle.time),
      value: candle.inboundCount,
      color: "#10b981",
    })),
    outbound: candles.map((candle) => ({
      time: isoToChartTime(candle.time),
      value: -candle.outboundCount,
      color: "#ef4444",
    })),
    netChange: candles.map((candle) => ({
      time: isoToChartTime(candle.time),
      value: candle.netChange,
    })),
  };
}

export const InventoryKlineChart = forwardRef<
  InventoryKlineChartHandle,
  InventoryKlineChartProps
>(function InventoryKlineChart(
  {
    mode,
    data,
    seriesVisibility,
    onSeriesVisibilityChange,
    onVisibleRangeChange,
    pendingVisibleRange = null,
    pendingVisibleRangeVersion = 0,
    shouldFit = false,
    loading = false,
    height,
    showLegend = mode === "interactive",
    className,
  },
  ref
) {
  const { resolvedTheme } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<import("lightweight-charts").IChartApi | null>(null);
  const candleSeriesRef =
    useRef<import("lightweight-charts").ISeriesApi<"Candlestick"> | null>(null);
  const inboundSeriesRef =
    useRef<import("lightweight-charts").ISeriesApi<"Histogram"> | null>(null);
  const outboundSeriesRef =
    useRef<import("lightweight-charts").ISeriesApi<"Histogram"> | null>(null);
  const netSeriesRef =
    useRef<import("lightweight-charts").ISeriesApi<"Line"> | null>(null);
  const chartModuleRef = useRef<ChartModule | null>(null);
  const suppressRangeEventRef = useRef(false);
  const onVisibleRangeChangeRef = useRef(onVisibleRangeChange);
  const dataRef = useRef(data);
  const shouldFitRef = useRef(shouldFit);
  const visibilityRef = useRef(mergeVisibility(seriesVisibility));
  const [internalVisibility, setInternalVisibility] = useState(
    mergeVisibility(seriesVisibility)
  );
  const [chartReady, setChartReady] = useState(0);

  const visibility = useMemo(
    () => mergeVisibility(seriesVisibility ?? internalVisibility),
    [internalVisibility, seriesVisibility]
  );

  const chartHeight = height ?? (mode === "compact" ? 180 : 360);
  const isDark = resolvedTheme === "dark";

  useEffect(() => {
    dataRef.current = data;
  }, [data]);

  useEffect(() => {
    shouldFitRef.current = shouldFit;
  }, [shouldFit]);

  useEffect(() => {
    visibilityRef.current = visibility;
  }, [visibility]);

  useEffect(() => {
    onVisibleRangeChangeRef.current = onVisibleRangeChange;
  }, [onVisibleRangeChange]);

  useEffect(() => {
    if (seriesVisibility) {
      setInternalVisibility(mergeVisibility(seriesVisibility));
    }
  }, [seriesVisibility]);

  const withSuppressedRangeEvents = useCallback((fn: () => void) => {
    suppressRangeEventRef.current = true;
    try {
      fn();
    } finally {
      window.setTimeout(() => {
        suppressRangeEventRef.current = false;
      }, 0);
    }
  }, []);

  const applyChartData = useCallback(
    (
      payload: KlinePayload | null,
      fit: boolean,
      restoreRange?: { fromMs: number; toMs: number } | null
    ) => {
      withSuppressedRangeEvents(() => {
        const candles = payload?.candles ?? [];
        const seriesData = buildSeriesData(candles);
        candleSeriesRef.current?.setData(seriesData.candlestick);
        inboundSeriesRef.current?.setData(seriesData.inbound);
        outboundSeriesRef.current?.setData(seriesData.outbound);
        netSeriesRef.current?.setData(seriesData.netChange);

        if (fit) {
          chartRef.current?.timeScale().fitContent();
        } else if (restoreRange) {
          chartRef.current?.timeScale().setVisibleRange({
            from: Math.floor(
              restoreRange.fromMs / 1000
            ) as import("lightweight-charts").UTCTimestamp,
            to: Math.floor(
              restoreRange.toMs / 1000
            ) as import("lightweight-charts").UTCTimestamp,
          });
        }
      });
    },
    [withSuppressedRangeEvents]
  );

  function applySeriesVisibility(next: KlineSeriesVisibility) {
    candleSeriesRef.current?.applyOptions({ visible: next.candlestick });
    inboundSeriesRef.current?.applyOptions({ visible: next.inbound });
    outboundSeriesRef.current?.applyOptions({ visible: next.outbound });
    netSeriesRef.current?.applyOptions({ visible: next.netChange });
  }

  useImperativeHandle(ref, () => ({
    fitContent() {
      withSuppressedRangeEvents(() => {
        chartRef.current?.timeScale().fitContent();
      });
    },
    getVisibleRangeMs() {
      const range = chartRef.current?.timeScale().getVisibleRange();
      if (!range) return null;
      return {
        fromMs: parseTimeToMs(range.from as string | number),
        toMs: parseTimeToMs(range.to as string | number),
      };
    },
  }), [withSuppressedRangeEvents]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let disposed = false;
    let resizeObserver: ResizeObserver | null = null;
    let rangeHandler:
      | ((range: import("lightweight-charts").IRange<
          import("lightweight-charts").Time
        > | null) => void)
      | null = null;

    void import("lightweight-charts").then((module) => {
      if (disposed || !containerRef.current) return;
      chartModuleRef.current = module;

      const theme = getChartTheme(resolvedTheme === "dark");
      const chart = module.createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: chartHeight,
        layout: theme.layout,
        grid: theme.grid,
        rightPriceScale: {
          borderVisible: false,
        },
        timeScale: {
          borderVisible: false,
          timeVisible: mode === "interactive",
          secondsVisible: false,
        },
        handleScroll: {
          mouseWheel: mode === "interactive",
          pressedMouseMove: mode === "interactive",
          horzTouchDrag: mode === "interactive",
          vertTouchDrag: mode === "interactive",
        },
        handleScale: {
          mouseWheel: mode === "interactive",
          pinch: mode === "interactive",
          axisPressedMouseMove: mode === "interactive",
        },
        crosshair: {
          mode: mode === "interactive" ? 0 : 2,
        },
      });

      const candleSeries = chart.addSeries(module.CandlestickSeries, {
        upColor: theme.upColor,
        downColor: theme.downColor,
        borderVisible: false,
        wickUpColor: theme.upColor,
        wickDownColor: theme.downColor,
        priceScaleId: "right",
      });
      const inboundSeries = chart.addSeries(module.HistogramSeries, {
        color: theme.inboundColor,
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      });
      const outboundSeries = chart.addSeries(module.HistogramSeries, {
        color: theme.outboundColor,
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      });
      const netSeries = chart.addSeries(module.LineSeries, {
        color: theme.netLineColor,
        lineWidth: 2,
        priceScaleId: "left",
      });

      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });
      chart.priceScale("left").applyOptions({
        visible: false,
        scaleMargins: { top: 0.85, bottom: 0 },
      });

      chartRef.current = chart;
      candleSeriesRef.current = candleSeries;
      inboundSeriesRef.current = inboundSeries;
      outboundSeriesRef.current = outboundSeries;
      netSeriesRef.current = netSeries;

      applyChartData(dataRef.current, shouldFitRef.current);
      applySeriesVisibility(visibilityRef.current);
      setChartReady((version) => version + 1);

      if (mode === "interactive" && onVisibleRangeChangeRef.current) {
        rangeHandler = (range) => {
          if (suppressRangeEventRef.current || !range) return;
          onVisibleRangeChangeRef.current?.({
            fromMs: parseTimeToMs(range.from as string | number),
            toMs: parseTimeToMs(range.to as string | number),
          });
        };
        chart.timeScale().subscribeVisibleTimeRangeChange(rangeHandler);
      }

      resizeObserver = new ResizeObserver((entries) => {
        const entry = entries[0];
        if (!entry || !chartRef.current) return;
        chartRef.current.applyOptions({ width: entry.contentRect.width });
      });
      resizeObserver.observe(containerRef.current);
    });

    return () => {
      disposed = true;
      if (rangeHandler && chartRef.current) {
        chartRef.current.timeScale().unsubscribeVisibleTimeRangeChange(rangeHandler);
      }
      resizeObserver?.disconnect();
      chartRef.current?.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      inboundSeriesRef.current = null;
      outboundSeriesRef.current = null;
      netSeriesRef.current = null;
    };
  }, [applyChartData, chartHeight, mode, resolvedTheme]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const theme = getChartTheme(isDark);
    chart.applyOptions({
      layout: theme.layout,
      grid: theme.grid,
    });
    candleSeriesRef.current?.applyOptions({
      upColor: theme.upColor,
      downColor: theme.downColor,
      wickUpColor: theme.upColor,
      wickDownColor: theme.downColor,
    });
    netSeriesRef.current?.applyOptions({ color: theme.netLineColor });
  }, [isDark]);

  useEffect(() => {
    if (!chartRef.current) return;
    const restoreRange = shouldFit ? null : pendingVisibleRange;
    applyChartData(data, shouldFit, restoreRange);
  }, [
    applyChartData,
    chartReady,
    data,
    pendingVisibleRange,
    pendingVisibleRangeVersion,
    shouldFit,
  ]);

  useEffect(() => {
    if (!chartRef.current) return;
    applySeriesVisibility(visibility);
  }, [visibility, chartReady]);

  function updateVisibility(key: keyof KlineSeriesVisibility, checked: boolean) {
    const next = { ...visibility, [key]: checked };
    setInternalVisibility(next);
    onSeriesVisibilityChange?.(next);
  }

  return (
    <div className={cn("space-y-2", className)}>
      {showLegend && (
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          {(
            [
              ["candlestick", "库存 K 线"],
              ["inbound", "入库"],
              ["outbound", "出库"],
              ["netChange", "净变化"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="inline-flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={visibility[key]}
                onChange={(event) => updateVisibility(key, event.target.checked)}
              />
              <span>{label}</span>
            </label>
          ))}
        </div>
      )}

      <div className="relative">
        <div ref={containerRef} style={{ height: chartHeight }} />
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-background/60 text-sm text-muted-foreground">
            加载中…
          </div>
        )}
        {!loading && (data?.candles.length ?? 0) === 0 && (
          <div className="pointer-events-none absolute inset-x-0 top-1/2 -translate-y-1/2 text-center text-sm text-muted-foreground">
            暂无趋势数据
          </div>
        )}
      </div>
    </div>
  );
});
