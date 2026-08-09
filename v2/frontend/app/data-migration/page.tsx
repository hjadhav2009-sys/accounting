import {AppShell} from "../../components/AppShell";
import {DataMigrationWorkspace} from "../../components/DataMigrationWorkspace";
import {PageHeader} from "../../components/PageHeader";

export default function DataMigrationPage(){return <AppShell active="Data Migration"><PageHeader title="Existing Data Migration" description="Preview and validate the immutable Business Automation SQLite database before importing company-specific masters into PostgreSQL."/><DataMigrationWorkspace/></AppShell>}
