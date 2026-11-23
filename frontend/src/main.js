// Entry point: remember a ?token= link, then mount the app.
import { App } from "./App.js";
import { ReactDOM, html } from "./lib/react.js";
import { captureTokenFromUrl } from "./lib/storage.js";

captureTokenFromUrl();
ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
