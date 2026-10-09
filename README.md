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
- **`list_chapters(book_id)`** -- a book's chapter titles/page ranges, no
  content or images. Lets the model see what a book covers, or pick the
  right chapter_number, without paying the cost of fetching full chapter
  content just to see titles.
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
- **`create_simulation(html)`** -- for "can you make a simulation of this?"
  requests (not static images). Pass a complete, self-contained HTML/CSS/JS
  page; it's uploaded as-is to `eduteach-simulation-host` and a public URL
  comes back to share with the user, who opens it in their own browser where
  it runs live and interactively. This connector never renders or executes
  the page itself.
- **`create_prep_sheet(prep_sheet)`** -- for "create the prep material/prep
  sheet" requests (not a simulation). Pass structured content, not HTML: a
  topic, optional one-line goal/floor, and the 6 buckets (Refresher, Concept,
  Real Life, Challenge, Level Set, Explore -- Refresher and Real Life are
  optional, the rest required). This isn't freeform -- the tool's own
  description carries exact, non-negotiable authoring rules per bucket (e.g.
  Concept's teaching example must be a small handheld object, never the same
  one Challenge uses; Explore's details must all read as the teacher
  speaking, "Tell students that/to..."; Level Set is always exactly 3
  bullets with a fixed structure), all grounded in the textbook excerpt
  already fetched this conversation -- never inventing facts.
  `eduteach-simulation-host` lays this out using EduTeach's real prep-sheet
  design and renders it to a PDF; the returned `url` points at that PDF. The
  Refresher bucket is filled from Claude/ChatGPT's own memory of an earlier
  topic prepped *in the same conversation* -- there's no tool or storage
  involved in recalling it, so a brand-new chat has no previous Explore to
  draw on and Refresher is simply omitted (a known v1 limitation, not a bug).

## Classroom profile (gates create_prep_sheet / create_simulation)

Before its first call to either output tool in a conversation, the model is
instructed to ask the teacher a short classroom-profile questionnaire --
class size, the real ability level of most students relative to the nominal
grade, and four context toggles (everyday objects available, children can
move around vs. seated, each child has their own textbook vs. shared,
Telugu-language help vs. English-only). The answers then shape every
generation in that conversation (vocabulary/complexity, activity design,
bilingual labels, etc.) instead of the model assuming a generic classroom.

This is a plain conversational step, not a new tool or stored data -- same
pattern as the ambiguous-board check above, just a different trigger. A
plain-language correction later in the same chat (e.g. "we don't have a
shared textbook anymore") updates it without re-asking the full
questionnaire. **It does not persist across conversations** -- a new chat
starts over, same limitation as Refresher. True cross-chat persistence
would require adding real per-teacher identity (an OAuth connect flow) and
a database, which is a deliberate v1 trade-off, not built.

## Routing rule this encodes

Three cases, once `list_books` has resolved the `book_id`:

1. **Whole chapter, no narrower topic** ("give me chapter 2 of Class 5 EVS")
   -> `get_chapter(book_id, chapter_number)` -- full, complete, authoritative
   text, no search overhead.
2. **Topic named, chapter unknown** ("explain photosynthesis for class 5")
   -> `search_textbook(query, book_id)`, searching the whole book.
3. **Topic named AND chapter named** ("chapter 2, the tools topic") ->
   `search_textbook(query, book_id, chapter)`, scoped to that chapter. This
   is deliberately preferred over `get_chapter` here -- fetching an entire
   chapter just to manually find one topic inside it costs far more tokens
   than a scoped search already returns directly. `get_chapter` is only the
   fallback if the scoped search comes back empty.

Verified live against production: `search_textbook("agriculture tools",
book_id="ts_scert_class5_environmental_studies_en", chapter=2)` returns
"2.2 Agricultural equipment/tools" as the top-ranked chunk -- the exact
section, not the whole ~3,400-word chapter.

The tool descriptions are written so Claude picks the right one itself;
there's no hardcoded routing logic in the server.

## Ambiguity across multiple boards (future-proofing, not yet triggerable)

Today every grade/subject combination maps to exactly one book (TS SCERT is
the only board published), so `list_books` never actually returns more than
one match. Once other state boards publish the same grade/subject, the same
request ("explain chapter 1 of class 5 EVS") could match several real books.
The instructions explicitly tell the model: if `list_books` returns more
than one match, don't guess which board the user meant and don't call
`get_chapter` yet -- ask the user to pick, naming the real options, then
proceed once they answer. This is a plain conversational turn (the model
just replies in chat instead of calling a tool), not a new mechanism --
nothing to build for the back-and-forth itself, only the instruction that
triggers it at the right moment instead of silently guessing a board.

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
- ⬜ **`create_prep_sheet` built and verified locally** (request shape,
  rendering, and PDF generation all confirmed working), **but not yet live
  in production** -- `eduteach-simulation-host` must be redeployed on Render
  as a **Docker** environment (not its current native Python buildpack) for
  Playwright's Chromium to run at all; see that repo's README "Render
  deploy" section. Once that switch is made and the new bucket
  (`prep-sheets`) exists, this tool will work the same way `create_simulation`
  does today.
