import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[10px] text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary:
          "bg-primary text-primary-foreground shadow-[0_2px_8px_rgba(30,64,175,0.25)] hover:bg-primary/90 hover:shadow-[0_4px_12px_rgba(30,64,175,0.3)]",
        secondary:
          "bg-card text-foreground border border-border shadow-sm hover:bg-muted",
        danger:
          "bg-destructive text-destructive-foreground shadow-[0_2px_8px_rgba(220,38,38,0.2)] hover:bg-destructive/90",
        ghost: "hover:bg-muted text-foreground",
        outline:
          "border border-border bg-transparent hover:bg-muted shadow-sm",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-10 px-4",
        lg: "h-11 px-6 text-base",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({
  className,
  variant,
  size,
  ...props
}: ButtonProps) {
  return (
    <button className={cn(buttonVariants({ variant, size }), className)} {...props} />
  );
}

export { buttonVariants };
