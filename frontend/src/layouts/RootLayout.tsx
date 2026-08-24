import { Outlet } from "react-router-dom";

export function RootLayout() {
  return (
    <div className="relative flex min-h-screen flex-col bg-background text-foreground">
      {/* Command-center atmosphere: aurora glow, technical grid, film grain */}
      <div className="docmind-atmosphere" aria-hidden="true">
        <div className="docmind-noise" />
      </div>
      <div className="relative z-10">
        <Outlet />
      </div>
    </div>
  );
}
