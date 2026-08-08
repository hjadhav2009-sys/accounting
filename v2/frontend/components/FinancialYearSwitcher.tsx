export function FinancialYearSwitcher() {
  return (
    <label className="switcher compact">
      <span>Financial year</span>
      <select aria-label="Financial year placeholder" defaultValue="2026-27">
        <option value="2026-27">2026–27</option>
      </select>
    </label>
  );
}
