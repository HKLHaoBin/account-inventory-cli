export interface Account {
  id: string;
  username: string;
  password: string;
  email?: string;
  emailPassword?: string;
  url?: string;
  inboundAt: string;
}

export interface OutboundRecord {
  id: string;
  username: string;
  password: string;
  email?: string;
  emailPassword?: string;
  url?: string;
  inboundAt: string | null;
  inboundRecordId?: string | null;
  outboundAt: string;
}

export interface InboundRecord {
  id: string;
  username: string;
  password: string;
  email?: string;
  emailPassword?: string;
  url?: string;
  inboundAt: string;
}

export type HistoryType = "inbound" | "outbound";

export interface DateRangeFilter {
  label: string;
  value: string;
}

export interface HistoryRecord {
  id: string;
  type: HistoryType;
  username: string;
  password: string;
  email?: string;
  emailPassword?: string;
  url?: string;
  inboundAt: string | null;
  outboundAt?: string;
  timestamp: string;
}

export interface ParsedAccount {
  username: string;
  password: string;
  email?: string;
  emailPassword?: string;
  url?: string;
  line: string;
}

export type InboundCategory =
  | "ready"
  | "duplicate"
  | "pending"
  | "invalid"
  | "batchDuplicate";

export interface ClassifiedInboundLine {
  line: string;
  category: InboundCategory;
  reason?: string;
  account?: ParsedAccount;
  lastOutboundAt?: string;
}

export type OutboundCategory =
  | "inInventory"
  | "notInInventory"
  | "inHistory"
  | "invalid"
  | "batchDuplicate";

export type OutboundPasteCategory = OutboundCategory | "ready";

export interface ClassifiedOutboundLine {
  line: string;
  category: OutboundCategory;
  reason?: string;
  account?: ParsedAccount;
}

export interface OutboundPasteRow {
  clientId: string;
  line: string;
  username?: string | null;
  password?: string | null;
  email?: string | null;
  emailPassword?: string | null;
  url?: string | null;
  category: OutboundPasteCategory;
  status?: "success" | "error";
  message?: string | null;
  reason?: string | null;
}

export interface ActivityItem {
  id: string;
  type: "inbound" | "outbound";
  username: string;
  timestamp: string;
}

export type SearchResult =
  | {
      id: string;
      source: "inventory";
      account: Account;
      matchedField: string;
    }
  | {
      id: string;
      source: "history";
      account: OutboundRecord;
      matchedField: string;
    };

export interface SearchPayload {
  results: SearchResult[];
}

export interface OutboundHistoryPayload {
  records: OutboundRecord[];
}

export interface InboundHistoryPayload {
  records: InboundRecord[];
}

export interface HistoryPayload {
  records: HistoryRecord[];
}

export interface InventoryPayload {
  records: Account[];
}

export interface DashboardPayload {
  stats: {
    inventoryCount: number;
    todayInbound: number;
    todayOutbound: number;
    pendingCount: number;
  };
  database: DatabaseInfo;
  fifoPreview: Account[];
  recentActivities: ActivityItem[];
}

export interface DatabaseInfo {
  id: string;
  name: string;
  fileName: string;
  path: string;
  createdAt: string;
  active: boolean;
  inventoryCount: number;
  todayInbound: number;
  todayOutbound: number;
}

export interface DatabaseListPayload {
  databases: DatabaseInfo[];
  activeDatabaseId: string;
}

export interface CreateDatabaseRequest {
  name: string;
}

export interface CloneDatabaseRequest {
  name: string;
}

export interface RenameDatabaseRequest {
  name: string;
}

export interface InboundPreviewRow {
  clientId: string;
  line: string;
  username?: string | null;
  password?: string | null;
  email?: string | null;
  emailPassword?: string | null;
  url?: string | null;
  category: InboundCategory;
  reason?: string | null;
  lastOutboundAt?: string | null;
  selected?: boolean;
  deleted?: boolean;
}

export type InboundCommitStatus =
  | "success"
  | "error"
  | "warning"
  | "skipped";

export interface InboundCommitResultRow extends InboundPreviewRow {
  status: InboundCommitStatus;
  message: string;
}

export interface InboundCommitPayload {
  rows: InboundCommitResultRow[];
  successCount: number;
  errorCount: number;
  warningCount: number;
}

export interface FifoPreviewPayload {
  max: number;
  quantity: number;
  rows: Account[];
}

export interface FifoCommitPayload extends FifoPreviewPayload {
  clipboardText: string;
}

export interface OutboundByUsernamePayload {
  account: Account;
  clipboardText: string;
}

export interface OutboundPasteCommitPayload {
  rows: OutboundPasteRow[];
  successCount: number;
  errorCount: number;
  clipboardText: string;
}

export interface ClipboardMessage {
  source: "clipboard";
  text: string;
  validLines: string[];
  rejectedCount: number;
}

export interface UpdateStatusPayload {
  timestamp: string;
  state: string;
  message: string;
  phase: string;
  repo?: string;
  local_version?: string;
  latest_tag?: string;
  release_title?: string;
  release_published_at?: string;
  update_available?: boolean;
  assets_ready?: boolean;
  github_rate_limit_reset?: number;
  github_rate_limit_reset_at?: string;
  sidecar_pid?: number;
  last_result_state?: string;
  last_result_message?: string;
  rollback_reason?: string;
  updated_targets?: string[];
  updated_count?: number;
  skipped_count?: number;
}
