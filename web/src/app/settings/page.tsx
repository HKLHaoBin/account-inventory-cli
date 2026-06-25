"use client";

import { useTheme } from "next-themes";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Copy,
  Database,
  DownloadCloud,
  FolderTree,
  Globe,
  Keyboard,
  Monitor,
  Moon,
  Plus,
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
  fetchDatabaseGroups,
  fetchSeparatorRules,
  fetchUpdateStatus,
  renameDatabase,
  saveDatabaseGroups,
  triggerUpdate,
  updateSeparatorRule,
} from "@/lib/api";
import { emitDatabaseChanged, subscribeDatabaseChanged } from "@/lib/database-events";
import { generateId } from "@/lib/id";
import {
  fetchLocalConfig,
  saveLocalConfig,
  testLocalConfig,
} from "@/lib/local-config";
import {
  emitSeparatorRulesChanged,
  subscribeSeparatorRulesChanged,
} from "@/lib/separator-rules-events";
import type {
  DatabaseGroup,
  DatabaseInfo,
  SeparatorRule,
  UpdateStatusPayload,
} from "@/types/account";

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
  const [databaseGroups, setDatabaseGroups] = useState<DatabaseGroup[]>([]);
  const [groupDatabases, setGroupDatabases] = useState<DatabaseInfo[]>([]);
  const [groupsError, setGroupsError] = useState("");
  const [groupsDirty, setGroupsDirty] = useState(false);
  const [savingGroups, setSavingGroups] = useState(false);
  const [separatorRules, setSeparatorRules] = useState<SeparatorRule[]>([]);
  const [separatorRulesError, setSeparatorRulesError] = useState("");
  const [newRuleName, setNewRuleName] = useState("");
  const [newRuleSeparator, setNewRuleSeparator] = useState("");
  const [addingRule, setAddingRule] = useState(false);
  const [updatingRuleId, setUpdatingRuleId] = useState<string | null>(null);
  const [deletingRuleId, setDeletingRuleId] = useState<string | null>(null);
  const [isCloudMode, setIsCloudMode] = useState<boolean | null>(null);
  const [cloudApiBaseUrl, setCloudApiBaseUrl] = useState("");
  const [cloudConfigured, setCloudConfigured] = useState(false);
  const [cloudRemoteAccessToken, setCloudRemoteAccessToken] = useState("");
  const [cloudRemoteAccessTokenConfigured, setCloudRemoteAccessTokenConfigured] =
    useState(false);
  const [cloudRemoteAccessTokenDirty, setCloudRemoteAccessTokenDirty] =
    useState(false);
  const [cloudConfigError, setCloudConfigError] = useState("");
  const [cloudConfigMessage, setCloudConfigMessage] = useState("");
  const [savingCloudConfig, setSavingCloudConfig] = useState(false);
  const [testingCloudConfig, setTestingCloudConfig] = useState(false);

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

  const refreshDatabaseGroups = useCallback(async () => {
    try {
      const payload = await fetchDatabaseGroups();
      setDatabaseGroups(payload.groups);
      setGroupDatabases(payload.databases);
      setGroupsError("");
      setGroupsDirty(false);
    } catch (error) {
      setGroupsError(
        error instanceof Error ? error.message : "数据库组配置读取失败"
      );
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

  const refreshLocalConfig = useCallback(async () => {
    try {
      const payload = await fetchLocalConfig();
      if (!payload) {
        setIsCloudMode(false);
        return;
      }
      setIsCloudMode(true);
      setCloudApiBaseUrl(payload.cloudApiBaseUrl ?? "");
      setCloudConfigured(payload.configured);
      setCloudRemoteAccessTokenConfigured(payload.remoteAccessTokenConfigured);
      setCloudRemoteAccessToken("");
      setCloudRemoteAccessTokenDirty(false);
      setCloudConfigError("");
    } catch (error) {
      setIsCloudMode(false);
      setCloudConfigError(
        error instanceof Error ? error.message : "本地配置读取失败"
      );
    }
  }, []);

  useEffect(() => {
    const mountTimer = window.setTimeout(() => setMounted(true), 0);
    const statusTimer = window.setTimeout(() => {
      void refreshLocalConfig();
      void refreshUpdateStatus();
      void refreshDatabase();
      void refreshDatabaseGroups();
      void refreshSeparatorRules();
    }, 0);
    return () => {
      window.clearTimeout(mountTimer);
      window.clearTimeout(statusTimer);
    };
  }, [refreshDatabase, refreshDatabaseGroups, refreshLocalConfig, refreshSeparatorRules, refreshUpdateStatus]);

  useEffect(
    () =>
      subscribeDatabaseChanged(() => {
        void refreshDatabase();
        void refreshDatabaseGroups();
        void refreshSeparatorRules();
      }),
    [refreshDatabase, refreshDatabaseGroups, refreshSeparatorRules]
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

  const assignedDatabaseIds = useMemo(() => {
    const ids = new Set<string>();
    for (const group of databaseGroups) {
      for (const databaseId of group.databaseIds) {
        ids.add(databaseId);
      }
    }
    return ids;
  }, [databaseGroups]);

  const unassignedDatabases = useMemo(
    () => groupDatabases.filter((item) => !assignedDatabaseIds.has(item.id)),
    [assignedDatabaseIds, groupDatabases]
  );

  function createDatabaseGroup() {
    const nextIndex = databaseGroups.length + 1;
    setDatabaseGroups((current) => [
      ...current,
      {
        id: generateId(),
        name: `组 ${nextIndex}`,
        databaseIds: [],
      },
    ]);
    setGroupsDirty(true);
    setGroupsError("");
  }

  function renameDatabaseGroup(groupId: string, name: string) {
    setDatabaseGroups((current) =>
      current.map((group) =>
        group.id === groupId ? { ...group, name: name.trim() || group.name } : group
      )
    );
    setGroupsDirty(true);
  }

  async function deleteDatabaseGroup(groupId: string) {
    const nextGroups = databaseGroups.filter((group) => group.id !== groupId);
    setDatabaseGroups(nextGroups);
    setSavingGroups(true);
    setGroupsError("");
    try {
      const payload = await saveDatabaseGroups(nextGroups);
      setDatabaseGroups(payload.groups);
      setGroupDatabases(payload.databases);
      setGroupsDirty(false);
      emitDatabaseChanged();
    } catch (error) {
      await refreshDatabaseGroups();
      setGroupsError(error instanceof Error ? error.message : "数据库组删除失败");
    } finally {
      setSavingGroups(false);
    }
  }

  function assignDatabaseToGroup(databaseId: string, groupId: string | null) {
    setDatabaseGroups((current) =>
      current.map((group) => {
        const without = group.databaseIds.filter((id) => id !== databaseId);
        if (groupId && group.id === groupId) {
          return { ...group, databaseIds: [...without, databaseId] };
        }
        return { ...group, databaseIds: without };
      })
    );
    setGroupsDirty(true);
  }

  function groupForDatabase(databaseId: string): string {
    return (
      databaseGroups.find((group) => group.databaseIds.includes(databaseId))?.id ??
      ""
    );
  }

  async function handleSaveDatabaseGroups() {
    setSavingGroups(true);
    try {
      const payload = await saveDatabaseGroups(databaseGroups);
      setDatabaseGroups(payload.groups);
      setGroupDatabases(payload.databases);
      setGroupsError("");
      setGroupsDirty(false);
      emitDatabaseChanged();
    } catch (error) {
      setGroupsError(error instanceof Error ? error.message : "数据库组保存失败");
    } finally {
      setSavingGroups(false);
    }
  }

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

  async function handleSaveCloudConfig() {
    const url = cloudApiBaseUrl.trim();
    if (!url) {
      setCloudConfigError("数据库服务地址不能为空");
      setCloudConfigMessage("");
      return;
    }
    setSavingCloudConfig(true);
    try {
      const payload = await saveLocalConfig(
        url,
        cloudRemoteAccessTokenDirty
          ? { remoteAccessToken: cloudRemoteAccessToken.trim() }
          : undefined
      );
      setCloudApiBaseUrl(payload.cloudApiBaseUrl ?? "");
      setCloudConfigured(payload.configured);
      setCloudRemoteAccessTokenConfigured(payload.remoteAccessTokenConfigured);
      setCloudRemoteAccessToken("");
      setCloudRemoteAccessTokenDirty(false);
      setCloudConfigError("");
      setCloudConfigMessage("服务地址已保存");
    } catch (error) {
      setCloudConfigMessage("");
      setCloudConfigError(
        error instanceof Error ? error.message : "保存服务地址失败"
      );
    } finally {
      setSavingCloudConfig(false);
    }
  }

  async function handleClearCloudRemoteAccessToken() {
    const url = cloudApiBaseUrl.trim();
    if (!url) {
      setCloudConfigError("请先填写并保存数据库服务地址");
      setCloudConfigMessage("");
      return;
    }
    setSavingCloudConfig(true);
    try {
      const payload = await saveLocalConfig(url, { remoteAccessToken: "" });
      setCloudRemoteAccessToken("");
      setCloudRemoteAccessTokenDirty(false);
      setCloudRemoteAccessTokenConfigured(payload.remoteAccessTokenConfigured);
      setCloudConfigError("");
      setCloudConfigMessage("远端访问令牌已清空");
    } catch (error) {
      setCloudConfigMessage("");
      setCloudConfigError(
        error instanceof Error ? error.message : "清空远端访问令牌失败"
      );
    } finally {
      setSavingCloudConfig(false);
    }
  }

  async function handleTestCloudConfig() {
    setTestingCloudConfig(true);
    setCloudConfigMessage("");
    try {
      let savedPayload: Awaited<ReturnType<typeof saveLocalConfig>> | null = null;
      if (cloudApiBaseUrl.trim()) {
        savedPayload = await saveLocalConfig(
          cloudApiBaseUrl.trim(),
          cloudRemoteAccessTokenDirty
            ? { remoteAccessToken: cloudRemoteAccessToken.trim() }
            : undefined
        );
      }
      await testLocalConfig();
      if (savedPayload) {
        setCloudApiBaseUrl(savedPayload.cloudApiBaseUrl ?? "");
        setCloudConfigured(savedPayload.configured);
        setCloudRemoteAccessTokenConfigured(savedPayload.remoteAccessTokenConfigured);
        setCloudRemoteAccessToken("");
        setCloudRemoteAccessTokenDirty(false);
      } else {
        setCloudConfigured(true);
      }
      setCloudConfigError("");
      setCloudConfigMessage("连接测试成功");
    } catch (error) {
      setCloudConfigMessage("");
      setCloudConfigError(
        error instanceof Error ? error.message : "连接测试失败"
      );
    } finally {
      setTestingCloudConfig(false);
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

      {isCloudMode !== true && (
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
      )}

      {isCloudMode && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Globe className="h-4 w-4" />
              数据库服务地址
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 rounded-xl border border-border bg-muted/30 p-4 text-sm sm:grid-cols-2">
              <div>
                <p className="text-xs text-muted-foreground">当前状态</p>
                <p
                  className={`mt-1 flex items-center gap-1.5 ${
                    cloudConfigured ? "text-emerald-600" : "text-amber-600"
                  }`}
                >
                  {cloudConfigured ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    <AlertCircle className="h-4 w-4" />
                  )}
                  {cloudConfigured ? "已配置" : "未配置"}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">远端访问令牌</p>
                <p
                  className={`mt-1 flex items-center gap-1.5 ${
                    cloudRemoteAccessTokenConfigured
                      ? "text-emerald-600"
                      : "text-amber-600"
                  }`}
                >
                  {cloudRemoteAccessTokenConfigured ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    <AlertCircle className="h-4 w-4" />
                  )}
                  {cloudRemoteAccessTokenConfigured ? "已配置" : "未配置"}
                </p>
              </div>
              <div className="sm:col-span-2">
                <p className="text-xs text-muted-foreground">说明</p>
                <p className="mt-1 text-foreground">
                  填写云端后端 API 根地址；若远端启用了远程访问门禁，请配置对应令牌。业务请求仍走 `/api/...`。
                </p>
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">服务地址</label>
              <Input
                value={cloudApiBaseUrl}
                onChange={(event) => setCloudApiBaseUrl(event.target.value)}
                placeholder="https://example.com"
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">远端访问令牌</label>
              <Input
                value={cloudRemoteAccessToken}
                onChange={(event) => {
                  setCloudRemoteAccessToken(event.target.value);
                  setCloudRemoteAccessTokenDirty(true);
                }}
                placeholder={
                  cloudRemoteAccessTokenConfigured
                    ? "已配置，输入新值可覆盖"
                    : "远端 REMOTE_ACCESS_TOKEN"
                }
                type="password"
                autoComplete="off"
              />
            </div>
            {cloudConfigError && (
              <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                {cloudConfigError}
              </div>
            )}
            {cloudConfigMessage && (
              <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 px-4 py-3 text-sm text-emerald-700">
                {cloudConfigMessage}
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                onClick={() => void handleSaveCloudConfig()}
                disabled={savingCloudConfig || testingCloudConfig}
              >
                保存地址
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void handleTestCloudConfig()}
                disabled={savingCloudConfig || testingCloudConfig}
              >
                <RefreshCw
                  className={
                    testingCloudConfig ? "h-4 w-4 animate-spin" : "h-4 w-4"
                  }
                />
                测试连接
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void handleClearCloudRemoteAccessToken()}
                disabled={
                  savingCloudConfig ||
                  testingCloudConfig ||
                  !cloudRemoteAccessTokenConfigured
                }
              >
                清空令牌
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

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
            <FolderTree className="h-4 w-4" />
            数据库组
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            同组内的数据库在入库时会互相比对库存与出库记录；未分配的数据库仅与自身比对。
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={() => void refreshDatabaseGroups()}>
              <RefreshCw className="h-4 w-4" />
              刷新
            </Button>
            <Button variant="secondary" size="sm" onClick={createDatabaseGroup}>
              <Plus className="h-4 w-4" />
              新建组
            </Button>
            <Button
              size="sm"
              onClick={() => void handleSaveDatabaseGroups()}
              disabled={!groupsDirty || savingGroups}
            >
              {savingGroups ? "保存中…" : "保存组配置"}
            </Button>
          </div>

          {databaseGroups.length === 0 ? (
            <p className="rounded-xl border border-dashed border-border px-4 py-3 text-sm text-muted-foreground">
              尚未创建数据库组。所有数据库均为独立组（仅自身比对）。
            </p>
          ) : (
            <div className="space-y-3">
              {databaseGroups.map((group) => (
                <div
                  key={group.id}
                  className="rounded-xl border border-border bg-muted/20 p-4 space-y-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Input
                      value={group.name}
                      onChange={(event) =>
                        renameDatabaseGroup(group.id, event.target.value)
                      }
                      className="max-w-xs"
                      placeholder="组名称"
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      disabled={savingGroups}
                      onClick={() => void deleteDatabaseGroup(group.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                      {savingGroups ? "删除中…" : "删除组"}
                    </Button>
                  </div>
                  <div className="space-y-2">
                    {group.databaseIds.length === 0 ? (
                      <p className="text-xs text-muted-foreground">暂无数据库，请从下方独立组分配。</p>
                    ) : (
                      group.databaseIds.map((databaseId) => {
                        const info = groupDatabases.find((item) => item.id === databaseId);
                        return (
                          <div
                            key={databaseId}
                            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm"
                          >
                            <span className="font-medium">{info?.name ?? databaseId}</span>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => assignDatabaseToGroup(databaseId, null)}
                            >
                              移出组
                            </Button>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="space-y-2 border-t border-border pt-4">
            <p className="text-sm font-medium">独立组（仅自身比对）</p>
            {groupDatabases.length === 0 ? (
              <p className="text-sm text-muted-foreground">加载数据库列表中…</p>
            ) : unassignedDatabases.length === 0 ? (
              <p className="text-sm text-muted-foreground">所有数据库均已分配到组。</p>
            ) : (
              <div className="space-y-2">
                {unassignedDatabases.map((item) => (
                  <div
                    key={item.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border px-3 py-2 text-sm"
                  >
                    <div>
                      <p className="font-medium">{item.name}</p>
                      <p className="text-xs text-muted-foreground">
                        库存 {item.inventoryCount}
                      </p>
                    </div>
                    {databaseGroups.length > 0 && (
                      <select
                        className="h-9 rounded-lg border border-border bg-background px-3 text-sm"
                        value={groupForDatabase(item.id)}
                        onChange={(event) => {
                          const groupId = event.target.value;
                          if (groupId) assignDatabaseToGroup(item.id, groupId);
                        }}
                      >
                        <option value="">分配到组…</option>
                        {databaseGroups.map((group) => (
                          <option key={group.id} value={group.id}>
                            {group.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {groupsError && (
            <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {groupsError}
            </div>
          )}
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
