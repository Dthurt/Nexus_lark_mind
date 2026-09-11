import { useState } from "react";

import SettingsPage from "@/pages/SettingsPage";
import WorkbenchPage from "@/pages/WorkbenchPage";

type Page = "workbench" | "settings";

export default function App() {
  const [page, setPage] = useState<Page>("workbench");
  const [catalogTick, setCatalogTick] = useState(0);

  if (page === "settings") {
    return (
      <div className="h-screen overflow-hidden bg-background text-foreground">
        <SettingsPage
          onBack={() => setPage("workbench")}
          onCatalogChanged={() => setCatalogTick((t) => t + 1)}
        />
      </div>
    );
  }

  return (
    <div className="h-screen overflow-hidden bg-background text-foreground">
      <WorkbenchPage
        catalogTick={catalogTick}
        onOpenSettings={() => setPage("settings")}
      />
    </div>
  );
}
