"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { HistoryFilters } from "@/components/history/HistoryFilters";
import { HistoryTable } from "@/components/history/HistoryTable";
import { Pagination } from "@/components/ui/pagination";
import {
  commitOutboundFromInboundHistory,
  DEFAULT_PAGE_SIZE,
  fetchInboundHistory,
} from "@/lib/api";
import { runHistoryQuickAction } from "@/lib/clipboard-actions";
import { subscribeDatabaseChanged } from "@/lib/database-events";
import type { DateRangeFilter, HistoryRecord, InboundRecord } from "@/types/account";

export default function InboundHistoryPage() {
  const [query, setQuery] = useState("");
  const [ranges, setRanges] = useState<DateRangeFilter[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [records, setRecords] = useState<InboundRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadToken, setReloadToken] = useState(0);

  const rangeValues = useMemo(
    () => ranges.map((item) => item.value),
    [ranges]
  );

  const exportFilters = useMemo(
    () => ({
      type: "inbound" as const,
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
      try {
        const payload = await fetchInboundHistory({
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
        setError("");
      } catch (requestError) {
        if (ignoreResult?.()) return;
        setError(
          requestError instanceof Error ? requestError.message : "入库历史读取失败"
        );
        setRecords([]);
        setTotal(0);
        setTotalPages(1);
      } finally {
        if (!ignoreResult?.()) setLoading(false);
      }
    },
    [query, rangeValues, page, pageSize]
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

  const handleOutboundFromInbound = useCallback(
    async (record: InboundRecord | HistoryRecord) => {
      await runHistoryQuickAction(
        () => commitOutboundFromInboundHistory(record),
        () => setReloadToken((value) => value + 1)
      );
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

      <p className="text-sm text-muted-foreground">共 {total} 条入库记录</p>

      <HistoryTable
        mode="inbound"
        exportMode="inbound"
        records={records}
        total={total}
        exportFilters={exportFilters}
        loading={loading}
        error={error}
        emptyMessage="暂无入库历史记录"
        onRetry={retry}
        onOutboundFromInbound={handleOutboundFromInbound}
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
