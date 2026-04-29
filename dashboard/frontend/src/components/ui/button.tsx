"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap font-medium transition-colors disabled:pointer-events-none disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive) focus-visible:ring-offset-2 focus-visible:ring-offset-(--color-bg-marketing)",
  {
    variants: {
      variant: {
        primary:
          "bg-(--color-brand-indigo) text-white hover:bg-(--color-brand-interactive) shadow-[var(--shadow-elevated)]",
        ghost:
          "bg-(--color-ghost-bg) text-(--color-text-primary) border border-(--color-border-solid) hover:bg-(--color-ghost-bg-hover) hover:border-(--color-border-strong)",
        subtle:
          "text-(--color-text-secondary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)",
        danger:
          "bg-(--color-status-red)/10 text-(--color-status-red) border border-(--color-status-red)/30 hover:bg-(--color-status-red)/20",
        icon:
          "bg-(--color-icon-bg) text-(--color-text-secondary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary) rounded-full",
      },
      size: {
        sm: "h-7 px-2 text-[12px] rounded-[6px]",
        md: "h-8 px-3 text-[13px] rounded-[6px]",
        lg: "h-9 px-4 text-[14px] rounded-[6px]",
        iconSm: "size-7 rounded-full p-0",
        iconMd: "size-8 rounded-full p-0",
      },
    },
    defaultVariants: {
      variant: "ghost",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp ref={ref} className={cn(buttonVariants({ variant, size, className }))} {...props} />
    );
  }
);
Button.displayName = "Button";

export { buttonVariants };
