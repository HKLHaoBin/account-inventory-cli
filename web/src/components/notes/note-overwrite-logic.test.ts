import { describe, expect, it } from "vitest";
import {
  effectiveOverwriteNoteForCommit,
  notesDiffer,
  shouldResetTopbarNoteDraft,
  shouldShowOverwriteButton,
} from "./note-overwrite-logic";

describe("notesDiffer", () => {
  it("is false when no existing note", () => {
    expect(notesDiffer(null, "new")).toBe(false);
  });

  it("is false when draft matches existing", () => {
    expect(notesDiffer("same", "same")).toBe(false);
    expect(notesDiffer(" same ", "same")).toBe(false);
  });

  it("is true when draft differs from existing", () => {
    expect(notesDiffer("old", "new")).toBe(true);
  });
});

describe("shouldShowOverwriteButton", () => {
  it("shows when existing differs and not confirmed", () => {
    expect(shouldShowOverwriteButton("old", "new", false)).toBe(true);
  });

  it("hides when overwrite already confirmed", () => {
    expect(shouldShowOverwriteButton("old", "new", true)).toBe(false);
  });

  it("hides when draft matches existing", () => {
    expect(shouldShowOverwriteButton("old", "old", false)).toBe(false);
  });
});

describe("effectiveOverwriteNoteForCommit", () => {
  it("inbound: edit without confirm does not overwrite", () => {
    expect(effectiveOverwriteNoteForCommit("old", "new", false)).toBe(false);
  });

  it("inbound: confirm overwrite sends flag", () => {
    expect(effectiveOverwriteNoteForCommit("old", "new", true)).toBe(true);
  });

  it("fifo: confirm overwrite is effective on commit", () => {
    expect(effectiveOverwriteNoteForCommit("fifo-old", "fifo-new", true)).toBe(
      true
    );
  });

  it("no overwrite when note unchanged", () => {
    expect(effectiveOverwriteNoteForCommit("same", "same", true)).toBe(false);
  });
});

describe("shouldResetTopbarNoteDraft", () => {
  it("resets when unique hit account changes", () => {
    expect(
      shouldResetTopbarNoteDraft(
        { query: "user", hitUsername: "alice" },
        { query: "user", hitUsername: "bob" }
      )
    ).toBe(true);
  });

  it("keeps draft when same query and same hit", () => {
    expect(
      shouldResetTopbarNoteDraft(
        { query: "user", hitUsername: "alice" },
        { query: "user", hitUsername: "alice" }
      )
    ).toBe(false);
  });

  it("resets when query changes", () => {
    expect(
      shouldResetTopbarNoteDraft(
        { query: "alice", hitUsername: "alice" },
        { query: "bob", hitUsername: "bob" }
      )
    ).toBe(true);
  });

  it("resets when search cleared", () => {
    expect(
      shouldResetTopbarNoteDraft(
        { query: "alice", hitUsername: "alice" },
        { query: "", hitUsername: null }
      )
    ).toBe(true);
  });
});
