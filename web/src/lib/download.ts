function timestampForFilename(date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    "-",
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
  ].join("");
}

export function defaultOutboundTextFilename(): string {
  return `outbound-${timestampForFilename()}.txt`;
}

export function defaultHistoryTextFilename(
  mode: "all" | "inbound" | "outbound"
): string {
  return `history-${mode}-${timestampForFilename()}.txt`;
}

export function downloadTextFile(
  text: string,
  filename = defaultOutboundTextFilename()
): void {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
