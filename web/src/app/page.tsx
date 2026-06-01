"use client";

import Link from "next/link";
import {
  Package,
  Download,
  Upload,
  Clipboard,
  ArrowDownToLine,
  ArrowUpFromLine,
} from "lucide-react";
import { StatCard } from "@/components/ui/stat-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  mockActivities,
  mockInventory,
  mockStats,
} from "@/lib/mock-data";
import { formatRelativeTime, maskValue } from "@/lib/utils";

export default function DashboardPage() {
  const fifoPreview = mockInventory.slice(0, 5);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">仪表盘</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          一屏掌握库存状态与最近动态
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="当前库存"
          value={mockStats.inventoryCount}
          subtitle="条账号"
          icon={Package}
          variant="default"
        />
        <StatCard
          title="今日入库"
          value={mockStats.todayInbound}
          subtitle="条"
          icon={ArrowDownToLine}
          variant="success"
        />
        <StatCard
          title="今日出库"
          value={mockStats.todayOutbound}
          subtitle="条"
          icon={ArrowUpFromLine}
          variant="info"
        />
        <StatCard
          title="待处理"
          value={mockStats.pendingCount}
          subtitle="待确认批次"
          icon={Clipboard}
          variant="warning"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Link href="/inbound" className="group">
          <Card className="h-full transition-all hover:shadow-[0_8px_30px_rgba(30,64,175,0.12)] hover:-translate-y-0.5">
            <CardContent className="flex flex-col items-center gap-3 p-6 pt-6 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-600">
                <Download className="h-6 w-6" />
              </div>
              <div>
                <p className="font-semibold">批量入库</p>
                <p className="mt-1 text-xs text-muted-foreground group-hover:text-foreground/70">
                  粘贴多行账号，实时分类预览
                </p>
              </div>
            </CardContent>
          </Card>
        </Link>
        <Link href="/outbound" className="group">
          <Card className="h-full transition-all hover:shadow-[0_8px_30px_rgba(30,64,175,0.12)] hover:-translate-y-0.5">
            <CardContent className="flex flex-col items-center gap-3 p-6 pt-6 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Upload className="h-6 w-6" />
              </div>
              <div>
                <p className="font-semibold">FIFO 出库</p>
                <p className="mt-1 text-xs text-muted-foreground group-hover:text-foreground/70">
                  按入库顺序取出并复制
                </p>
              </div>
            </CardContent>
          </Card>
        </Link>
        <Card className="group cursor-pointer transition-all hover:shadow-[0_8px_30px_rgba(30,64,175,0.12)] hover:-translate-y-0.5">
          <CardContent className="flex flex-col items-center gap-3 p-6 pt-6 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-500/10 text-violet-600">
              <Clipboard className="h-6 w-6" />
            </div>
            <div>
              <p className="font-semibold">从剪贴板导入</p>
              <p className="mt-1 text-xs text-muted-foreground">
                检测到 3 条合法账号
              </p>
              <Button size="sm" className="mt-3" variant="secondary">
                点击导入
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            FIFO 预览
            <Badge variant="fifo">将按此顺序出库</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-3 overflow-x-auto pb-2">
            {fifoPreview.map((account, i) => (
              <div
                key={account.id}
                className="flex min-w-[160px] shrink-0 flex-col gap-1 rounded-xl border border-border bg-muted/30 p-3"
              >
                {i === 0 && (
                  <Badge variant="fifo" className="w-fit text-[10px]">
                    队首
                  </Badge>
                )}
                <span className="font-mono text-sm font-medium">
                  {account.username}
                </span>
                <span className="text-xs text-muted-foreground">
                  {maskValue(account.password)}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">最近活动</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="divide-y divide-border">
            {mockActivities.slice(0, 10).map((activity) => (
              <div
                key={activity.id}
                className="flex items-center justify-between py-3 first:pt-0 last:pb-0"
              >
                <div className="flex items-center gap-3">
                  <Badge
                    variant={
                      activity.type === "inbound" ? "success" : "info"
                    }
                  >
                    {activity.type === "inbound" ? "入库" : "出库"}
                  </Badge>
                  <span className="font-mono text-sm">{activity.username}</span>
                </div>
                <span className="text-xs text-muted-foreground">
                  {formatRelativeTime(activity.timestamp)}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
