import { StatusBadge, type Status } from "./StatusBadge";

const rows: Array<{ document: string; workflow: string; updated: string; status: Status }> = [
  { document: "Invoice batch review", workflow: "PDF to Excel", updated: "Awaiting source", status: "REVIEW" },
  { document: "Marketplace vouchers", workflow: "Marketplace XML", updated: "Foundation ready", status: "VERIFIED" },
  { document: "Bank reconciliation", workflow: "Bank Statement XML", updated: "Not connected", status: "BLOCKED" },
];

export function DataTable() {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Work item</th><th>Workflow</th><th>Current state</th><th>Status</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.document}>
              <td><strong>{row.document}</strong></td>
              <td>{row.workflow}</td>
              <td>{row.updated}</td>
              <td><StatusBadge status={row.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
