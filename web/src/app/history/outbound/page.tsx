"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { HistoryFilters } from "@/components/history/HistoryFilters";
import { HistoryTable } from "@/components/history/HistoryTable";
import { Pagination } from "@/components/ui/pagination";
import {
  commitReInboundFromHistory,
  DEFAULT_PAGE_SIZE,
  fetchOutboundHistory,
  writeAppClipboardText,
} from "@/lib/api";
import { subscribeDatabaseChanged } from "@/lib/database-events";
import type { DateRangeFilter, HistoryRecord, OutboundRecord } from "@/types/account";

export default function OutboundHistoryPage() {
  const [query, setQuery] = useState("");
  const [ranges, setRanges] = useState<DateRangeFilter[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [records, setRecords] = useState<OutboundRecord[]>([]);
  const [inventoryUsernames, setInventoryUsernames] = useState<Set<string>>(
    new Set()
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadToken, setReloadToken] = useState(0);

  const rangeValues = useMemo(
    () => ranges.map((item) => item.value),
    [ranges]
  );

  const exportFilters = useMemo(
    () => ({
      type: "outbound" as const,
      q: query,
      ranges: rangeValues,
    }),
    [query, rangeValues]
  );

  const retry = useCallback(() => {
    setReloadToken((value) => value + 1);
  }, []);

  const loadHistory = useCallback(
    async (ignoreResult?: () => boolean) => {
      setLoading(true);
      setError("");
      try {
        const payload = await fetchOutboundHistory({
          q: query,
          ranges: rangeValues,
          page,
          pageSize,
        });
        if (ignoreResult?.()) return;
        if (payload.records.length === 0 && page > 1) {
          setPage((current) => Math.max(1, current - 1));
          return;
        }
        setRecords(payload.records);
        setTotal(payload.total);
        setTotalPages(payload.totalPages);
        setInventoryUsernames(new Set(payload.inventoryUsernames ?? []));
      } catch (requestError) {
        if (ignoreResult?.()) return;
        setError(
          requestError instanceof Error ? requestError.message : "出库历史读取失败"
        );
        setRecords([]);
        setTotal(0);
        setTotalPages(1);
        setInventoryUsernames(new Set());
      } finally {
        if (!ignoreResult?.()) setLoading(false);
      }
    },
    [page, pageSize, query, rangeValues]
  );

  useEffect(() => {
    let ignore = false;
    const timer = window.setTimeout(() => {
      void loadHistory(() => ignore);
    }, 0);
    return () => {
      ignore = true;
      window.clearTimeout(timer);
    };
  }, [loadHistory, reloadToken]);

  useEffect(
    () =>
      subscribeDatabaseChanged(() => {
        setPage(1);
        setReloadToken((value) => value + 1);
      }),
    []
  );

  const handleReInbound = useCallback(
    async (record: OutboundRecord | HistoryRecord) => {
      const payload = await commitReInboundFromHistory(record);
      await writeAppClipboardText(payload.clipboardText);
      setReloadToken((value) => value + 1);
    },
    []
  );

  return (
    <div className="space-y-4">
      <HistoryFilters
        query={query}
        ranges={ranges}
        onQueryChange={(value) => {
          setPage(1);
          setQuery(value);
        }}
        onRangesChange={(value) => {
          setPage(1);
          setRanges(value);
        }}
      />

      <p className="text-sm text-muted-foreground">共 {total} 条出库记录</p>

      <HistoryTable
        mode="outbound"
        exportMode="outbound"
        records={records}
        total={total}
        exportFilters={exportFilters}
        loading={loading}
        error={error}
        emptyMessage="暂无出库历史记录"
        onRetry={retry}
        inventoryUsernames={inventoryUsernames}
        onReInbound={handleReInbound}
      />

      <Pagination
        total={total}
        page={page}
        pageSize={pageSize}
        totalPages={totalPages}
        onPageChange={setPage}
        disabled={loading}
      />
    </div>
  );
}
