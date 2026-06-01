import { mockStats } from "@/lib/mock-data";

export function StatusBar() {
  return (
    <footer className="flex h-9 shrink-0 items-center justify-between border-t border-border bg-muted/50 px-6 text-xs text-muted-foreground">
      <span>库存 {mockStats.inventoryCount} 条</span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(22,163,74,0.6)]" />
        数据库已连接
      </span>
      <span>上次同步 刚刚</span>
    </footer>
  );
}
