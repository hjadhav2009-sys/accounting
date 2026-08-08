export function FilterBar() {
  return (
    <div className="filter-bar" aria-label="Document filters">
      <label>
        <span className="sr-only">Search documents</span>
        <input type="search" placeholder="Search documents, invoices, suppliers…" />
      </label>
      <button type="button" className="filter-button">All workflows</button>
      <button type="button" className="filter-button">All statuses</button>
    </div>
  );
}
