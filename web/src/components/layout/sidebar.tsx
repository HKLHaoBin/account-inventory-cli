"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Package,
  Download,
  Upload,
  ClipboardPaste,
  History,
  Settings,
  Boxes,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { NAV_ITEMS } from "@/lib/constants";

const iconMap = {
  LayoutDashboard,
  Package,
  Download,
  Upload,
  ClipboardPaste,
  History,
  Settings,
};

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-[64px] shrink-0 flex-col border-r border-border bg-card/50 backdrop-blur-sm lg:w-[220px]">
      <div className="flex h-16 items-center justify-center gap-2.5 border-b border-border px-3 lg:justify-start lg:px-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-[0_2px_8px_rgba(30,64,175,0.3)]">
          <Boxes className="h-5 w-5" />
        </div>
        <div className="hidden min-w-0 lg:block">
          <p className="truncate text-sm font-semibold">账号出入库</p>
          <p className="text-[11px] text-muted-foreground">Inventory CLI</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 p-2 lg:p-3">
        {NAV_ITEMS.map((item) => {
          const Icon = iconMap[item.icon as keyof typeof iconMap];
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              title={item.label}
              className={cn(
                "flex items-center justify-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200 lg:justify-start",
                active
                  ? "bg-primary text-primary-foreground shadow-[0_2px_8px_rgba(30,64,175,0.25)]"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="hidden lg:inline">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
