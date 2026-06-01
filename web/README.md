# 账号出入库管理 — Web 前端

本地 Web 前端演示 UI，对应 Python CLI 的图形化界面。使用 **Next.js App Router + TypeScript + Tailwind CSS**，数据为静态 Mock，无 API 路由。

## 运行

```bash
cd web
npm install
npm run dev
```

浏览器打开 [http://localhost:3000](http://localhost:3000)。

## 构建

```bash
npm run build
npm start
```

## 页面

| 路由 | 说明 |
|------|------|
| `/` | 仪表盘 — 统计、快捷操作、FIFO 预览、最近活动 |
| `/inventory` | 库存列表 — 排序、批量选择、密码掩码 |
| `/inbound` | 入库 — 60/40 分栏、分类预览、待确认 Modal |
| `/outbound` | FIFO 出库 — 数量步进、快捷 chip、预览列表 |
| `/outbound-paste` | 出库粘贴 — 分类着色预览 |
| `/search` | 搜索结果 — Tab 筛选、唯一命中出库 |
| `/history` | 出库历史 — 按日期分组 |
| `/settings` | 设置 — DB 路径、快捷键、主题、版本 |

## 技术栈

- Next.js 16 (App Router)
- React 19
- Tailwind CSS 4
- next-themes（浅色/深色）
- lucide-react 图标
- Inter + Noto Sans SC 字体

## 说明

- 未修改 Python CLI 源码
- 分类逻辑在 `src/lib/classification.ts` 中简化复刻 `batch.py` 概念
- 版本号来自仓库根目录 `VERSION` 文件（当前 `0.1.6`）
