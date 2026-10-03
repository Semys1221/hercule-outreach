"""Post-push link provisioning via Hercule Next.js API (shared implementation)."""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.link_provision_client import (  # noqa: E402
    provision_leads_after_push,
    provision_leads_batches,
)

__all__ = ["provision_leads_after_push", "provision_leads_batches"]
