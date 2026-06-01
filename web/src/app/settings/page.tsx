"use client";

import { useTheme } from "next-themes";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Database,
  DownloadCloud,
  Keyboard,
  Monitor,
  Moon,
  RefreshCw,
  ShieldCheck,
  Sun,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { APP_NAME, APP_VERSION, DB_PATH, SHORTCUTS } from "@/lib/constants";
import {
  checkForUpdate,
  fetchUpdateStatus,
  triggerUpdate,
} from "@/lib/api";
import type { UpdateStatusPayload } from "@/types/account";

function statusTone(state?: string) {
  if (state === "updated" || state === "idle") return "text-emerald-600";
  if (state === "error" || state === "rolled_back") return "text-red-600";
  if (state === "update_available") return "text-primary";
  return "text-amber-600";
}

function phaseLabel(phase?: string) {
  const labels: Record<string, string> = {
    idle: "空闲",
    checking: "检查中",
    downloading: "下载中",
    extracting: "解压中",
    backing_up: "备份中",
    applying: "应用中",
    stopping_backend: "停止后端",
    restarting: "重启中",
    rollback: "回滚中",
    completed: "已完成",
    failed: "失败",
    sleeping: "等待下次检查",
    launching: "已启动",
  };
  return labels[phase || ""] || phase || "未知";
}

function isBusy(status: UpdateStatusPayload | null) {
  return [
    "checking",
    "downloading",
    "extracting",
    "backup",
    "applying",
    "stopping",
    "restarting",
    "rollback",
    "launching",
  ].includes(status?.state || "");
}

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatusPayload | null>(null);
  const [updateError, setUpdateError] = useState("");
  const [updateToken, setUpdateToken] = useState("");
  const [checking, setChecking] = useState(false);
  const [triggering, setTriggering] = useState(false);

  const refreshUpdateStatus = useCallback(async () => {
    try {
      const payload = await fetchUpdateStatus();
      setUpdateStatus(payload);
      setUpdateError("");
    } catch (error) {
      setUpdateError(error instanceof Error ? error.message : "更新状态读取失败");
    }
  }, []);

  useEffect(() => {
    const mountTimer = window.setTimeout(() => setMounted(true), 0);
    const statusTimer = window.setTimeout(() => {
      void refreshUpdateStatus();
    }, 0);
    return () => {
      window.clearTimeout(mountTimer);
      window.clearTimeout(statusTimer);
    };
  }, [refreshUpdateStatus]);

  useEffect(() => {
    if (!isBusy(updateStatus)) return;
    const timer = window.setInterval(() => {
      void refreshUpdateStatus();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [refreshUpdateStatus, updateStatus]);

  const latestText = useMemo(() => {
    if (!updateStatus?.latest_tag) return "未检查";
    return updateStatus.latest_tag;
  }, [updateStatus]);

  async function handleCheckUpdate() {
    setChecking(true);
    try {
      const payload = await checkForUpdate();
      setUpdateStatus(payload);
      setUpdateError("");
    } catch (error) {
      setUpdateError(error instanceof Error ? error.message : "检查更新失败");
    } finally {
      setChecking(false);
    }
  }

  async function handleTriggerUpdate() {
    setTriggering(true);
    try {
      const payload = await triggerUpdate(updateToken);
      setUpdateStatus(payload);
      setUpdateError("");
    } catch (error) {
      setUpdateError(error instanceof Error ? error.message : "触发更新失败");
    } finally {
      setTriggering(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">设置</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          应用配置与快捷键说明
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <DownloadCloud className="h-4 w-4" />
            应用更新
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 rounded-xl border border-border bg-muted/30 p-4 text-sm sm:grid-cols-2">
            <div>
              <p className="text-xs text-muted-foreground">当前版本</p>
              <p className="mt-1 font-mono text-foreground">
                {updateStatus?.local_version || APP_VERSION}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">最新版本</p>
              <p className="mt-1 font-mono text-foreground">{latestText}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">阶段</p>
              <p className="mt-1 text-foreground">
                {phaseLabel(updateStatus?.phase)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">状态</p>
              <p className={`mt-1 flex items-center gap-1.5 ${statusTone(updateStatus?.state)}`}>
                {updateStatus?.state === "error" || updateStatus?.state === "rolled_back" ? (
                  <AlertCircle className="h-4 w-4" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                {updateStatus?.message || "未检查"}
              </p>
            </div>
          </div>

          {updateStatus?.updated_targets && updateStatus.updated_targets.length > 0 && (
            <p className="text-xs text-muted-foreground">
              已更新：{updateStatus.updated_targets.join("、")}
            </p>
          )}

          {(updateError || updateStatus?.rollback_reason) && (
            <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {updateError || updateStatus?.rollback_reason}
            </div>
          )}

          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm font-medium">
              <ShieldCheck className="h-4 w-4" />
              管理令牌
            </label>
            <Input
              type="password"
              value={updateToken}
              onChange={(event) => setUpdateToken(event.target.value)}
              placeholder="执行更新时需要"
              autoComplete="off"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void refreshUpdateStatus()}
              disabled={checking || triggering}
            >
              <RefreshCw className="h-4 w-4" />
              刷新状态
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void handleCheckUpdate()}
              disabled={checking || triggering}
            >
              <RefreshCw className={checking ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
              检查更新
            </Button>
            <Button
              size="sm"
              onClick={() => void handleTriggerUpdate()}
              disabled={checking || triggering || !updateToken.trim()}
            >
              <DownloadCloud className={triggering ? "h-4 w-4 animate-bounce" : "h-4 w-4"} />
              执行更新
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Database className="h-4 w-4" />
            数据库路径
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-xl border border-border bg-muted/30 px-4 py-3 font-mono text-sm">
            {DB_PATH}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            只读显示 · 由 Python CLI 管理
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Keyboard className="h-4 w-4" />
            快捷键
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="divide-y divide-border">
            {SHORTCUTS.map((s) => (
              <div
                key={s.key}
                className="flex items-center justify-between py-3 first:pt-0 last:pb-0"
              >
                <span className="text-sm">{s.description}</span>
                <kbd className="rounded-lg border border-border bg-muted px-2.5 py-1 font-mono text-xs">
                  {s.key}
                </kbd>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            {mounted && theme === "dark" ? (
              <Moon className="h-4 w-4" />
            ) : (
              <Sun className="h-4 w-4" />
            )}
            主题
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Button
              variant={mounted && theme === "light" ? "primary" : "secondary"}
              size="sm"
              onClick={() => setTheme("light")}
            >
              <Sun className="h-4 w-4" />
              浅色
            </Button>
            <Button
              variant={mounted && theme === "dark" ? "primary" : "secondary"}
              size="sm"
              onClick={() => setTheme("dark")}
            >
              <Moon className="h-4 w-4" />
              深色
            </Button>
            <Button
              variant={mounted && theme === "system" ? "primary" : "secondary"}
              size="sm"
              onClick={() => setTheme("system")}
            >
              <Monitor className="h-4 w-4" />
              跟随系统
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">关于</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            <span className="font-medium text-foreground">{APP_NAME}</span>
          </p>
          <p>
            版本{" "}
            <span className="font-mono text-foreground">
              {updateStatus?.local_version || APP_VERSION}
            </span>
          </p>
          <p>
            仪表盘已连接本地 Python API，其余页面会逐步接入真实数据。
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
