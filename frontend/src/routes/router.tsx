import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, createBrowserRouter } from "react-router-dom";

import { ProtectedShell } from "@/layouts/ProtectedShell";
import { RootLayout } from "@/layouts/RootLayout";
import { RequireAuth } from "@/routes/RequireAuth";

const ChatPage = lazy(() =>
  import("@/pages/ChatPage").then((module) => ({ default: module.ChatPage })),
);
const DashboardPage = lazy(() =>
  import("@/pages/DashboardPage").then((module) => ({
    default: module.DashboardPage,
  })),
);
const DocumentsPage = lazy(() =>
  import("@/pages/DocumentsPage").then((module) => ({
    default: module.DocumentsPage,
  })),
);
const LoginPage = lazy(() =>
  import("@/pages/LoginPage").then((module) => ({ default: module.LoginPage })),
);
const RegisterPage = lazy(() =>
  import("@/pages/RegisterPage").then((module) => ({
    default: module.RegisterPage,
  })),
);

function LazyPage({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-1 items-center justify-center p-8" role="status">
          <div className="size-6 animate-spin rounded-full border-2 border-muted border-t-brand" />
        </div>
      }
    >
      {children}
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <RootLayout />,
    children: [
      { index: true, element: <Navigate to="/app" replace /> },
      {
        path: "login",
        element: (
          <LazyPage>
            <LoginPage />
          </LazyPage>
        ),
      },
      {
        path: "register",
        element: (
          <LazyPage>
            <RegisterPage />
          </LazyPage>
        ),
      },
      {
        path: "app",
        element: (
          <RequireAuth>
            <ProtectedShell />
          </RequireAuth>
        ),
        children: [
          {
            index: true,
            element: (
              <LazyPage>
                <DashboardPage />
              </LazyPage>
            ),
          },
          {
            path: "documents",
            element: (
              <LazyPage>
                <DocumentsPage />
              </LazyPage>
            ),
          },
          {
            path: "chat",
            element: (
              <LazyPage>
                <ChatPage />
              </LazyPage>
            ),
          },
        ],
      },
    ],
  },
]);
