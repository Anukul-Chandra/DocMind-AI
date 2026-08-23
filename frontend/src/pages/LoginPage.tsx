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
    <div className="docmind-page relative flex min-h-screen flex-col items-center justify-center gap-8 p-6 docmind-ambient">
      {/* Ambient background elements */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div className="absolute -top-32 left-1/2 h-96 w-96 -translate-x-1/2 rounded-full bg-brand/10 blur-3xl" />
        <div className="absolute -bottom-40 right-1/4 h-80 w-80 rounded-full bg-brand-soft/30 blur-3xl" />
      </div>

      <div className="absolute right-4 top-4 z-10">
        <ThemeToggle />
      </div>

      {/* Brand */}
      <div className="docmind-rise flex items-center gap-3 relative z-10">
        <span className="flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-brand to-brand-strong text-brand-foreground shadow-brand ring-1 ring-brand-border/30">
          <FileSearch className="size-6" aria-hidden="true" />
        </span>
        <span className="text-xl font-semibold text-foreground">DocMind AI</span>
      </div>

      {/* Login Card */}
      <Card variant="glass" className="docmind-rise w-full max-w-md" style={{ animationDelay: "60ms" }}>
        <CardHeader className="text-center pb-4">
          <CardTitle className="text-2xl font-semibold text-foreground">Sign in</CardTitle>
          <CardDescription className="text-base text-muted-foreground">
            Access your DocMind AI document workspace
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {justRegistered && (
            <div className="flex items-center gap-2 rounded-xl bg-brand/5 border border-brand-border/30 px-4 py-3 text-sm font-medium text-brand">
              <span className="size-2 shrink-0 rounded-full bg-brand animate-pulse" aria-hidden="true" />
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
                <p className="text-sm text-destructive flex items-center gap-1">
                  <span className="size-3.5 rounded-full bg-destructive/10 flex items-center justify-center">
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
                <p className="text-sm text-destructive flex items-center gap-1">
                  <span className="size-3.5 rounded-full bg-destructive/10 flex items-center justify-center">
                    <span className="size-1.5 rounded-full bg-destructive" aria-hidden="true" />
                  </span>
                  {errors.password.message}
                </p>
              )}
            </div>
            {errors.root && (
              <p className="text-sm text-destructive flex items-center gap-1">
                <span className="size-3.5 rounded-full bg-destructive/10 flex items-center justify-center">
                  <span className="size-1.5 rounded-full bg-destructive" aria-hidden="true" />
                </span>
                {errors.root.message}
              </p>
            )}
            <Button
              type="submit"
              className="w-full h-11 text-base shadow-brand hover:shadow-brand/30 disabled:opacity-50"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </CardContent>
        <CardFooter className="justify-center py-4 border-t border-border/50">
          <p className="text-sm text-muted-foreground flex items-center gap-2">
            <span>No account?</span>
            <Link
              to="/register"
              className="font-medium text-brand hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand rounded-sm"
            >
              Create one
            </Link>
          </p>
        </CardFooter>
      </Card>
    </div>
  );
}