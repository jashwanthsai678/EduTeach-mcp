import os

from dotenv import load_dotenv

load_dotenv()

CATALOG_API_BASE = os.environ.get(
    "CATALOG_API_BASE", "https://eduteach-textbook-api.onrender.com"
).rstrip("/")

RETRIEVAL_API_BASE = os.environ.get(
    "RETRIEVAL_API_BASE", "https://text-book-rag.onrender.com"
).rstrip("/")

# Both upstream APIs are free-tier Render services that cold-start slowly.
HTTP_TIMEOUT_SECONDS = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "60"))
