export function ReviewBadge({ count }: { count: number }) {
  return <span className="review-badge" aria-label={`${count} review notifications`}>{count}</span>;
}
