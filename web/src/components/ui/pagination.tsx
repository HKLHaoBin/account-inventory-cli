"use client";

import { useRef } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface PaginationProps {
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  disabled?: boolean;
  className?: string;
}

export function Pagination({
  total,
  page,
  pageSize,
  totalPages,
  onPageChange,
  disabled = false,
  className,
}: PaginationProps) {
  const pageInputRef = useRef<HTMLInputElement>(null);
  const safeTotalPages = Math.max(1, totalPages);
  const canPrev = page > 1;
  const canNext = page < safeTotalPages;

  function goToPage(next: number) {
    const clamped = Math.min(Math.max(1, next), safeTotalPages);
    if (clamped !== page) {
      onPageChange(clamped);
    }
  }

  function commitPageInput() {
    const raw = pageInputRef.current?.value ?? String(page);
    const parsed = Number.parseInt(raw.trim(), 10);
    if (!Number.isFinite(parsed)) {
      if (pageInputRef.current) {
        pageInputRef.current.value = String(page);
      }
      return;
    }
    goToPage(parsed);
    if (pageInputRef.current) {
      pageInputRef.current.value = String(
        Math.min(Math.max(1, parsed), safeTotalPages)
      );
    }
  }

  if (total === 0) {
    return null;
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground",
        className
      )}
    >
      <p>
        共 {total} 条 · 每页 {pageSize} 条 · 第 {page}/{safeTotalPages} 页
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          disabled={disabled || !canPrev}
          onClick={() => goToPage(page - 1)}
          aria-label="上一页"
        >
          <ChevronLeft className="h-4 w-4" />
          上一页
        </Button>
        <div className="flex items-center gap-1.5">
          <span className="text-xs">跳至</span>
          <Input
            key={page}
            ref={pageInputRef}
            defaultValue={String(page)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                commitPageInput();
              }
            }}
            onBlur={commitPageInput}
            disabled={disabled}
            className="h-8 w-14 px-2 text-center text-xs"
            inputMode="numeric"
            aria-label="页码"
          />
          <span className="text-xs">页</span>
        </div>
        <Button
          variant="secondary"
          size="sm"
          disabled={disabled || !canNext}
          onClick={() => goToPage(page + 1)}
          aria-label="下一页"
        >
          下一页
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
