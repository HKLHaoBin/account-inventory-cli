"use client";

import { useEffect, useState } from "react";
import { fetchDashboard } from "@/lib/api";

export function StatusBar() {
  const [inventoryCount, setInventoryCount] = useState<number | null>(null);
  const [syncText, setSyncText] = useState("同步中");
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function refresh() {
      try {
        const payload = await fetchDashboard();
        if (cancelled) return;
        setInventoryCount(payload.stats.inventoryCount);
        setConnected(true);
        setSyncText("刚刚");
      } catch {
        if (cancelled) return;
        setConnected(false);
        setSyncText("连接失败");
      }
    }

    const timer = window.setTimeout(() => {
      void refresh();
    }, 0);
    const interval = window.setInterval(() => {
      void refresh();
    }, 15000);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      window.clearInterval(interval);
    };
  }, []);

  return (
    <footer className="flex h-9 shrink-0 items-center justify-between border-t border-border bg-muted/50 px-6 text-xs text-muted-foreground">
      <span>库存 {inventoryCount ?? "-"} 条</span>
      <span className="flex items-center gap-1.5">
        <span
          className={
            connected
              ? "inline-block h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(22,163,74,0.6)]"
              : "inline-block h-1.5 w-1.5 rounded-full bg-amber-500"
          }
        />
        {connected ? "数据库已连接" : "数据库未连接"}
      </span>
      <span>上次同步 {syncText}</span>
    </footer>
  );
}
