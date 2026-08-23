import * as React from "react";

import { cn } from "@/lib/utils";

function Card({ className, variant = "default", ...props }: React.ComponentProps<"div"> & { variant?: "default" | "glass" | "elevated" | "brand" }) {
  const variants = {
    default: "bg-card text-card-foreground flex flex-col gap-6 rounded-2xl border border-border/50 shadow-elevation-1",
    glass: "glass flex flex-col gap-6 rounded-2xl",
    elevated: "bg-card text-card-foreground flex flex-col gap-6 rounded-2xl border border-border/50 shadow-elevation-2",
    brand: "bg-brand-surface/50 text-card-foreground flex flex-col gap-6 rounded-2xl border border-brand-border/30 shadow-brand/10",
  };

  return (
    <div
      data-slot="card"
      className={cn(variants[variant], className)}
      {...props}
    />
  );
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn("grid auto-rows-min items-start gap-1.5 px-6", className)}
      {...props}
    />
  );
}

function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-title"
      className={cn("leading-none font-semibold text-foreground", className)}
      {...props}
    />
  );
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-muted-foreground text-sm", className)}
      {...props}
    />
  );
}

function CardAction({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn(
        "col-start-2 row-span-2 row-start-1 self-start justify-self-end",
        className,
      )}
      {...props}
    />
  );
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div data-slot="card-content" className={cn("px-6", className)} {...props} />
  );
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn("flex items-center px-6 pt-2", className)}
      {...props}
    />
  );
}

export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardAction,
  CardDescription,
  CardContent,
};