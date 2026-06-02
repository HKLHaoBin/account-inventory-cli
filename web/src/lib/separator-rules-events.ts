export const SEPARATOR_RULES_CHANGED_EVENT = "separator-rules:changed";

export function emitSeparatorRulesChanged() {
  window.dispatchEvent(new CustomEvent(SEPARATOR_RULES_CHANGED_EVENT));
}

export function subscribeSeparatorRulesChanged(listener: () => void) {
  const handler = () => listener();
  window.addEventListener(SEPARATOR_RULES_CHANGED_EVENT, handler);
  return () => window.removeEventListener(SEPARATOR_RULES_CHANGED_EVENT, handler);
}
