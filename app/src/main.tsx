import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

// Initialize theme on page load
try {
  const savedTheme = localStorage.getItem("theme");
  // Normalize: only accept "light" or "dark", default to "dark"
  const theme = (savedTheme === "light" || savedTheme === "dark") ? savedTheme : "dark";
  document.documentElement.setAttribute("data-theme", theme);
  // Update localStorage if we normalized the value
  if (savedTheme !== theme) {
    localStorage.setItem("theme", theme);
  }
} catch {
  document.documentElement.setAttribute("data-theme", "dark");
}

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Failed to find the root element. Make sure index.html contains a div with id='root'.");
}
createRoot(rootElement).render(<App />);
