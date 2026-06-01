export const APP_VERSION = "0.1.6";
export const DB_PATH = "data/accounts.db";
export const APP_NAME = "账号出入库管理";

export const NAV_ITEMS = [
  { href: "/", label: "仪表盘", icon: "LayoutDashboard" },
  { href: "/inventory", label: "库存", icon: "Package" },
  { href: "/inbound", label: "入库", icon: "Download" },
  { href: "/outbound", label: "FIFO出库", icon: "Upload" },
  { href: "/outbound-paste", label: "出库粘贴", icon: "ClipboardPaste" },
  { href: "/history", label: "出库历史", icon: "History" },
  { href: "/settings", label: "设置", icon: "Settings" },
] as const;

export const SHORTCUTS = [
  { key: "/", description: "聚焦全局搜索" },
  { key: "Esc", description: "清空搜索 / 关闭弹窗" },
  { key: "Ctrl+C", description: "复制选中行标准格式" },
  { key: "O", description: "打开快捷出库" },
] as const;
