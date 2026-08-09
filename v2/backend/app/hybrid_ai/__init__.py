"""Phase 5 hybrid document-intelligence boundary.

Model output is advisory. Deterministic validation and Template Studio remain the
only route to persisted template changes.
"""

from .models import AiMode, BillingMode, ConfidenceBand, PrivacyMode, ResultState
from .service import HybridAiService

__all__ = ["AiMode", "BillingMode", "ConfidenceBand", "HybridAiService", "PrivacyMode", "ResultState"]
