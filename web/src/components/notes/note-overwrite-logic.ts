/** Pure helpers for single-row note overwrite UI and commit semantics. */

export function applyBatchNoteToRows<T extends { note?: string | null }>(
  rows: T[],
  batchNote: string
): T[] {
  const value = batchNote.trim();
  if (!value) return rows;
  return rows.map((row) =>
    row.note?.trim() ? row : { ...row, note: value, overwriteNote: false }
  );
}

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

/** Merge draft/preview row with a prior commit result for display and submit. */
export function mergeInboundDraftWithResult<
  TDraft extends { note?: string | null; overwriteNote?: boolean },
  TResult extends TDraft & { status: string },
>(draftRow: TDraft, resultRow: TResult | undefined): TDraft | TResult {
  if (!resultRow) return draftRow;
  if (resultRow.status === "success") return resultRow;
  return {
    ...resultRow,
    note: draftRow.note,
    overwriteNote: draftRow.overwriteNote,
  };
}

export function buildInboundVisibleRows<
  TDraft extends {
    clientId: string;
    note?: string | null;
    overwriteNote?: boolean;
  },
  TResult extends TDraft & { status: string },
>(
  draftRows: TDraft[],
  deletedIds: Set<string>,
  resultRows: Map<string, TResult>
): Array<TDraft | TResult> {
  return draftRows
    .filter((row) => !deletedIds.has(row.clientId))
    .map((row) =>
      mergeInboundDraftWithResult(row, resultRows.get(row.clientId))
    );
}

/** Partial submit: merge payload rows into existing result map. */
export function mergeCommitResultRowsIntoMap<TRow extends { clientId: string }>(
  current: Map<string, TRow>,
  payloadRows: TRow[]
): Map<string, TRow> {
  const next = new Map(current);
  for (const row of payloadRows) next.set(row.clientId, row);
  return next;
}

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
