import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ConfigProvider } from "./config";
import { AuthProvider, ProtectedRoute } from "./auth";

const rootElement = document.getElementById("root");
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <ConfigProvider>
        <AuthProvider><ProtectedRoute><App /></ProtectedRoute></AuthProvider>
      </ConfigProvider>
    </React.StrictMode>
  );
}
