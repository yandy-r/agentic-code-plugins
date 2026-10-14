"""Always-loaded description listing budget shared by skills and opencode commands.

Single source of truth for the YAN-1083 / YAN-1102 budget: both the skill
practices validator and the generated opencode command validator import these.
"""

from __future__ import annotations

DESCRIPTION_LIMIT = 300  # per-description target for the always-loaded listing
DESCRIPTION_TOTAL_CAP = 12000  # aggregate description chars across the listing
