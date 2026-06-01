"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "./sidebar";
import { TopBar } from "./topbar";
import { StatusBar } from "./status-bar";
import { QuickOutboundModal } from "@/components/outbound/quick-outbound-modal";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [quickOpen, setQuickOpen] = useState(false);

  return (
    <div className="flex h-screen max-w-[1440px] mx-auto overflow-hidden bg-background shadow-[0_0_60px_rgba(15,23,42,0.08)]">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onQuickOutbound={() => setQuickOpen(true)} />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
        <StatusBar />
      </div>
      <QuickOutboundModal
        open={quickOpen}
        onClose={() => setQuickOpen(false)}
        onNavigate={() => {
          setQuickOpen(false);
          router.push("/outbound");
        }}
      />
    </div>
  );
}
