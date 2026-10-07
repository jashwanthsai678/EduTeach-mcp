# EduTeach Textbook Connector (MCP)

A remote [MCP](https://modelcontextprotocol.io) server that lets Claude pull
real, published school-textbook content mid-conversation, so it can ground
explanations/worksheets/lesson material in the actual textbook instead of its
own general knowledge -- without the user needing an API key or a separate app.

This is a **thin proxy**, not a new data layer: it holds no database of its
own and does no extraction. It just exposes two already-live services as MCP
tools.

## How it fits with the rest of the EduTeach stack

```
Claude (MCP client)
     │  tool calls
     ▼
textbook-connector (this repo)
     │                              │
     │ get_chapter / list_books     │ search_textbook
     ▼                              ▼
eduteach-textbook-api          textbook-retrieval
(read-only catalog REST API,   (Qdrant semantic search
 covers all published books)    over indexed books only)
```

## Tools

- **`list_books(board?, grade?, subject?, language?)`** -- discover a book's
  exact `book_id` from natural-language filters.
- **`get_chapter(book_id, chapter_number)`** -- full, clean chapter text +
  image URLs. **Preferred path** whenever the user names a specific
  textbook/chapter directly -- covers every published book, no search
  overhead.
- **`search_textbook(query, book_id? | board?/grade?/subject?/language?, chapter?, top_k_text, top_k_images)`**
  -- semantic search for a topic when the exact location isn't known. Falls
  back to returning `candidate_books` instead of guessing when
  board/grade/subject resolves to more than one book. Only covers books that
  have actually been indexed in Qdrant (a subset of the full catalog as of
  writing) -- `get_chapter` is the complete-coverage fallback.
- **`view_image(url)`** -- fetches one image's real bytes (as a native MCP
  image block) so Claude can actually see it via vision before deciding to
  include it, instead of only ever inferring relevance from its caption
  text. Only accepts URLs from known textbook-image storage hosts (not an
  open proxy for arbitrary URLs).

## Routing rule this encodes

Specific request ("chapter 3 of Class 5 EVS") -> `list_books` (if book_id
unknown) then `get_chapter`, direct and complete. Vague/topical request
("explain photosynthesis for class 5") -> `search_textbook`. The tool
descriptions are written so Claude picks the right one itself; there's no
hardcoded routing logic in the server.

## Local run

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # defaults already point at the live upstream APIs
python -m mcp_server.server
```

Serves streamable-HTTP MCP at `http://localhost:8000/mcp`.

## Environment variables

See `.env.example` -- `CATALOG_API_BASE` and `RETRIEVAL_API_BASE` default to
the live deployed upstream services, so no values are required to run
locally against production data. `PORT` is set automatically by Render in
deployment.

## Docker / deploy

```
docker build -t textbook-connector .
docker run -p 8000:8000 --env-file .env textbook-connector
```

Deploys as a Render **Web Service** (not Static Site) the same way the other
EduTeach services do: build command `pip install -r requirements.txt`, start
command `python -m mcp_server.server`.

Once deployed, add it in Claude as a custom connector using the deployed
URL + `/mcp`.

## Status

- ✅ Core client logic (`core/`) verified against both live upstream APIs.
- ✅ MCP server verified end-to-end locally (`tools/list` and `tools/call`
  over streamable-HTTP).
- ✅ Deployed on Render at `https://eduteach-mcp.onrender.com/mcp`.
- ✅ Added as a connector in Claude.
- ✅ **Fail-fast on cold starts.** Both upstream services are free-tier Render
  and cold-start in ~20-30s after idling; this connector itself is also a
  free-tier Render service. With three such services chained, a naive
  internal-retry approach can block well past what the calling MCP client
  will wait, surfacing as a hard "Failed" even though the upstream would
  have come up fine moments later. Fixed by making `core/catalog_client.py`
  / `core/retrieval_client.py` try once with a ~20s timeout and raise
  `UpstreamUnavailable` with a message telling the caller to retry, instead
  of blocking for minutes -- the MCP SDK surfaces that message to Claude
  directly, which can then retry the same tool call itself.
- ⬜ **Keep-warm ping not yet set up.** Without one, the *first* call after
  ~15 min idle will still show this cold-start message once before
  succeeding on retry. Recommended: an external scheduler (e.g.
  cron-job.org, free) hitting all three health endpoints every ~10 min:
  `eduteach-mcp.onrender.com` (add a `/health` route if pinging this one),
  `eduteach-textbook-api.onrender.com/published/books`,
  `text-book-rag.onrender.com/health`.
- ⬜ ChatGPT Custom GPT Action (OpenAPI wrapper over the same `core/tools.py`)
  not yet built -- planned as a second interface on this same core, once the
  MCP side is confirmed working end-to-end from inside Claude.
