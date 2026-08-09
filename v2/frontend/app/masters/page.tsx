import {AppShell} from "../../components/AppShell";
import {MastersWorkspace} from "../../components/MastersWorkspace";
import {PageHeader} from "../../components/PageHeader";

export default function MastersPage(){return <AppShell active="Database / Masters"><PageHeader title="Database / Masters" description="Manage PostgreSQL bank accounts, party ledgers, GST ledgers, voucher rules, and audited mappings for the selected company."/><MastersWorkspace/></AppShell>}
