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
  { key: "I", description: "聚焦仪表盘批量入库输入框" },
  { key: "F", description: "聚焦仪表盘 FIFO 数量" },
  { key: "↑ / ↓", description: "在待确认入库项之间移动" },
  { key: "Space / Enter", description: "切换当前待确认项批准状态" },
  { key: "Y / N", description: "批准当前项 / 取消选中或当前项" },
  { key: "Ctrl+Enter", description: "在入库输入框内提交当前批次" },
] as const;
