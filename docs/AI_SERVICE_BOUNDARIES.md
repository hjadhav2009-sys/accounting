# AI Service Boundaries

Phase 1 defines protocols only: `DocumentIntelligenceService`, `OcrService`, `LocalAiService`, `CloudAiService`, `PrivacyService`, `AiQuotaService`, and `TemplateGenerationService`. There are no credentials, network calls, models, OCR replacement, or AI inference.

Processing modes are LOCAL_ONLY, HYBRID_PRIVATE, and FULL_CLOUD_ADMIN_OPT_IN. Future quota states are NORMAL, WARNING, CRITICAL, LOCAL_ONLY, and QUEUE_UNTIL_RESET; paid fallback is never automatic.

AI may propose extraction/template structure. It cannot establish authoritative accounting values, post vouchers, change ledgers/templates without approval, bypass deterministic validation, or override mismatches. The required sequence is proposal → deterministic validation → human approval when required → versioned rule/template.
