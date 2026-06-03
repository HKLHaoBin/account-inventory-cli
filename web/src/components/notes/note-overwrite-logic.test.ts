import { describe, expect, it } from "vitest";
import {
  applyBatchNoteToRows,
  buildInboundVisibleRows,
  effectiveOverwriteNoteForCommit,
  mergeCommitResultRowsIntoMap,
  mergeInboundDraftWithResult,
  notesDiffer,
  shouldResetTopbarNoteDraft,
  shouldShowOverwriteButton,
} from "./note-overwrite-logic";

describe("applyBatchNoteToRows", () => {
  it("returns rows unchanged when batch note is empty", () => {
    const rows = [{ note: "" }, { note: "existing" }];
    expect(applyBatchNoteToRows(rows, "")).toEqual(rows);
    expect(applyBatchNoteToRows(rows, "   ")).toEqual(rows);
  });

  it("fills only rows with empty notes", () => {
    const rows = [
      { note: "" },
      { note: "  " },
      { note: "existing" },
    ];
    expect(applyBatchNoteToRows(rows, " batch ")).toEqual([
      { note: "batch", overwriteNote: false },
      { note: "batch", overwriteNote: false },
      { note: "existing" },
    ]);
  });

  it("skips rows that already have notes", () => {
    const rows = [{ note: "keep" }, { note: null }];
    expect(applyBatchNoteToRows(rows, "new")).toEqual([
      { note: "keep" },
      { note: "new", overwriteNote: false },
    ]);
  });
});

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

describe("mergeCommitResultRowsIntoMap", () => {
  it("partial outbound-paste submit keeps prior result rows", () => {
    type PasteRow = {
      clientId: string;
      line: string;
      category: "inInventory" | "invalid";
      status?: "success" | "error";
      message?: string;
    };
    const prior = new Map<string, PasteRow>([
      [
        "line-1",
        {
          clientId: "line-1",
          line: "a----b",
          category: "inInventory",
          status: "success",
          message: "ok",
        },
      ],
    ]);
    const merged = mergeCommitResultRowsIntoMap(prior, [
      {
        clientId: "line-2",
        line: "c----d",
        category: "invalid",
        status: "error",
        message: "bad",
      },
    ]);
    expect(merged.get("line-1")).toEqual(prior.get("line-1"));
    expect(merged.get("line-2")?.status).toBe("error");
    expect(merged.size).toBe(2);
  });
});

describe("mergeInboundDraftWithResult", () => {
  it("success rows keep server note", () => {
    const merged = mergeInboundDraftWithResult(
      { note: "draft", overwriteNote: true as boolean | undefined },
      {
        clientId: "x",
        line: "l",
        category: "ready" as const,
        status: "success" as const,
        message: "ok",
        note: "server",
        overwriteNote: false,
      }
    );
    expect(merged).toMatchObject({ status: "success", note: "server" });
  });

  it("warning rows take latest draft note for second confirm", () => {
    const merged = mergeInboundDraftWithResult(
      { note: "batch-note", overwriteNote: false },
      {
        clientId: "x",
        line: "l",
        category: "pending" as const,
        status: "warning" as const,
        message: "confirm",
        note: "",
        overwriteNote: false,
      }
    );
    expect(merged).toMatchObject({
      status: "warning",
      message: "confirm",
      note: "batch-note",
    });
  });

  it("warning rows preserve manual note edit on second confirm", () => {
    const merged = mergeInboundDraftWithResult<
      { note: string; overwriteNote?: boolean },
      {
        clientId: string;
        line: string;
        category: "pending";
        status: "warning";
        message: string;
        note: string;
        overwriteNote?: boolean;
      }
    >(
      { note: "manual-edit", overwriteNote: true },
      {
        clientId: "x",
        line: "l",
        category: "pending",
        status: "warning",
        message: "confirm",
        note: "",
        overwriteNote: false,
      }
    );
    expect(merged).toMatchObject({
      note: "manual-edit",
      overwriteNote: true,
    });
  });
});

describe("buildInboundVisibleRows second confirm commit payload", () => {
  it("applies batch note to warning rows in commit payload", () => {
    type Row = {
      clientId: string;
      line: string;
      category: "ready" | "pending";
      note?: string;
      overwriteNote?: boolean;
      status?: string;
      message?: string;
    };
    const drafts = applyBatchNoteToRows<Row>(
      [
        {
          clientId: "line-1",
          line: "u----p",
          category: "ready",
          note: "",
        },
      ],
      "shared-batch"
    );
    const results = new Map<string, Row & { status: string; message: string }>([
      [
        "line-1",
        {
          clientId: "line-1",
          line: "u----p",
          category: "pending",
          status: "warning",
          message: "曾出库",
          note: "",
        },
      ],
    ]);
    const visible = buildInboundVisibleRows(drafts, new Set(), results);
    expect(visible[0]).toMatchObject({ note: "shared-batch", status: "warning" });
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
