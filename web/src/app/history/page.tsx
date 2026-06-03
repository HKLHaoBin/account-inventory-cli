"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { HistoryFilters } from "@/components/history/HistoryFilters";
import { HistoryTable } from "@/components/history/HistoryTable";
import { commitReInboundFromHistory, fetchInventory, fetchUnifiedHistory } from "@/lib/api";
import { subscribeDatabaseChanged } from "@/lib/database-events";
import type { DateRangeFilter, HistoryRecord, OutboundRecord } from "@/types/account";

export default function HistoryPage() {
  const [query, setQuery] = useState("");
  const [ranges, setRanges] = useState<DateRangeFilter[]>([]);
  const [records, setRecords] = useState<HistoryRecord[]>([]);
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

  const retry = useCallback(() => {
    setLoading(true);
    setReloadToken((value) => value + 1);
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchUnifiedHistory({
        type: "all",
        q: query,
        ranges: rangeValues,
      }),
      fetchInventory(),
    ])
      .then(([historyPayload, inventoryPayload]) => {
        if (!active) return;
        setRecords(historyPayload);
        setInventoryUsernames(
          new Set(inventoryPayload.map((item) => item.username))
        );
        setError("");
      })
      .catch((requestError) => {
        if (!active) return;
        setError(
          requestError instanceof Error ? requestError.message : "历史流水读取失败"
        );
        setRecords([]);
        setInventoryUsernames(new Set());
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

  const handleReInbound = useCallback(
    async (record: OutboundRecord | HistoryRecord) => {
      await commitReInboundFromHistory(record);
      setReloadToken((value) => value + 1);
    },
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

      <p className="text-sm text-muted-foreground">共 {records.length} 条记录</p>

      <HistoryTable
        mode="all"
        exportMode="all"
        records={records}
        loading={loading}
        error={error}
        emptyMessage="暂无历史流水记录"
        onRetry={retry}
        inventoryUsernames={inventoryUsernames}
        onReInbound={handleReInbound}
      />
    </div>
  );
}
