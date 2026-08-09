import { AppShell } from "../../components/AppShell";
import { PageHeader } from "../../components/PageHeader";
import { UserWorkspace } from "../../components/UserWorkspace";

export default function UsersPage(){return <AppShell active="Users"><PageHeader title="Users" description="Create accounts, assign company roles, disable access, and review login state without exposing credentials."/><UserWorkspace/></AppShell>}
