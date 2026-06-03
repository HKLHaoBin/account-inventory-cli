"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type NoteRow = {
  clientId?: string;
  username?: string | null;
  note?: string | null;
  overwriteNote?: boolean;
};

type BatchNoteControlsProps<T extends NoteRow> = {
  rows: T[];
  onRowsChange: (rows: T[]) => void;
  disabled?: boolean;
  batchNote?: string;
  onBatchNoteChange?: (value: string) => void;
};

export function BatchNoteControls<T extends NoteRow>({
  rows,
  onRowsChange,
  disabled = false,
  batchNote: batchNoteProp,
  onBatchNoteChange,
}: BatchNoteControlsProps<T>) {
  const [internalBatchNote, setInternalBatchNote] = useState("");
  const batchNote = batchNoteProp ?? internalBatchNote;
  const setBatchNote = onBatchNoteChange ?? setInternalBatchNote;
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);

  function fillEmptyNotes() {
    const value = batchNote.trim();
    if (!value) return;
    onRowsChange(
      rows.map((row) =>
        row.note?.trim() ? row : { ...row, note: value, overwriteNote: false }
      )
    );
  }

  function overwriteAllNotes() {
    const value = batchNote.trim();
    if (!value) return;
    if (!confirmOverwrite) {
      setConfirmOverwrite(true);
      return;
    }
    onRowsChange(
      rows.map((row) =>
        row.username?.trim()
          ? { ...row, note: value, overwriteNote: true }
          : row
      )
    );
    setConfirmOverwrite(false);
  }

  return (
    <div className="flex flex-wrap items-end gap-2">
      <Input
        value={batchNote}
        onChange={(event) => {
          setBatchNote(event.target.value);
          setConfirmOverwrite(false);
        }}
        placeholder="批量备注"
        disabled={disabled}
        className="max-w-xs"
      />
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={fillEmptyNotes}
        disabled={disabled || !batchNote.trim()}
      >
        填充空备注
      </Button>
      <Button
        type="button"
        variant={confirmOverwrite ? "danger" : "outline"}
        size="sm"
        onClick={overwriteAllNotes}
        disabled={disabled || !batchNote.trim()}
      >
        {confirmOverwrite ? "确认覆盖全部备注" : "覆盖全部备注"}
      </Button>
    </div>
  );
}
