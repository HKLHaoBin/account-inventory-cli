"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronDown,
  Copy,
  Database,
  Plus,
  RefreshCw,
  Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import {
  activateDatabase,
  cloneDatabase,
  createDatabase,
  fetchDashboard,
  fetchDatabases,
} from "@/lib/api";
import { emitDatabaseChanged } from "@/lib/database-events";
import type { DatabaseInfo } from "@/types/account";
import { cn } from "@/lib/utils";

export function StatusBar() {
  const [inventoryCount, setInventoryCount] = useState<number | null>(null);
  const [syncText, setSyncText] = useState("同步中");
  const [connected, setConnected] = useState(false);
  const [databases, setDatabases] = useState<DatabaseInfo[]>([]);
  const [activeDatabase, setActiveDatabase] = useState<DatabaseInfo | null>(null);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [databaseSearch, setDatabaseSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [databaseName, setDatabaseName] = useState("");
  const [cloneOpen, setCloneOpen] = useState(false);
  const [cloneSource, setCloneSource] = useState<DatabaseInfo | null>(null);
  const [cloneName, setCloneName] = useState("");
  const [busyDatabaseId, setBusyDatabaseId] = useState("");
  const [createBusy, setCreateBusy] = useState(false);
  const [cloneBusy, setCloneBusy] = useState(false);
  const [error, setError] = useState("");

  const filteredDatabases = useMemo(() => {
    const query = databaseSearch.trim().toLowerCase();
    if (!query) return databases;
    return databases.filter((database) =>
      [database.name, database.fileName, database.path].some((value) =>
        value.toLowerCase().includes(query)
      )
    );
  }, [databaseSearch, databases]);

  async function refresh() {
    const [dashboard, list] = await Promise.all([
      fetchDashboard(),
      fetchDatabases(),
    ]);
    setInventoryCount(dashboard.stats.inventoryCount);
    setActiveDatabase(dashboard.database);
    setDatabases(list.databases);
    setConnected(true);
    setSyncText("刚刚");
    setError("");
  }

  useEffect(() => {
    let cancelled = false;

    async function refreshSafely() {
      try {
        const payload = await Promise.all([fetchDashboard(), fetchDatabases()]);
        if (cancelled) return;
        setInventoryCount(payload[0].stats.inventoryCount);
        setActiveDatabase(payload[0].database);
        setDatabases(payload[1].databases);
        setConnected(true);
        setSyncText("刚刚");
        setError("");
      } catch {
        if (cancelled) return;
        setConnected(false);
        setSyncText("连接失败");
      }
    }

    const timer = window.setTimeout(() => {
      void refreshSafely();
    }, 0);
    const interval = window.setInterval(() => {
      void refreshSafely();
    }, 15000);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      window.clearInterval(interval);
    };
  }, []);

  async function handleActivate(database: DatabaseInfo) {
    if (database.active || busyDatabaseId) return;
    setBusyDatabaseId(database.id);
    try {
      const active = await activateDatabase(database.id);
      setActiveDatabase(active);
      setSelectorOpen(false);
      emitDatabaseChanged(active.id);
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "切换数据库失败");
    } finally {
      setBusyDatabaseId("");
    }
  }

  async function handleCreate() {
    const name = databaseName.trim();
    if (!name) {
      setError("数据库名称不能为空");
      return;
    }
    setCreateBusy(true);
    try {
      const active = await createDatabase(name);
      setDatabaseName("");
      setCreateOpen(false);
      setSelectorOpen(false);
      setActiveDatabase(active);
      emitDatabaseChanged(active.id);
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "创建数据库失败");
    } finally {
      setCreateBusy(false);
    }
  }

  function openCloneDialog(database: DatabaseInfo) {
    setError("");
    setCloneSource(database);
    setCloneName("");
    setCloneOpen(true);
  }

  async function handleClone() {
    if (!cloneSource) return;
    const name = cloneName.trim();
    if (!name) {
      setError("数据库名称不能为空");
      return;
    }
    setCloneBusy(true);
    try {
      const active = await cloneDatabase(cloneSource.id, name);
      setCloneName("");
      setCloneOpen(false);
      setSelectorOpen(false);
      setActiveDatabase(active);
      emitDatabaseChanged(active.id);
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "克隆数据库失败");
    } finally {
      setCloneBusy(false);
    }
  }

  return (
    <footer className="relative flex h-9 shrink-0 items-center justify-between border-t border-border bg-muted/50 px-6 text-xs text-muted-foreground">
      <span>库存 {inventoryCount ?? "-"} 条</span>
      <div className="relative">
        <button
          type="button"
          className="flex h-7 items-center gap-1.5 rounded-md px-2 text-xs transition-colors hover:bg-muted"
          onClick={() => setSelectorOpen((value) => !value)}
        >
          <Database className="h-3.5 w-3.5" />
          <span
            className={
              connected
                ? "inline-block h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(22,163,74,0.6)]"
                : "inline-block h-1.5 w-1.5 rounded-full bg-amber-500"
            }
          />
          <span className="max-w-[180px] truncate">
            {connected
              ? `${activeDatabase?.name ?? "数据库"}已连接`
              : "数据库未连接"}
          </span>
          <ChevronDown
            className={cn(
              "h-3.5 w-3.5 transition-transform",
              selectorOpen && "rotate-180"
            )}
          />
        </button>

        {selectorOpen && (
          <div className="absolute bottom-9 left-1/2 z-40 w-[min(360px,calc(100vw-2rem))] -translate-x-1/2 rounded-lg border border-border bg-card p-3 text-sm text-foreground shadow-xl">
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="text-xs font-medium text-muted-foreground">切换数据库</p>
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground"
                onClick={() => void refresh()}
                aria-label="刷新数据库列表"
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="relative mb-2">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={databaseSearch}
                onChange={(event) => setDatabaseSearch(event.target.value)}
                placeholder="查找数据库名称、文件名或路径"
                className="h-9 pl-8 text-xs"
              />
            </div>
            <div className="max-h-64 space-y-1 overflow-y-auto">
              {filteredDatabases.length > 0 ? (
                filteredDatabases.map((database) => (
                  <div
                    key={database.id}
                    className={cn(
                      "flex items-center gap-1 rounded-md transition-colors hover:bg-muted",
                      database.active && "bg-primary/5 text-primary"
                    )}
                  >
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 items-center justify-between gap-3 px-3 py-2 text-left"
                      disabled={Boolean(busyDatabaseId)}
                      onClick={() => void handleActivate(database)}
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium">
                          {database.name}
                        </span>
                        <span className="block text-xs text-muted-foreground">
                          库存 {database.inventoryCount} 条
                        </span>
                      </span>
                      {database.active ? (
                        <Check className="h-4 w-4 shrink-0" />
                      ) : (
                        <span className="shrink-0 text-xs text-muted-foreground">
                          {busyDatabaseId === database.id ? "切换中" : "切换"}
                        </span>
                      )}
                    </button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="mr-1 h-8 w-8 shrink-0"
                      disabled={cloneBusy}
                      onClick={() => openCloneDialog(database)}
                      aria-label={`克隆 ${database.name}`}
                      title="克隆数据库"
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))
              ) : (
                <p className="rounded-md border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
                  没有匹配的数据库
                </p>
              )}
            </div>
            <div className="mt-3 border-t border-border pt-3">
              <Button
                size="sm"
                className="w-full"
                onClick={() => {
                  setError("");
                  setCreateOpen(true);
                }}
              >
                <Plus className="h-4 w-4" />
                创建数据库
              </Button>
              {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
            </div>
          </div>
        )}
      </div>
      <span>上次同步 {syncText}</span>
      <Modal
        open={createOpen}
        onClose={() => {
          if (!createBusy) setCreateOpen(false);
        }}
        title="创建数据库"
        description="创建后会自动切换到新数据库"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setCreateOpen(false)}
              disabled={createBusy}
            >
              取消
            </Button>
            <Button
              onClick={() => void handleCreate()}
              disabled={createBusy || !databaseName.trim()}
            >
              创建
            </Button>
          </>
        }
      >
        <div className="space-y-2">
          <label className="text-sm font-medium">数据库名称</label>
          <Input
            value={databaseName}
            onChange={(event) => setDatabaseName(event.target.value)}
            placeholder="例如：客户 A 库"
            autoFocus
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
      </Modal>
      <Modal
        open={cloneOpen}
        onClose={() => {
          if (!cloneBusy) setCloneOpen(false);
        }}
        title="克隆数据库"
        description={`复制「${cloneSource?.name ?? ""}」并自动切换到新数据库`}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setCloneOpen(false)}
              disabled={cloneBusy}
            >
              取消
            </Button>
            <Button
              onClick={() => void handleClone()}
              disabled={cloneBusy || !cloneName.trim()}
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
            placeholder="例如：客户 A 库副本"
            autoFocus
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
      </Modal>
    </footer>
  );
}
