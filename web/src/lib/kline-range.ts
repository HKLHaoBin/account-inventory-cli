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

export function clampRangeToDataBounds(
  fromMs: number,
  toMs: number,
  bounds: { dataFromMs: number | null; dataToMs: number | null },
  paddingRatio = 0
): { fromMs: number; toMs: number } {
  if (bounds.dataFromMs === null || bounds.dataToMs === null) {
    return { fromMs, toMs };
  }

  const dataFromMs = bounds.dataFromMs;
  const dataToMs = bounds.dataToMs;
  const requestSpan = Math.max(0, toMs - fromMs);
  const dataSpan = Math.max(0, dataToMs - dataFromMs);

  let from: number;
  let to: number;

  if (requestSpan > dataSpan) {
    from = dataFromMs;
    to = dataToMs;
  } else if (toMs < dataFromMs) {
    from = dataFromMs;
    to = Math.min(dataFromMs + requestSpan, dataToMs);
  } else if (fromMs > dataToMs) {
    to = dataToMs;
    from = Math.max(dataToMs - requestSpan, dataFromMs);
  } else {
    from = Math.max(fromMs, dataFromMs);
    to = Math.min(toMs, dataToMs);
  }

  if (paddingRatio > 0) {
    const span = Math.max(0, to - from);
    const padding = span * paddingRatio;
    from = Math.max(dataFromMs, from - padding);
    to = Math.min(dataToMs, to + padding);
  }

  return { fromMs: from, toMs: to };
}

export function mergeLoadedRange(
  current: { fromMs: number; toMs: number },
  next: { fromMs: number; toMs: number }
): { fromMs: number; toMs: number } {
  if (current.fromMs === 0 && current.toMs === 0) {
    return next;
  }

  return {
    fromMs: Math.min(current.fromMs, next.fromMs),
    toMs: Math.max(current.toMs, next.toMs),
  };
}

export function loadedRangeCovers(
  loaded: { fromMs: number; toMs: number },
  target: { fromMs: number; toMs: number }
): boolean {
  if (loaded.fromMs === 0 && loaded.toMs === 0) {
    return false;
  }

  return loaded.fromMs <= target.fromMs && loaded.toMs >= target.toMs;
}

export function shouldExpandLoadedRange(
  visible: { fromMs: number; toMs: number },
  loaded: { fromMs: number; toMs: number },
  thresholdRatio = 0.15
): boolean {
  const loadedSpan = Math.max(0, loaded.toMs - loaded.fromMs);
  if (loadedSpan === 0) {
    return true;
  }

  const threshold = loadedSpan * thresholdRatio;
  const nearLeftEdge = visible.fromMs - loaded.fromMs < threshold;
  const nearRightEdge = loaded.toMs - visible.toMs < threshold;
  return nearLeftEdge || nearRightEdge;
}
