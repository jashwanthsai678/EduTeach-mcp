import os

from dotenv import load_dotenv

load_dotenv()

CATALOG_API_BASE = os.environ.get(
    "CATALOG_API_BASE", "https://eduteach-textbook-api.onrender.com"
).rstrip("/")

RETRIEVAL_API_BASE = os.environ.get(
    "RETRIEVAL_API_BASE", "https://text-book-rag.onrender.com"
).rstrip("/")

SIMULATION_HOST_BASE = os.environ.get(
    "SIMULATION_HOST_BASE", "https://eduteach-simulation-host.onrender.com"
).rstrip("/")

# Both upstream APIs are free-tier Render services that cold-start in ~25-30s
# after ~15 min idle. A tool call that blocks that long (or longer, with
# internal retries stacked on top) outlasts the calling MCP client's own
# patience and gets reported as "Failed" even though the upstream would have
# come up fine a few seconds later. So: one attempt, a timeout just above
# typical cold-start time, and fail fast with a message telling the caller
# to retry -- rather than silently blocking until the client gives up anyway.
HTTP_TIMEOUT_SECONDS = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "20"))
