import "@fontsource/fraunces/600.css"
import "@fontsource/outfit/400.css"
import "@fontsource/outfit/500.css"
import "@fontsource/outfit/700.css"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { App } from "./App"
import "./styles.css"

const root = document.getElementById("root")
if (!root) throw new Error("Missing root element.")
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
