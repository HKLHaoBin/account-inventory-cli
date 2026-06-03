"use client";

import { useCallback, useRef, useState } from "react";

export function useCategoryStatusFilter<C extends string>() {
  const listRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<Set<C>>(() => new Set());

  const isFiltering = selected.size > 0;

  const matches = useCallback(
    (category: C) => selected.size === 0 || selected.has(category),
    [selected]
  );

  const toggle = useCallback((category: C) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
    listRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  return { listRef, selected, isFiltering, matches, toggle };
}
