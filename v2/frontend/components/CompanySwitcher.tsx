export function CompanySwitcher() {
  const companyId = process.env.NEXT_PUBLIC_COMPANY_ID || "";
  return (
    <label className="switcher">
      <span>Company</span>
      <select aria-label="Selected company" defaultValue={companyId || "current"}>
        <option value={companyId || "current"}>{companyId ? `Company ${companyId.slice(0, 8)}…` : "Company not configured"}</option>
      </select>
    </label>
  );
}
