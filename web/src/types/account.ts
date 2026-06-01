export interface Account {
  id: string;
  username: string;
  password: string;
  email?: string;
  emailPassword?: string;
  url?: string;
  inboundAt: string;
}

export interface OutboundRecord extends Account {
  outboundAt: string;
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

export interface ClassifiedOutboundLine {
  line: string;
  category: OutboundCategory;
  reason?: string;
  account?: ParsedAccount;
}

export interface ActivityItem {
  id: string;
  type: "inbound" | "outbound";
  username: string;
  timestamp: string;
}

export interface SearchResult {
  id: string;
  source: "inventory" | "history";
  account: Account | OutboundRecord;
  matchedField: string;
}
