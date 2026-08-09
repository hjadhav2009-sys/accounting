"""One synthetic live Cloudflare -> validated action -> PostgreSQL DRAFT -> deterministic preview check."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

import psycopg

from v2.backend.app.hybrid_ai.models import BillingMode
from v2.backend.app.hybrid_ai.proposal import validate_proposal
from v2.backend.app.hybrid_ai.providers import CloudAiService
from v2.backend.app.hybrid_ai.quota import AiQuotaService
from v2.backend.app.hybrid_ai.template_actions import TemplateActionAdapter
from v2.backend.app.infrastructure.postgres_migrations import apply_migrations
from v2.backend.app.template_studio.models import StudioContext
from v2.backend.app.template_studio.repository import TemplateRepository
from v2.backend.app.template_studio.service import TemplateStudioService


def env_value(name: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="): return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError(f"{name} is not configured")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    database_url = env_value("POSTGRES_TEST_DATABASE_URL")
    secret = (ROOT / "local_tools" / "cloudflare_worker_hmac.secret").read_text(encoding="utf-8").strip()
    quota = AiQuotaService(limit=10_000, billing_mode=BillingMode.FREE_ONLY)
    reservation = quota.reserve(500)
    if not reservation.allowed: raise RuntimeError("FREE_ONLY reservation unexpectedly blocked")
    result = CloudAiService(args.url, secret, timeout_seconds=180).complete(
        "TEMPLATE_PROPOSAL", "TEXT_TOOL_MODEL",
        "Synthetic sanitized bank columns: Date, Narration, Debit, Credit, Balance. "
        "Return exactly one create_table action for a new DRAFT bank mapping; never approve it.",
        f"cloud-action-{uuid4()}",
    )
    quota_status = quota.reconcile(reservation.reservation_id, result.usage.accounted_neurons)
    proposal = validate_proposal(result.payload, provider=result.provider, model=result.model,
                                 prompt_version="phase5b-cloud-runtime")
    if len(proposal.actions) != 1 or proposal.actions[0].action != "create_table":
        raise RuntimeError("cloud model did not return the single requested safe table action")

    connection = psycopg.connect(database_url); apply_migrations(connection)
    org, company, user = uuid4(), uuid4(), uuid4()
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)", (org, f"Cloud Phase5B {org}"))
        cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Cloud Phase5B','Cloud Phase5B')", (company, org))
        cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'Cloud Phase5B','ACTIVE')", (user, org, f"{user}@example.invalid"))
    connection.commit(); connection.close()
    studio = TemplateStudioService(TemplateRepository(lambda: psycopg.connect(database_url)))
    context = StudioContext(org, company, user, frozenset({"ADMIN"}))
    version = studio.create_family(context, "Cloud Phase5B synthetic bank", "BANK", mode="GENERIC")["version"]
    selection = {"box": {"x0": .05, "y0": .2, "x1": .95, "y1": .8}, "columns": [
        {"boundary": .18, "field": "date"}, {"boundary": .48, "field": "narration"},
        {"boundary": .65, "field": "debit"}, {"boundary": .82, "field": "credit"},
        {"boundary": .98, "field": "balance"},
    ]}
    evidence = {"pages": [{"page_number": 1, "tables": [{
        "bounding_box": {"x0": 5, "y0": 20, "x1": 95, "y1": 80, "page_width": 100, "page_height": 100},
        "rows": [{"cells": [{"text": "2026-08-09"}, {"text": "Synthetic"},
                              {"text": "100"}, {"text": "0"}, {"text": "900"}]}],
    }]}]}
    applied = TemplateActionAdapter(studio).apply(
        context, version["id"], version["revision"], proposal.actions[0], selection, evidence,
    )
    print(json.dumps({
        "synthetic_only": True,
        "provider": result.provider,
        "model": result.model,
        "model_action": proposal.actions[0].action,
        "draft_status": applied.saved["status"],
        "new_revision": applied.saved["revision"],
        "deterministic_preview_ran": True,
        "preview_validation": applied.preview["validation"],
        "human_approval_required": applied.human_approval_required,
        "provider_reported_neurons": result.usage.provider_reported_neurons,
        "application_estimated_neurons": result.usage.application_estimated_neurons,
        "accounting_basis": result.usage.accounting_basis,
        "quota_used_estimate": quota_status.used,
        "raw_payload_retained": False,
    }, default=str, indent=2))


if __name__ == "__main__": main()
