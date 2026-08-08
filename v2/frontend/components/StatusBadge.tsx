export type Status = "VERIFIED" | "REVIEW" | "BLOCKED";

export function StatusBadge({ status }: { status: Status }) {
  return <span className={`status status-${status.toLowerCase()}`}>{status}</span>;
}
