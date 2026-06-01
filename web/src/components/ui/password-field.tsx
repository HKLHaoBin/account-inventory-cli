"use client";

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { cn, maskValue } from "@/lib/utils";

interface PasswordFieldProps {
  value: string;
  className?: string;
}

export function PasswordField({ value, className }: PasswordFieldProps) {
  const [revealed, setRevealed] = useState(false);

  return (
    <span className={cn("inline-flex items-center gap-1.5 font-mono text-xs", className)}>
      <span>{revealed ? value : maskValue(value)}</span>
      <button
        type="button"
        onClick={() => setRevealed(!revealed)}
        className="rounded-md p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        aria-label={revealed ? "隐藏密码" : "显示密码"}
      >
        {revealed ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
      </button>
    </span>
  );
}
