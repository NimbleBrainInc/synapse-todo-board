import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { AppProvider, useTheme } from "@nimblebrain/synapse/react";
import "@nimblebrain/synapse/ui/base";
import App from "./App";
import Settings from "./Settings";
import { version } from "../package.json";

const settingsView = document.querySelector('meta[name="todo-board-view"]')?.getAttribute("content") === "settings";

function Surface() {
  const theme = useTheme();
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme.mode);
  }, [theme.mode]);
  return settingsView ? <Settings /> : <App />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProvider name="todo-board" version={version}>
      <Surface />
    </AppProvider>
  </StrictMode>,
);
