"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { shouldShowOverwriteButton } from "@/components/notes/note-overwrite-logic";

export type OutboundNoteFieldProps = {
  existingNote?: string | null;
  value: string;
  onChange: (value: string) => void;
  overwriteNote: boolean;
  onOverwriteNoteChange: (overwrite: boolean) => void;
  disabled?: boolean;
  className?: string;
  inputClassName?: string;
};

export function OutboundNoteField({
  existingNote,
  value,
  onChange,
  overwriteNote,
  onOverwriteNoteChange,
  disabled = false,
  className,
  inputClassName = "h-8 max-w-xs text-xs",
}: OutboundNoteFieldProps) {
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);
  const hasExisting = Boolean(existingNote?.trim());
  const trimmed = value.trim();
  const showOverwrite = shouldShowOverwriteButton(
    existingNote,
    value,
    overwriteNote
  );

  function handleOverwriteClick() {
    if (!trimmed) return;
    if (!confirmOverwrite) {
      setConfirmOverwrite(true);
      return;
    }
    onOverwriteNoteChange(true);
    setConfirmOverwrite(false);
  }

  return (
    <div className={className ?? "flex flex-wrap items-center gap-2"}>
      <Input
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
          onOverwriteNoteChange(false);
          setConfirmOverwrite(false);
        }}
        placeholder={hasExisting ? `现有：${existingNote}` : "备注（可选）"}
        disabled={disabled}
        className={inputClassName}
      />
      {showOverwrite && (
        <Button
          type="button"
          variant={confirmOverwrite ? "danger" : "outline"}
          size="sm"
          onClick={handleOverwriteClick}
          disabled={disabled}
        >
          {confirmOverwrite ? "确认覆盖备注" : "覆盖备注"}
        </Button>
      )}
    </div>
  );
}
