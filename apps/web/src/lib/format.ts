export function compactId(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }

  if (value.length <= 12) {
    return value;
  }

  return `${value.slice(0, 8)}...${value.slice(-4)}`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(parsed);
}

export function formatDecimal(
  value: string | number | null | undefined,
  fractionDigits = 2,
): string {
  if (value === null || value === undefined || value === "") {
    return "--";
  }

  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }

  return new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(numeric);
}

export function formatSignedMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "--";
  }

  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }

  const sign = numeric > 0 ? "+" : "";
  return `${sign}${formatDecimal(numeric, 2)}`;
}

export function summarizePayload(payload: Record<string, unknown> | null | undefined): string {
  if (!payload || Object.keys(payload).length === 0) {
    return "No payload details";
  }

  const serialized = JSON.stringify(payload);
  if (serialized.length <= 132) {
    return serialized;
  }

  return `${serialized.slice(0, 129)}...`;
}

export function titleCase(value: string | null | undefined): string {
  if (!value) {
    return "Unknown";
  }

  return value
    .split("_")
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1).toLowerCase())
    .join(" ");
}

