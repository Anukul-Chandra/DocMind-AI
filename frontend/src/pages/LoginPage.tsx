import { zodResolver } from "@hookform/resolvers/zod";
import { FileSearch } from "lucide-react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { useAuth } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";

const loginSchema = z.object({
  email: z.string().min(1, "Email is required").email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});

type LoginValues = z.infer<typeof loginSchema>;

interface LoginLocationState {
  from?: { pathname?: string };
  registered?: boolean;
}

export function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const state = location.state as LoginLocationState | null;
  const from = state?.from?.pathname ?? "/app";
  const justRegistered = Boolean(state?.registered);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  if (isAuthenticated) {
    return <Navigate to="/app" replace />;
  }

  async function onSubmit(values: LoginValues) {
    try {
      await login(values.email, values.password);
      navigate(from, { replace: true });
    } catch (error) {
      setError("root", {
        message:
          error instanceof ApiError
            ? error.message
            : "Something went wrong. Please try again.",
      });
    }
  }

  return (
    <div className="docmind-page relative flex min-h-screen flex-col items-center justify-center gap-8 p-6">
      {/* Local atmosphere accents over the global backdrop */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div className="docmind-grid-fade absolute inset-0 opacity-70" />
        <div className="absolute -top-24 left-1/2 h-80 w-[36rem] -translate-x-1/2 rounded-full bg-brand/6 blur-3xl" />
      </div>

      <div className="absolute right-4 top-4 z-10">
        <ThemeToggle />
      </div>

      {/* Brand */}
      <div className="docmind-rise relative z-10 flex flex-col items-center gap-3">
        <span className="flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-brand to-brand-strong text-brand-foreground shadow-brand ring-1 ring-brand-border/30">
          <FileSearch className="size-6" aria-hidden="true" />
        </span>
        <span className="flex flex-col items-center leading-tight">
          <span className="text-xl font-semibold tracking-tight text-foreground">DocMind AI</span>
          <span className="docmind-label mt-1 text-muted-foreground">Document Intelligence System</span>
        </span>
      </div>

      {/* Auth panel */}
      <div className="docmind-rise relative z-10 w-full max-w-md" style={{ animationDelay: "60ms" }}>
        <span aria-hidden="true" className="absolute -left-px -top-px z-10 size-3.5 rounded-tl-md border-l border-t border-brand/40" />
        <span aria-hidden="true" className="absolute -right-px -top-px z-10 size-3.5 rounded-tr-md border-r border-t border-brand/40" />
        <span aria-hidden="true" className="absolute -bottom-px -left-px z-10 size-3.5 rounded-bl-md border-b border-l border-brand/40" />
        <span aria-hidden="true" className="absolute -bottom-px -right-px z-10 size-3.5 rounded-br-md border-b border-r border-brand/40" />
        <Card variant="glass">
          <CardHeader className="pb-4 text-center">
            <CardTitle className="text-2xl font-semibold text-foreground">Sign in</CardTitle>
            <CardDescription className="text-base text-muted-foreground">
              Access your document intelligence workspace
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {justRegistered && (
              <div className="flex items-center gap-2 rounded-xl border border-brand-border/30 bg-brand/5 px-4 py-3 text-sm font-medium text-brand" role="status">
                <span className="size-2 shrink-0 rounded-full bg-brand" aria-hidden="true" />
                Account created. Sign in to continue.
              </div>
            )}
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
              <div className="space-y-2">
                <Label htmlFor="email" className="text-sm font-medium text-foreground">
                  Email
                </Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  aria-invalid={Boolean(errors.email)}
                  className="h-10 focus-visible:border-brand focus-visible:ring-brand/20"
                  {...register("email")}
                />
                {errors.email && (
                  <p className="flex items-center gap-1 text-sm text-destructive">
                    <span className="flex size-3.5 items-center justify-center rounded-full bg-destructive/10">
                      <span className="size-1.5 rounded-full bg-destructive" aria-hidden="true" />
                    </span>
                    {errors.email.message}
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="password" className="text-sm font-medium text-foreground">
                  Password
                </Label>
                <PasswordInput
                  id="password"
                  autoComplete="current-password"
                  aria-invalid={Boolean(errors.password)}
                  className="focus-visible:border-brand focus-visible:ring-brand/20"
                  {...register("password")}
                />
                {errors.password && (
                  <p className="flex items-center gap-1 text-sm text-destructive">
                    <span className="flex size-3.5 items-center justify-center rounded-full bg-destructive/10">
                      <span className="size-1.5 rounded-full bg-destructive" aria-hidden="true" />
                    </span>
                    {errors.password.message}
                  </p>
                )}
              </div>
              {errors.root && (
                <p className="flex items-center gap-1 text-sm text-destructive">
                  <span className="flex size-3.5 items-center justify-center rounded-full bg-destructive/10">
                    <span className="size-1.5 rounded-full bg-destructive" aria-hidden="true" />
                  </span>
                  {errors.root.message}
                </p>
              )}
              <Button
                type="submit"
                className="h-11 w-full text-base shadow-brand hover:shadow-brand/45 disabled:opacity-50"
                disabled={isSubmitting}
              >
                {isSubmitting ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          </CardContent>
          <CardFooter className="justify-center border-t border-border/40 py-4">
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <span>No account?</span>
              <Link
                to="/register"
                className={cn(
                  "rounded-sm font-medium text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                  "hover:underline",
                )}
              >
                Create one
              </Link>
            </p>
          </CardFooter>
        </Card>
      </div>

      <p
        className="docmind-label docmind-rise relative z-10 text-muted-foreground/45"
        style={{ animationDelay: "120ms" }}
      >
        DocMind AI · Secure Workspace Access
      </p>
    </div>
  );
}
