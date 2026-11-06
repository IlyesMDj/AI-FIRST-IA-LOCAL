import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { MOCK, setApi } from "./api";
import App from "./App";

async function boot() {
  if (MOCK) {
    const { mockApi } = await import("./mock");
    setApi(mockApi);
  }
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

boot();
