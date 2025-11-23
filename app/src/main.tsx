import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

// Initialize theme on page load
try {
  const savedTheme = localStorage.getItem("theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);
} catch {
  document.documentElement.setAttribute("data-theme", "dark");
}

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Failed to find the root element. Make sure index.html contains a div with id='root'.");
}
createRoot(rootElement).render(<App />);
