import {AccountingExcelWorkspace} from "../../components/AccountingExcelWorkspace";
import {AppShell} from "../../components/AppShell";
import {PageHeader} from "../../components/PageHeader";

export default function InvoiceConverterPage(){return <AppShell active="Invoice Converter"><PageHeader title="Invoice Converter" description="Convert Tax Invoices, Credit Notes, Stock Transfers, and approved custom invoice-like formats to verified Excel."/><AccountingExcelWorkspace invoiceMode/></AppShell>}
