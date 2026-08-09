import {AppShell} from "../../components/AppShell";
import {PageHeader} from "../../components/PageHeader";
import {ParityWorkspace} from "../../components/ParityWorkspace";

export default function ParityPage(){return <AppShell active="Legacy vs V2"><PageHeader title="Legacy vs V2" description="Compare the certified reference result with an independently executed V2 template. Reference output is never supplied to V2 as a hint."/><ParityWorkspace/></AppShell>}
