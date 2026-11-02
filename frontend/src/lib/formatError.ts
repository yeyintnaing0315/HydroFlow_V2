export function formatApiDetail(detail: unknown): string {
  if (detail == null) return "Request failed";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (typeof detail === "object" && "msg" in detail) {
    return String((detail as { msg: unknown }).msg);
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

export function errorText(reason: unknown): string {
  if (reason instanceof Error) return reason.message;
  return formatApiDetail(reason);
}
