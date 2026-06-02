"use client";

import { useTheme } from "next-themes";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Copy,
  Database,
  DownloadCloud,
  Keyboard,
  Monitor,
  Moon,
  RefreshCw,
  Scissors,
  ShieldCheck,
  Sun,
  Trash2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { APP_NAME, APP_VERSION, DB_PATH, SHORTCUTS } from "@/lib/constants";
import {
  checkForUpdate,
  cloneDatabase,
  createSeparatorRule,
  deleteDatabase,
  deleteSeparatorRule,
  fetchDashboard,
  fetchSeparatorRules,
  fetchUpdateStatus,
  renameDatabase,
  triggerUpdate,
  updateSeparatorRule,
} from "@/lib/api";
import { emitDatabaseChanged, subscribeDatabaseChanged } from "@/lib/database-events";
import {
  emitSeparatorRulesChanged,
  subscribeSeparatorRulesChanged,
} from "@/lib/separator-rules-events";
import type { DatabaseInfo, SeparatorRule, UpdateStatusPayload } from "@/types/account";

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
  const [database, setDatabase] = useState<DatabaseInfo | null>(null);
  const [databaseName, setDatabaseName] = useState("");
  const [databaseError, setDatabaseError] = useState("");
  const [renamingDatabase, setRenamingDatabase] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteToken, setDeleteToken] = useState("");
  const [deletingDatabase, setDeletingDatabase] = useState(false);
  const [cloneOpen, setCloneOpen] = useState(false);
  const [cloneName, setCloneName] = useState("");
  const [cloningDatabase, setCloningDatabase] = useState(false);
  const [separatorRules, setSeparatorRules] = useState<SeparatorRule[]>([]);
  const [separatorRulesError, setSeparatorRulesError] = useState("");
  const [newRuleName, setNewRuleName] = useState("");
  const [newRuleSeparator, setNewRuleSeparator] = useState("");
  const [addingRule, setAddingRule] = useState(false);
  const [updatingRuleId, setUpdatingRuleId] = useState<string | null>(null);
  const [deletingRuleId, setDeletingRuleId] = useState<string | null>(null);

  const refreshUpdateStatus = useCallback(async () => {
    try {
      const payload = await fetchUpdateStatus();
      setUpdateStatus(payload);
      setUpdateError("");
    } catch (error) {
      setUpdateError(error instanceof Error ? error.message : "更新状态读取失败");
    }
  }, []);

  const refreshDatabase = useCallback(async () => {
    try {
      const payload = await fetchDashboard();
      setDatabase(payload.database);
      setDatabaseName(payload.database.name);
      setDatabaseError("");
    } catch (error) {
      setDatabaseError(error instanceof Error ? error.message : "数据库状态读取失败");
    }
  }, []);

  const refreshSeparatorRules = useCallback(async () => {
    try {
      const rules = await fetchSeparatorRules();
      setSeparatorRules(rules);
      setSeparatorRulesError("");
    } catch (error) {
      setSeparatorRulesError(
        error instanceof Error ? error.message : "分隔规则读取失败"
      );
    }
  }, []);

  useEffect(() => {
    const mountTimer = window.setTimeout(() => setMounted(true), 0);
    const statusTimer = window.setTimeout(() => {
      void refreshUpdateStatus();
      void refreshDatabase();
      void refreshSeparatorRules();
    }, 0);
    return () => {
      window.clearTimeout(mountTimer);
      window.clearTimeout(statusTimer);
    };
  }, [refreshDatabase, refreshSeparatorRules, refreshUpdateStatus]);

  useEffect(
    () =>
      subscribeDatabaseChanged(() => {
        void refreshDatabase();
        void refreshSeparatorRules();
      }),
    [refreshDatabase, refreshSeparatorRules]
  );

  useEffect(
    () => subscribeSeparatorRulesChanged(() => void refreshSeparatorRules()),
    [refreshSeparatorRules]
  );

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

  const rateLimitText = useMemo(() => {
    if (updateStatus?.state !== "error" || !updateStatus.github_rate_limit_reset_at) return "";
    return `GitHub API 暂时限流，重置时间：${updateStatus.github_rate_limit_reset_at}。请稍后重试；高级用户可配置 UPDATER_GITHUB_TOKEN。`;
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

  async function handleRenameDatabase() {
    if (!database) return;
    const name = databaseName.trim();
    if (!name) {
      setDatabaseError("数据库名称不能为空");
      return;
    }
    setRenamingDatabase(true);
    try {
      const next = await renameDatabase(database.id, name);
      setDatabase(next);
      setDatabaseName(next.name);
      setDatabaseError("");
      emitDatabaseChanged(next.id);
    } catch (error) {
      setDatabaseError(error instanceof Error ? error.message : "数据库重命名失败");
    } finally {
      setRenamingDatabase(false);
    }
  }

  async function handleDeleteDatabase() {
    if (!database) return;
    setDeletingDatabase(true);
    try {
      const next = await deleteDatabase(database.id, deleteToken);
      setDatabase(next);
      setDatabaseName(next.name);
      setDeleteToken("");
      setDeleteOpen(false);
      setDatabaseError("");
      emitDatabaseChanged(next.id);
    } catch (error) {
      setDatabaseError(error instanceof Error ? error.message : "数据库删除失败");
    } finally {
      setDeletingDatabase(false);
    }
  }

  async function handleCloneDatabase() {
    if (!database) return;
    const name = cloneName.trim();
    if (!name) {
      setDatabaseError("数据库名称不能为空");
      return;
    }
    setCloningDatabase(true);
    try {
      const next = await cloneDatabase(database.id, name);
      setDatabase(next);
      setDatabaseName(next.name);
      setCloneName("");
      setCloneOpen(false);
      setDatabaseError("");
      emitDatabaseChanged(next.id);
    } catch (error) {
      setDatabaseError(error instanceof Error ? error.message : "数据库克隆失败");
    } finally {
      setCloningDatabase(false);
    }
  }

  async function handleAddSeparatorRule() {
    const name = newRuleName.trim();
    const separator = newRuleSeparator.trim();
    if (!name || !separator) {
      setSeparatorRulesError("规则名称和分隔符不能为空");
      return;
    }
    setAddingRule(true);
    try {
      await createSeparatorRule(name, separator);
      setNewRuleName("");
      setNewRuleSeparator("");
      setSeparatorRulesError("");
      await refreshSeparatorRules();
      emitSeparatorRulesChanged();
    } catch (error) {
      setSeparatorRulesError(
        error instanceof Error ? error.message : "添加分隔规则失败"
      );
    } finally {
      setAddingRule(false);
    }
  }

  async function handleToggleSeparatorRule(rule: SeparatorRule) {
    setUpdatingRuleId(rule.id);
    try {
      await updateSeparatorRule(rule.id, { enabled: !rule.enabled });
      setSeparatorRulesError("");
      await refreshSeparatorRules();
      emitSeparatorRulesChanged();
    } catch (error) {
      setSeparatorRulesError(
        error instanceof Error ? error.message : "更新分隔规则失败"
      );
    } finally {
      setUpdatingRuleId(null);
    }
  }

  async function handleDeleteSeparatorRule(ruleId: string) {
    setDeletingRuleId(ruleId);
    try {
      await deleteSeparatorRule(ruleId);
      setSeparatorRulesError("");
      await refreshSeparatorRules();
      emitSeparatorRulesChanged();
    } catch (error) {
      setSeparatorRulesError(
        error instanceof Error ? error.message : "删除分隔规则失败"
      );
    } finally {
      setDeletingRuleId(null);
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

          {rateLimitText && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
              {rateLimitText}
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
            <div className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
              <p>管理令牌来自环境变量 UPDATE_ADMIN_TOKEN，用于执行更新和删除数据库。</p>
              <div className="mt-2 space-y-1 font-mono text-foreground">
                <p>$env:UPDATE_ADMIN_TOKEN=&quot;your-token&quot;; python app.py</p>
                <p>setx UPDATE_ADMIN_TOKEN &quot;your-token&quot;</p>
              </div>
              <p className="mt-2">使用 setx 后需重启应用，前端输入同一令牌即可通过校验。</p>
            </div>
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
            当前数据库
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 rounded-xl border border-border bg-muted/30 p-4 text-sm sm:grid-cols-3">
            <div>
              <p className="text-xs text-muted-foreground">当前名称</p>
              <p className="mt-1 font-medium text-foreground">
                {database?.name || "读取中"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">当前库存</p>
              <p className="mt-1 font-mono text-foreground">
                {database?.inventoryCount ?? "-"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">今日出入库</p>
              <p className="mt-1 font-mono text-foreground">
                {database
                  ? `${database.todayInbound} / ${database.todayOutbound}`
                  : "-"}
              </p>
            </div>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">数据库路径</p>
            <div className="mt-1 rounded-xl border border-border bg-muted/30 px-4 py-3 font-mono text-sm">
              {database?.path || DB_PATH}
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">数据库名称</label>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                value={databaseName}
                onChange={(event) => setDatabaseName(event.target.value)}
                placeholder="数据库名称"
              />
              <Button
                size="sm"
                className="sm:h-10"
                onClick={() => void handleRenameDatabase()}
                disabled={
                  renamingDatabase ||
                  !database ||
                  !databaseName.trim() ||
                  databaseName.trim() === database.name
                }
              >
                保存名称
              </Button>
            </div>
          </div>
          {databaseError && (
            <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {databaseError}
            </div>
          )}
          <div className="flex flex-wrap gap-2 border-t border-border pt-4">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setCloneName("");
                setCloneOpen(true);
              }}
              disabled={!database}
            >
              <Copy className="h-4 w-4" />
              克隆当前数据库
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={() => {
                setDeleteToken("");
                setDeleteOpen(true);
              }}
              disabled={!database}
            >
              删除当前数据库
            </Button>
          </div>
          <div>
            <p className="mt-2 text-xs text-muted-foreground">
              删除后会自动切换到其他数据库；若没有剩余数据库，会创建新的空默认数据库。
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Scissors className="h-4 w-4" />
            分隔规则
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            输入解析使用当前数据库已启用的分隔符；复制与展示仍统一为
            <span className="font-mono text-foreground"> ---- </span>
            格式。
          </p>
          {separatorRules.length === 0 ? (
            <p className="rounded-xl border border-dashed border-border px-4 py-3 text-sm text-muted-foreground">
              {separatorRulesError ? "读取失败" : "加载分隔规则中…"}
            </p>
          ) : (
            <div className="divide-y divide-border rounded-xl border border-border">
              {separatorRules.map((rule) => (
                <div
                  key={rule.id}
                  className="flex flex-col gap-3 px-4 py-3 first:pt-3 last:pb-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0 space-y-1">
                    <p className="text-sm font-medium text-foreground">
                      {rule.builtIn ? "默认规则" : rule.name}
                    </p>
                    <p className="font-mono text-xs text-muted-foreground">
                      {rule.separator}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-border"
                        checked={rule.enabled}
                        disabled={
                          updatingRuleId === rule.id || deletingRuleId === rule.id
                        }
                        onChange={() => void handleToggleSeparatorRule(rule)}
                      />
                      启用
                    </label>
                    {!rule.builtIn && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        disabled={
                          deletingRuleId === rule.id || updatingRuleId === rule.id
                        }
                        onClick={() => void handleDeleteSeparatorRule(rule.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                        删除
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="space-y-2 border-t border-border pt-4">
            <p className="text-sm font-medium">添加规则</p>
            <div className="grid gap-2 sm:grid-cols-2">
              <Input
                value={newRuleName}
                onChange={(event) => setNewRuleName(event.target.value)}
                placeholder="规则名称"
              />
              <Input
                value={newRuleSeparator}
                onChange={(event) => setNewRuleSeparator(event.target.value)}
                placeholder="分隔符，例如 ::::"
                className="font-mono"
              />
            </div>
            <Button
              size="sm"
              onClick={() => void handleAddSeparatorRule()}
              disabled={
                addingRule || !newRuleName.trim() || !newRuleSeparator.trim()
              }
            >
              添加规则
            </Button>
          </div>
          {separatorRulesError && (
            <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {separatorRulesError}
            </div>
          )}
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

      <Modal
        open={deleteOpen}
        onClose={() => {
          if (!deletingDatabase) setDeleteOpen(false);
        }}
        title="删除当前数据库"
        description={`将删除「${database?.name ?? ""}」及其数据库文件。`}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setDeleteOpen(false)}
              disabled={deletingDatabase}
            >
              取消
            </Button>
            <Button
              variant="danger"
              onClick={() => void handleDeleteDatabase()}
              disabled={deletingDatabase || !deleteToken.trim()}
            >
              确认删除
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            删除操作不可撤销。确认删除前请输入管理令牌。
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">管理令牌</label>
            <Input
              type="password"
              value={deleteToken}
              onChange={(event) => setDeleteToken(event.target.value)}
              placeholder="UPDATE_ADMIN_TOKEN"
              autoComplete="off"
            />
          </div>
        </div>
      </Modal>
      <Modal
        open={cloneOpen}
        onClose={() => {
          if (!cloningDatabase) setCloneOpen(false);
        }}
        title="克隆当前数据库"
        description={`复制「${database?.name ?? ""}」并自动切换到新数据库。`}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setCloneOpen(false)}
              disabled={cloningDatabase}
            >
              取消
            </Button>
            <Button
              onClick={() => void handleCloneDatabase()}
              disabled={cloningDatabase || !cloneName.trim()}
            >
              克隆
            </Button>
          </>
        }
      >
        <div className="space-y-2">
          <label className="text-sm font-medium">新数据库名称</label>
          <Input
            value={cloneName}
            onChange={(event) => setCloneName(event.target.value)}
            placeholder="例如：当前数据库副本"
            autoFocus
          />
        </div>
      </Modal>
    </div>
  );
}
