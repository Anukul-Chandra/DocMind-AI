import { Navigate, createBrowserRouter } from "react-router-dom";

import { ProtectedShell } from "@/layouts/ProtectedShell";
import { RootLayout } from "@/layouts/RootLayout";
import { ChatPage } from "@/pages/ChatPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { RequireAuth } from "@/routes/RequireAuth";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <RootLayout />,
    children: [
      { index: true, element: <Navigate to="/app" replace /> },
      { path: "login", element: <LoginPage /> },
      { path: "register", element: <RegisterPage /> },
      {
        path: "app",
        element: (
          <RequireAuth>
            <ProtectedShell />
          </RequireAuth>
        ),
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "documents", element: <DocumentsPage /> },
          { path: "chat", element: <ChatPage /> },
        ],
      },
    ],
  },
]);