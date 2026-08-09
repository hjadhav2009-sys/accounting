import {AppShell} from "../../components/AppShell";
import {MarketplaceWorkspace} from "../../components/MarketplaceWorkspace";
import {PageHeader} from "../../components/PageHeader";

export default function MarketplacePage(){return <AppShell active="Marketplace XML"><PageHeader title="Marketplace XML" description="Parse marketplace fees, resolve PostgreSQL ledger mappings, validate Purchase or Debit Note classification, and export tenant-scoped Tally XML."/><MarketplaceWorkspace/></AppShell>}
