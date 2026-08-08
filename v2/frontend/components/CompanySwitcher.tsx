export function CompanySwitcher() {
  return (
    <label className="switcher">
      <span>Company</span>
      <select aria-label="Company placeholder" defaultValue="current">
        <option value="current">Current company</option>
      </select>
    </label>
  );
}
