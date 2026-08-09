import {AppShell} from "../../components/AppShell";
import {BankStatementWorkspace} from "../../components/BankStatementWorkspace";
import {PageHeader} from "../../components/PageHeader";

export default function BankPage(){return <AppShell active="Bank Statement XML"><PageHeader title="Bank Statement XML" description="Extract transactions, verify the closing balance, resolve narration mappings, and export authorized Tally Receipt and Payment vouchers."/><BankStatementWorkspace/></AppShell>}
