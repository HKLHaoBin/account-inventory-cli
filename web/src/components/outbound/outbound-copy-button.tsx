"use client";

import { Check, Copy } from "lucide-react";
import { Button, type ButtonProps } from "@/components/ui/button";

interface OutboundCopyButtonProps extends Omit<ButtonProps, "onClick"> {
  clipboardText: string;
  copying: boolean;
  copied: boolean;
  onCopy: () => void | Promise<void>;
  label?: string;
}

export function OutboundCopyButton({
  clipboardText,
  copying,
  copied,
  onCopy,
  disabled,
  variant = "secondary",
  size,
  className,
  label = "重新复制出库内容",
  ...props
}: OutboundCopyButtonProps) {
  return (
    <Button
      variant={variant}
      size={size}
      className={className}
      onClick={() => void onCopy()}
      disabled={disabled || !clipboardText || copying}
      {...props}
    >
      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      {copied ? "已复制" : label}
    </Button>
  );
}
