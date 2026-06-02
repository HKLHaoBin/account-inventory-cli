import { HistoryNav } from "@/components/history/HistoryNav";

export default function HistoryLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">历史流水</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          查看入库与出库历史，支持文本与时段筛选
        </p>
      </div>

      <HistoryNav />

      {children}
    </div>
  );
}
