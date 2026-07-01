"""EDIFACT Orders Generator – src package."""
# Authorised UNB profile constants
AUTHORISED_PROFILE_ID = "ELM_STANDARD"
AUTHORISED_SENDER_ID = "4399901876613"
AUTHORISED_RECEIVER_ID = "3015981600108"

# These values must NEVER appear in generated output or active code paths
FORBIDDEN_SENDER_IDS: frozenset[str] = frozenset({"3020810000707", "54209794400681"})
FORBIDDEN_RECEIVER_IDS: frozenset[str] = frozenset({"3020810000707", "54209794400681"})
