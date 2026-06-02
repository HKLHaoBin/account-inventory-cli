"use client";

import { useMemo, useState } from "react";
import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { DateRangeFilter } from "@/types/account";

interface HistoryFiltersProps {
  query: string;
  ranges: DateRangeFilter[];
  onQueryChange: (value: string) => void;
  onRangesChange: (ranges: DateRangeFilter[]) => void;
  placeholder?: string;
}

function formatRangeLabel(start: string, end: string): string {
  if (start === end) return start;
  return `${start}..${end}`;
}

function buildRangeValue(start: string, end: string): string {
  return formatRangeLabel(start, end);
}

export function HistoryFilters({
  query,
  ranges,
  onQueryChange,
  onRangesChange,
  placeholder = "搜索账号、邮箱、网址或日期…",
}: HistoryFiltersProps) {
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const canAddRange = useMemo(
    () => Boolean(startDate || endDate),
    [startDate, endDate]
  );

  const addRange = () => {
    const start = startDate || endDate;
    const end = endDate || startDate;
    if (!start || !end) return;

    const value = buildRangeValue(start, end);
    if (ranges.some((item) => item.value === value)) {
      setStartDate("");
      setEndDate("");
      return;
    }

    onRangesChange([
      ...ranges,
      {
        label: formatRangeLabel(start, end),
        value,
      },
    ]);
    setStartDate("");
    setEndDate("");
  };

  const removeRange = (value: string) => {
    onRangesChange(ranges.filter((item) => item.value !== value));
  };

  return (
    <div className="space-y-3">
      <Input
        placeholder={placeholder}
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        className="max-w-xl"
      />

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">起始日期</label>
          <Input
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
            className="w-[180px]"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">结束日期</label>
          <Input
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
            className="w-[180px]"
          />
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!canAddRange}
          onClick={addRange}
        >
          <Plus className="mr-1 h-3.5 w-3.5" />
          添加时段
        </Button>
      </div>

      {ranges.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {ranges.map((range) => (
            <button
              key={range.value}
              type="button"
              onClick={() => removeRange(range.value)}
              className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/40 px-3 py-1 text-xs hover:bg-muted"
            >
              <span>{range.label}</span>
              <X className="h-3 w-3" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
