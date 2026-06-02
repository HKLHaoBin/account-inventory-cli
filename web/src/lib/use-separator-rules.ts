"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchSeparatorRules } from "@/lib/api";
import { subscribeDatabaseChanged } from "@/lib/database-events";
import { subscribeSeparatorRulesChanged } from "@/lib/separator-rules-events";
import type { SeparatorRule } from "@/types/account";

export function useSeparatorRules(): {
  rules: SeparatorRule[];
  enabledSeparators: string[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
} {
  const [rules, setRules] = useState<SeparatorRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const nextRules = await fetchSeparatorRules();
      setRules(nextRules);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载分隔规则失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh();
    }, 0);
    const unsubscribeDatabase = subscribeDatabaseChanged(() => {
      void refresh();
    });
    const unsubscribeRules = subscribeSeparatorRulesChanged(() => {
      void refresh();
    });
    return () => {
      window.clearTimeout(timer);
      unsubscribeDatabase();
      unsubscribeRules();
    };
  }, [refresh]);

  const enabledSeparators = useMemo(
    () => rules.filter((rule) => rule.enabled).map((rule) => rule.separator),
    [rules]
  );

  return { rules, enabledSeparators, loading, error, refresh };
}
