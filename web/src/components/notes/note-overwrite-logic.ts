/** Pure helpers for single-row note overwrite UI and commit semantics. */

export function normalizeNote(value?: string | null): string {
  return (value ?? "").trim();
}

/** True when account has a stored note and the draft differs from it. */
export function notesDiffer(
  existingNote?: string | null,
  newNote?: string | null
): boolean {
  const existing = normalizeNote(existingNote);
  const draft = normalizeNote(newNote);
  if (!existing || !draft) return false;
  return existing !== draft;
}

export function shouldShowOverwriteButton(
  existingNote?: string | null,
  newNote?: string | null,
  overwriteNote?: boolean
): boolean {
  return notesDiffer(existingNote, newNote) && !overwriteNote;
}

/** Commit should only send overwrite when user confirmed a real change. */
export function effectiveOverwriteNoteForCommit(
  existingNote?: string | null,
  newNote?: string | null,
  overwriteNote?: boolean
): boolean {
  if (!notesDiffer(existingNote, newNote)) return false;
  return Boolean(overwriteNote);
}

export type TopbarNoteDraftKey = {
  query: string;
  hitUsername: string | null;
};

/** Reset topbar outbound note draft when search context changes. */
export function shouldResetTopbarNoteDraft(
  prev: TopbarNoteDraftKey,
  next: TopbarNoteDraftKey
): boolean {
  if (!normalizeNote(next.query)) return true;
  if (normalizeNote(prev.query) !== normalizeNote(next.query)) return true;
  if (prev.hitUsername !== next.hitUsername) return true;
  return false;
}
