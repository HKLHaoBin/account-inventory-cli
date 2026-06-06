"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const tabs = [
  { href: "/history", label: "全部", exact: true },
  { href: "/history/inbound", label: "入库" },
  { href: "/history/outbound", label: "出库" },
  { href: "/history/trends", label: "趋势", trends: true },
] as const;

export function HistoryNav() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-wrap gap-2">
      {tabs.map((tab) => {
        const active =
          "trends" in tab && tab.trends
            ? pathname.startsWith("/history/trends")
            : "exact" in tab && tab.exact
              ? pathname === tab.href
              : pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              "rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted",
              active && "bg-primary text-primary-foreground border-primary"
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
