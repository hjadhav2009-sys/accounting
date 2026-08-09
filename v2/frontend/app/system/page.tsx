import {AppShell} from "../../components/AppShell";
import {PageHeader} from "../../components/PageHeader";
import {SystemHealth} from "../../components/SystemHealth";

export default function SystemPage(){return <AppShell active="System Health"><PageHeader title="System Health" description="Check local services, storage, OCR, AI policy, and legacy compatibility without exposing secrets or running accounting operations."/><SystemHealth/></AppShell>}
