"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "./sidebar";
import { TopBar } from "./topbar";
import { StatusBar } from "./status-bar";
import { QuickOutboundModal } from "@/components/outbound/quick-outbound-modal";
import { subscribeDatabaseChanged } from "@/lib/database-events";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [quickOpen, setQuickOpen] = useState(false);
  const [databaseVersion, setDatabaseVersion] = useState(0);

  useEffect(
    () => subscribeDatabaseChanged(() => setDatabaseVersion((value) => value + 1)),
    []
  );

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onQuickOutbound={() => setQuickOpen(true)} />
        <main
          key={databaseVersion}
          className="flex-1 overflow-y-auto p-3 sm:p-4 lg:p-6"
        >
          {children}
        </main>
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
