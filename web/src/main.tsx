import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@/components/tools/registerBuiltinTools";
import "@/components/canvas/registerBuiltinCanvasViews";
import { applyTheme, loadStoredTheme } from "@/hooks/useTheme";
import App from "./App";
import "./index.css";

applyTheme(loadStoredTheme());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
