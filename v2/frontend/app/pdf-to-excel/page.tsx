import {AccountingExcelWorkspace} from "../../components/AccountingExcelWorkspace";
import {AppShell} from "../../components/AppShell";
import {PageHeader} from "../../components/PageHeader";

export default function PdfToExcelPage(){return <AppShell active="PDF to Excel"><PageHeader title="PDF to Excel" description="Upload, validate, preview, and export accounting rows using certified deterministic parsing and tenant-scoped evidence."/><AccountingExcelWorkspace/></AppShell>}
