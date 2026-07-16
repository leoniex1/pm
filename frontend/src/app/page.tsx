"use client";

import { KanbanBoard } from "@/components/KanbanBoard";

export default function Home() {
  const handleLogout = async () => {
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "include",
    });
    window.location.href = "/login";
  };

  return <KanbanBoard onLogout={handleLogout} />;
}
