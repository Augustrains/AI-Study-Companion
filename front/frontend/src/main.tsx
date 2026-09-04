import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import "./theme-skyglass.css";
import "./workspace-layout.css";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
