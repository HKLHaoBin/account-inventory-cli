export const DATABASE_CHANGED_EVENT = "database:changed";

export function emitDatabaseChanged(databaseId?: string) {
  window.dispatchEvent(
    new CustomEvent(DATABASE_CHANGED_EVENT, {
      detail: { databaseId },
    })
  );
}

export function subscribeDatabaseChanged(listener: () => void) {
  const handler = () => listener();
  window.addEventListener(DATABASE_CHANGED_EVENT, handler);
  return () => window.removeEventListener(DATABASE_CHANGED_EVENT, handler);
}
