export function padVisibleRange(
  fromMs: number,
  toMs: number,
  ratio = 0.2
): { fromMs: number; toMs: number } {
  const span = Math.max(0, toMs - fromMs);
  const padding = span * ratio;
  return {
    fromMs: fromMs - padding,
    toMs: toMs + padding,
  };
}
