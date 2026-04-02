export interface CartesianPoint {
  x: number;
  y: number;
}

export function resolveRange(
  values: number[],
  paddingRatio = 0.08,
  minimumPadding = 1,
): { min: number; max: number } {
  if (values.length === 0) {
    return { min: 0, max: 1 };
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) {
    return {
      min: min - minimumPadding,
      max: max + minimumPadding,
    };
  }

  const padding = Math.max((max - min) * paddingRatio, minimumPadding * 0.1);
  return {
    min: min - padding,
    max: max + padding,
  };
}

export function buildLinePath(points: CartesianPoint[]): string {
  if (points.length === 0) {
    return "";
  }

  return points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
}

export function buildAreaPath(points: CartesianPoint[], baselineY: number): string {
  if (points.length === 0) {
    return "";
  }

  const first = points[0];
  const last = points[points.length - 1];
  const linePath = buildLinePath(points);

  return [
    `M ${first.x.toFixed(2)} ${baselineY.toFixed(2)}`,
    linePath,
    `L ${last.x.toFixed(2)} ${baselineY.toFixed(2)}`,
    "Z",
  ].join(" ");
}

export function buildTicks(range: { min: number; max: number }, tickCount = 4): number[] {
  if (tickCount < 2) {
    return [range.min, range.max];
  }

  const ticks: number[] = [];
  const step = (range.max - range.min) / (tickCount - 1);
  for (let index = 0; index < tickCount; index += 1) {
    ticks.push(range.min + step * index);
  }
  return ticks.reverse();
}

