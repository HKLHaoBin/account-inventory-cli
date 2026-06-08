"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { LineChart } from "lucide-react";
import { InventoryKlineChart } from "@/components/history/InventoryKlineChart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { fetchHistoryKline } from "@/lib/api";
import { subscribeDatabaseChanged } from "@/lib/database-events";
import {
  defaultTrendRangeMs,
  formatLocalDateTime,
} from "@/lib/kline-time";
import type { KlinePayload } from "@/types/account";

// Compact preview only: no zoom refetch; full pan/zoom at /history/trends.
export function DashboardTrendCard() {
  const abortRef = useRef<AbortController | null>(null);
  const [data, setData] = useState<KlinePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadToken, setReloadToken] = useState(0);

  const loadTrend = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const range = defaultTrendRangeMs(30);
    setLoading(true);
    setError("");

    try {
      const payload = await fetchHistoryKline(
        {
          from: formatLocalDateTime(range.fromMs),
          to: formatLocalDateTime(range.toMs),
          bucket: "day",
        },
        { signal: controller.signal }
      );
      if (controller.signal.aborted) return;
      setData(payload);
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
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadTrend();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadTrend, reloadToken]);

  useEffect(
    () =>
      subscribeDatabaseChanged(() => {
        setReloadToken((value) => value + 1);
      }),
    []
  );

  useEffect(() => () => abortRef.current?.abort(), []);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3 p-4 pb-3 sm:p-6 sm:pb-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <LineChart className="h-4 w-4 text-primary" />
          <Link href="/history/trends" className="hover:underline">
            近 30 天库存趋势
          </Link>
        </CardTitle>
        <Link
          href="/history/trends"
          className="inline-flex h-8 items-center rounded-[10px] px-3 text-xs font-medium hover:bg-muted"
        >
          查看详情
        </Link>
      </CardHeader>
      <CardContent className="p-4 pt-0 sm:p-6 sm:pt-0">
        {error ? (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-dashed border-border px-4 py-6 text-sm text-muted-foreground">
            <span>{error}</span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setReloadToken((value) => value + 1)}
            >
              重试
            </Button>
          </div>
        ) : (
          <InventoryKlineChart
            mode="compact"
            data={data}
            loading={loading}
            shouldFit
            showLegend={false}
          />
        )}
      </CardContent>
    </Card>
  );
}
