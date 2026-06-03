"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { HistoryFilters } from "@/components/history/HistoryFilters";
import { HistoryTable } from "@/components/history/HistoryTable";
import { fetchInboundHistory } from "@/lib/api";
import { subscribeDatabaseChanged } from "@/lib/database-events";
import type { DateRangeFilter, InboundRecord } from "@/types/account";

export default function InboundHistoryPage() {
  const [query, setQuery] = useState("");
  const [ranges, setRanges] = useState<DateRangeFilter[]>([]);
  const [records, setRecords] = useState<InboundRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadToken, setReloadToken] = useState(0);

  const rangeValues = useMemo(
    () => ranges.map((item) => item.value),
    [ranges]
  );

  const retry = useCallback(() => {
    setLoading(true);
    setReloadToken((value) => value + 1);
  }, []);

  useEffect(() => {
    let active = true;
    fetchInboundHistory({
      q: query,
      ranges: rangeValues,
    })
      .then((payload) => {
        if (!active) return;
        setRecords(payload);
        setError("");
      })
      .catch((requestError) => {
        if (!active) return;
        setError(
          requestError instanceof Error ? requestError.message : "入库历史读取失败"
        );
        setRecords([]);
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [query, rangeValues, reloadToken]);

  useEffect(
    () => subscribeDatabaseChanged(() => setReloadToken((value) => value + 1)),
    []
  );

  return (
    <div className="space-y-4">
      <HistoryFilters
        query={query}
        ranges={ranges}
        onQueryChange={setQuery}
        onRangesChange={setRanges}
      />

      <p className="text-sm text-muted-foreground">共 {records.length} 条入库记录</p>

      <HistoryTable
        mode="inbound"
        exportMode="inbound"
        records={records}
        loading={loading}
        error={error}
        emptyMessage="暂无入库历史记录"
        onRetry={retry}
      />
    </div>
  );
}
