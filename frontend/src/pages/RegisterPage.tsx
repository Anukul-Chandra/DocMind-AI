import { zodResolver } from "@hookform/resolvers/zod";
import { FileSearch } from "lucide-react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { z } from "zod";

import { ApiError } from "@/api/client";
import Galaxy from "@/components/Galaxy";
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

const registerSchema = z
  .object({
    email: z.string().min(1, "Email is required").email("Enter a valid email"),
    password: z
      .string()
      .min(1, "Password is required")
      .min(8, "Password must be at least 8 characters"),
    confirmPassword: z.string().min(1, "Please confirm your password"),
  })
  .refine((values) => values.password === values.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type RegisterValues = z.infer<typeof registerSchema>;

export function RegisterPage() {
  const { register: registerAccount, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: "", password: "", confirmPassword: "" },
  });

  if (isAuthenticated) {
    return <Navigate to="/app" replace />;
  }

  async function onSubmit(values: RegisterValues) {
    try {
      await registerAccount(values.email, values.password);
      navigate("/login", { replace: true, state: { registered: true } });
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
      {/* Full-viewport pure-black base with the animated galaxy stars on top */}
      <div className="fixed inset-0 z-0 overflow-hidden bg-[#000000]" aria-hidden="true">
        <Galaxy
          mouseRepulsion
          mouseInteraction
          density={1.5}
          glowIntensity={0.5}
          saturation={0.8}
          hueShift={140}
        />
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
        <Card variant="glass" className="docmind-auth-card">
        <CardHeader className="text-center pb-4">
          <CardTitle className="text-2xl font-semibold text-foreground">Create an account</CardTitle>
          <CardDescription className="text-base text-muted-foreground">
            Start uploading documents and asking questions
          </CardDescription>
        </CardHeader>
        <CardContent>
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
                autoComplete="new-password"
                placeholder="At least 8 characters"
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
            <div className="space-y-2">
              <Label htmlFor="confirmPassword" className="text-sm font-medium text-foreground">
                Confirm password
              </Label>
              <PasswordInput
                id="confirmPassword"
                autoComplete="new-password"
                aria-invalid={Boolean(errors.confirmPassword)}
                className="focus-visible:border-brand focus-visible:ring-brand/20"
                {...register("confirmPassword")}
              />
              {errors.confirmPassword && (
                <p className="text-sm text-destructive flex items-center gap-1">
                  <span className="size-3.5 rounded-full bg-destructive/10 flex items-center justify-center">
                    <span className="size-1.5 rounded-full bg-destructive" aria-hidden="true" />
                  </span>
                  {errors.confirmPassword.message}
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
              className="h-11 w-full text-base shadow-brand hover:shadow-brand/45 disabled:opacity-50"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Creating account…" : "Create account"}
            </Button>
          </form>
        </CardContent>
        <CardFooter className="justify-center border-t border-border/40 py-4">
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>Already have an account?</span>
            <Link
              to="/login"
              className="rounded-sm font-medium text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand hover:underline"
            >
              Sign in
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