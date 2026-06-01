import type { Account, ActivityItem, OutboundRecord } from "@/types/account";

const baseDate = new Date("2026-05-28T08:00:00");

function daysAgo(days: number, hours = 0): string {
  const d = new Date(baseDate);
  d.setDate(d.getDate() - days);
  d.setHours(d.getHours() + hours);
  return d.toISOString();
}

export const mockInventory: Account[] = [
  {
    id: "1",
    username: "alpha_user01",
    password: "Pass@2026a",
    email: "alpha01@mail.example.com",
    emailPassword: "MailPass01!",
    url: "https://platform.example.com/login",
    inboundAt: daysAgo(12, 2),
  },
  {
    id: "2",
    username: "beta_test02",
    password: "Beta#Secure2",
    email: "beta02@corp.net",
    emailPassword: "CorpMail02",
    inboundAt: daysAgo(11, 5),
  },
  {
    id: "3",
    username: "gamma_shop03",
    password: "Shop3Pwd!",
    url: "https://shop.example.com",
    inboundAt: daysAgo(10, 1),
  },
  {
    id: "4",
    username: "delta_dev04",
    password: "Dev4Code#",
    email: "delta04@dev.io",
    emailPassword: "DevMail04",
    url: "https://dev.example.com",
    inboundAt: daysAgo(9, 3),
  },
  {
    id: "5",
    username: "epsilon_app05",
    password: "App5Key!",
    inboundAt: daysAgo(8, 6),
  },
  {
    id: "6",
    username: "zeta_cloud06",
    password: "Cloud6@Pwd",
    email: "zeta06@cloud.com",
    emailPassword: "CloudMail06",
    inboundAt: daysAgo(7, 2),
  },
  {
    id: "7",
    username: "eta_stream07",
    password: "Stream7!",
    email: "eta07@media.tv",
    emailPassword: "Media07",
    url: "https://stream.example.com",
    inboundAt: daysAgo(6, 4),
  },
  {
    id: "8",
    username: "theta_game08",
    password: "Game8Play#",
    inboundAt: daysAgo(5, 1),
  },
  {
    id: "9",
    username: "iota_fin09",
    password: "Fin9Secure",
    email: "iota09@finance.bank",
    emailPassword: "BankMail09",
    inboundAt: daysAgo(4, 7),
  },
  {
    id: "10",
    username: "kappa_social10",
    password: "Social10!",
    email: "kappa10@social.net",
    emailPassword: "SocMail10",
    url: "https://social.example.com",
    inboundAt: daysAgo(3, 2),
  },
  {
    id: "11",
    username: "lambda_api11",
    password: "Api11Token",
    inboundAt: daysAgo(2, 5),
  },
  {
    id: "12",
    username: "mu_data12",
    password: "Data12#Key",
    email: "mu12@data.org",
    emailPassword: "DataMail12",
    inboundAt: daysAgo(1, 3),
  },
  {
    id: "13",
    username: "nu_latest13",
    password: "Latest13!",
    email: "nu13@new.com",
    emailPassword: "NewMail13",
    url: "https://new.example.com",
    inboundAt: daysAgo(0, 1),
  },
];

export const mockHistory: OutboundRecord[] = [
  {
    id: "h1",
    username: "old_user01",
    password: "OldPass01",
    email: "old01@mail.com",
    emailPassword: "OldMail01",
    inboundAt: daysAgo(20, 0),
    outboundAt: daysAgo(0, 4),
  },
  {
    id: "h2",
    username: "old_user02",
    password: "OldPass02",
    inboundAt: daysAgo(18, 2),
    outboundAt: daysAgo(0, 2),
  },
  {
    id: "h3",
    username: "alpha_user01",
    password: "PrevPass01",
    email: "alpha01@old.com",
    inboundAt: daysAgo(30, 0),
    outboundAt: daysAgo(1, 6),
  },
  {
    id: "h4",
    username: "retired04",
    password: "Retire04",
    email: "retired04@corp.net",
    emailPassword: "RetMail04",
    url: "https://old.example.com",
    inboundAt: daysAgo(25, 1),
    outboundAt: daysAgo(1, 2),
  },
  {
    id: "h5",
    username: "batch_out05",
    password: "Batch05!",
    inboundAt: daysAgo(15, 3),
    outboundAt: daysAgo(2, 5),
  },
  {
    id: "h6",
    username: "batch_out06",
    password: "Batch06!",
    email: "batch06@test.com",
    inboundAt: daysAgo(14, 1),
    outboundAt: daysAgo(2, 5),
  },
  {
    id: "h7",
    username: "archive07",
    password: "Arch7Key",
    inboundAt: daysAgo(40, 0),
    outboundAt: daysAgo(5, 3),
  },
  {
    id: "h8",
    username: "legacy08",
    password: "Legacy08#",
    email: "legacy08@archive.org",
    emailPassword: "ArchMail08",
    inboundAt: daysAgo(35, 2),
    outboundAt: daysAgo(7, 1),
  },
];

export const mockActivities: ActivityItem[] = [
  { id: "a1", type: "outbound", username: "old_user01", timestamp: daysAgo(0, 4) },
  { id: "a2", type: "inbound", username: "nu_latest13", timestamp: daysAgo(0, 1) },
  { id: "a3", type: "outbound", username: "old_user02", timestamp: daysAgo(0, 2) },
  { id: "a4", type: "inbound", username: "mu_data12", timestamp: daysAgo(1, 3) },
  { id: "a5", type: "outbound", username: "retired04", timestamp: daysAgo(1, 2) },
  { id: "a6", type: "inbound", username: "lambda_api11", timestamp: daysAgo(2, 5) },
  { id: "a7", type: "outbound", username: "batch_out05", timestamp: daysAgo(2, 5) },
  { id: "a8", type: "outbound", username: "batch_out06", timestamp: daysAgo(2, 5) },
  { id: "a9", type: "inbound", username: "kappa_social10", timestamp: daysAgo(3, 2) },
  { id: "a10", type: "inbound", username: "iota_fin09", timestamp: daysAgo(4, 7) },
];

export const mockStats = {
  inventoryCount: mockInventory.length,
  todayInbound: 2,
  todayOutbound: 3,
  pendingCount: 0,
};

export function getInventoryUsernames(): Set<string> {
  return new Set(mockInventory.map((a) => a.username));
}

export function getOutboundUsernames(): Set<string> {
  return new Set(mockHistory.map((a) => a.username));
}

export function getOutboundTimes(): Map<string, string> {
  const map = new Map<string, string>();
  for (const r of mockHistory) {
    const existing = map.get(r.username);
    if (!existing || r.outboundAt > existing) {
      map.set(r.username, r.outboundAt);
    }
  }
  return map;
}

export const SAMPLE_FORMAT = `账号----密码----邮箱----邮箱密码----网址
alpha_user01----Pass@2026a----alpha01@mail.example.com----MailPass01!----https://platform.example.com/login
beta_test02----Beta#Secure2----beta02@corp.net----CorpMail02`;
