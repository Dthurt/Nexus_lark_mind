import { useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router-dom";

import { Toaster } from "@/components/ui/sonner";
import SettingsPage from "@/pages/SettingsPage";
import WorkbenchPage from "@/pages/WorkbenchPage";

function AppRoutes() {
  const navigate = useNavigate();
  const [catalogTick, setCatalogTick] = useState(0);

  return (
    <>
      <Toaster />
      <Routes>
        <Route
          path="/settings"
          element={
            <div className="h-screen overflow-hidden bg-background text-foreground">
              <SettingsPage
                onBack={() => navigate("/")}
                onCatalogChanged={() => setCatalogTick((t) => t + 1)}
              />
            </div>
          }
        />
        <Route
          path="/"
          element={
            <div className="h-screen overflow-hidden bg-background text-foreground">
              <WorkbenchPage
                catalogTick={catalogTick}
                onOpenSettings={() => navigate("/settings")}
              />
            </div>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
