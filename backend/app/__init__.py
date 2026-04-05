"""AssistantBot Backend Application."""

import os

# Prevent HuggingFace tokenizers fork warning/deadlock risks in reload/fork mode.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
