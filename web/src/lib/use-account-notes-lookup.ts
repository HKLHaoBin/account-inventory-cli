"use client";

import { useEffect, useMemo, useRef } from "react";
import { fetchAccountNotes } from "@/lib/api";

type NoteRow = {
  clientId: string;
  username?: string | null;
  note?: string | null;
  existingAccountNote?: string | null;
};

export function useAccountNotesLookup<T extends NoteRow>(
  rows: T[],
  setRows: (updater: (current: T[]) => T[]) => void,
  enabled = true
) {
  const requestIdRef = useRef(0);
  const usernamesKey = useMemo(
    () =>
      rows
        .map((row) => row.username?.trim())
        .filter((username): username is string => Boolean(username))
        .sort()
        .join("\0"),
    [rows]
  );

  useEffect(() => {
    if (!enabled || !usernamesKey) return;

    const usernames = usernamesKey.split("\0");
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;

    void fetchAccountNotes(usernames).then((notes) => {
      if (requestIdRef.current !== requestId) return;
      setRows((current) =>
        current.map((row) => {
          const username = row.username?.trim();
          if (!username || row.note?.trim()) return row;
          const existing = notes[username];
          if (!existing) return row;
          return {
            ...row,
            note: existing,
            existingAccountNote: existing,
          };
        })
      );
    });
  }, [enabled, setRows, usernamesKey]);
}
