"""Remote MCP server exposing EduTeach's published textbook content to Claude.

Seven tools:
  - list_books        : discover a book_id from board/grade/subject/language
  - list_chapters     : a book's chapter titles/pages, no content or images
  - get_chapter       : exact, full-content lookup once the book/chapter is known
  - search_textbook   : semantic search for a topic when the exact location isn't known
  - view_image        : fetch one image's real bytes so Claude can actually see it
                        (vision), not just infer relevance from its caption text
  - create_simulation : host a generated interactive HTML/CSS/JS page, get a URL
  - create_prep_sheet : render the 6-bucket lesson prep sheet to a PDF, get a URL

Run locally:   python -m mcp_server.server
Deployed:      streamable-http transport, bound to 0.0.0.0:$PORT (see Dockerfile)
"""

import os

from mcp.server.fastmcp import FastMCP, Image
from starlette.requests import Request
from starlette.responses import JSONResponse

from core import tools
from core.image_fetch import fetch_image
from core.prep_sheet_schema import PrepSheetRequest

mcp = FastMCP(
    name="eduteach-textbook-connector",
    instructions=(
        "Tools for grounding answers in real, published school-textbook content "
        "(TS SCERT boards so far, more boards may be added later). If the user "
        "names a specific textbook/chapter, call list_books (if you don't "
        "already have the exact book_id) first. If list_books returns MORE "
        "THAN ONE match for what the user asked (e.g. once multiple state "
        "boards publish the same grade/subject), do not guess which one they "
        "meant and do not fetch content yet -- ask the user to clarify, "
        "naming the real options (e.g. \"I found this for Telangana SCERT, AP "
        "SCERT, and CBSE -- which one does your school follow?\"), then "
        "proceed once they answer. Only skip asking when there's exactly one "
        "match, or the user already named the board. Call list_chapters first "
        "if you need to see what a book covers, or to pick the right chapter "
        "number, without paying the cost of fetching full content just to see "
        "titles. "
        "THREE CASES for fetching actual content, once the book_id is known: "
        "(1) the user wants a whole chapter with no narrower topic named (e.g. "
        "\"give me chapter 2\") -- call get_chapter(book_id, chapter_number): "
        "full, complete, authoritative text, no search overhead. "
        "(2) the user names a specific topic/sub-section but NOT which chapter "
        "it's in (e.g. \"explain photosynthesis for class 5\") -- call "
        "search_textbook(query, book_id=...) with no chapter filter, so it "
        "searches the whole book. "
        "(3) the user names BOTH a chapter AND a specific topic within it "
        "(e.g. \"chapter 2, the tools topic\") -- call search_textbook(query, "
        "book_id=..., chapter=...), scoped to that chapter. Do NOT call "
        "get_chapter here -- fetching the whole chapter just to manually find "
        "one topic inside it burns far more tokens than a scoped search "
        "already returns directly. Only fall back to get_chapter in this case "
        "if search_textbook returns nothing useful for that chapter. "
        "search_textbook only covers books that have been semantically "
        "indexed (currently the full published catalog, but get_chapter "
        "remains the complete-coverage fallback for case 1). "
        "The underlying services are free-tier and can take ~20-30s to wake up "
        "from idle -- if a tool call errors saying the service is waking up or "
        "didn't respond in time, simply call the same tool again once; it will "
        "usually succeed on the retry. get_chapter and search_textbook return "
        "real textbook images (a usable `url` + `caption`, not just text). "
        "When a caption looks relevant to what you're explaining, call "
        "view_image(url) first to actually look at it before deciding -- this "
        "lets you confirm it genuinely matches rather than guessing from the "
        "caption alone, and skip ones that don't. For images you confirm are "
        "relevant, embed them in your answer as a markdown image "
        "(![caption](url)), especially for young students who benefit from "
        "seeing the actual textbook picture, not just reading about it. Don't "
        "just report that images exist without showing the relevant ones. "
        "If you generate a downloadable file from this content (e.g. a Word "
        "document, PDF, or slide deck), download and embed the actual image "
        "data in that file wherever relevant, the same way you would in a "
        "chat answer -- don't leave it as a caption-only or text-only file. "
        "If the user asks for a lesson prep sheet / prep material (not a "
        "simulation), use create_prep_sheet -- read that tool's own "
        "description closely before calling it, it has exact, non-negotiable "
        "rules for what each of the 6 buckets must contain. "
        "CLASSROOM PROFILE: before your FIRST call to create_prep_sheet or "
        "create_simulation in a conversation, if you haven't already gathered "
        "one in this same conversation, ask the teacher a short classroom-"
        "profile questionnaire in plain chat (not a tool call) -- phrase "
        "EVERY question as explicit, numbered/lettered options to pick from "
        "(a quick reply, not an essay), never as an open-ended question: "
        "(1) Class size -- a) Under 20  b) 20-40  c) Over 40 (or just give "
        "the number). (2) Real ability level of most students, relative to "
        "the nominal grade -- a) At grade level  b) Below grade level (say "
        "which grade if known, e.g. \"Class 5 on paper, most at Class 2-3\") "
        "c) Mixed levels. (3) Everyday objects for demonstrations -- "
        "a) Available (e.g. a chair, a notebook)  b) Not available. "
        "(4) Movement -- a) Children can move around  b) Seated only. "
        "(5) Textbooks -- a) Each child has their own  b) One shared with "
        "the board. (6) Language -- a) Add Telugu help alongside English  "
        "b) English only. Once answered, treat these as the CLASSROOM "
        "PROFILE for "
        "the rest of THIS conversation and let them shape every subsequent "
        "create_prep_sheet/create_simulation call -- e.g. the real ability "
        "level (not the nominal grade) sets vocabulary/complexity, seated-"
        "only changes what Challenge's PLAY can physically involve, no "
        "individual textbooks means Concept/Challenge can't assume every "
        "child is looking at their own page, and Telugu help means adding "
        "the regional term alongside English where you're confident it's "
        "correct (same rule create_prep_sheet's real_life bucket already "
        "has). Do NOT ask this questionnaire again later in the same "
        "conversation. If the teacher later corrects any part of it with a "
        "plain sentence (e.g. \"actually we don't have a shared textbook "
        "anymore\"), update your working understanding and apply the "
        "correction to anything generated afterward -- no need to re-ask the "
        "full questionnaire. This profile does not carry over to a new "
        "conversation; ask again there."
    ),
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", "8000")),
    stateless_http=True,
)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """Plain health check, separate from the MCP protocol endpoint -- for
    uptime/keep-warm pingers that just need a simple GET to hit."""
    return JSONResponse({"status": "ok"})


@mcp.tool()
def list_books(
    board: str | None = None,
    grade: str | None = None,
    subject: str | None = None,
    language: str | None = None,
) -> list[dict]:
    """List published textbooks, optionally filtered by board/grade/subject/language.

    Use this to find a book's exact book_id from natural-language filters
    (e.g. board="TS SCERT", grade="5", subject="Environmental Studies") before
    calling get_chapter. If this returns more than one match, don't pick one --
    ask the user which board, naming the real options, then call this again
    (or get_chapter directly) once they've told you.
    """
    return tools.list_books(board=board, grade=grade, subject=subject, language=language)


@mcp.tool()
def get_chapter(book_id: str, chapter_number: int) -> dict:
    """Fetch one chapter's full, clean text and image URLs by exact book_id and number.

    Use this when the user wants the WHOLE chapter with no narrower topic
    named (e.g. "give me chapter 2") -- it returns the complete chapter,
    covers every published book, and costs no embedding/search overhead.

    If the user names a specific topic/sub-section WITHIN a chapter (e.g.
    "chapter 2, the tools topic"), prefer search_textbook(query, book_id,
    chapter=...) instead -- it returns just the relevant section at a
    fraction of the token cost of fetching and reading the entire chapter
    yourself. Only use get_chapter in that case as a fallback if the scoped
    search comes back empty.

    The returned `content` has `<img id="...">` placeholders matched by
    `image_id` in the `images` list -- when explaining a part of the chapter
    that has a nearby image, embed that image (markdown: ![caption](url))
    alongside your explanation instead of only using the text.
    """
    return tools.get_chapter(book_id=book_id, chapter_number=chapter_number)


@mcp.tool()
def list_chapters(book_id: str) -> list[dict]:
    """List a book's chapters (number, title, page range) -- no content or images.

    Use this to see what a book covers, or to pick the right chapter_number
    before calling get_chapter, instead of fetching full chapter content (and
    every image) just to find titles.
    """
    return tools.list_chapters(book_id=book_id)


@mcp.tool()
def search_textbook(
    query: str,
    book_id: str | None = None,
    board: str | None = None,
    grade: str | None = None,
    subject: str | None = None,
    language: str | None = None,
    chapter: int | None = None,
    top_k_text: int = 5,
    top_k_images: int = 3,
) -> dict:
    """Semantically search textbook content for a topic/concept.

    Use this whenever the user names a specific topic, even if they ALSO name
    the chapter it's in (e.g. "chapter 2, the tools topic") -- pass `chapter`
    to scope the search to just that chapter instead of searching the whole
    book. This is strictly better than get_chapter whenever a topic is named:
    it returns the relevant section directly, at a fraction of the token cost
    of fetching the whole chapter and reading through it yourself. Only skip
    this and use get_chapter directly when the user wants the ENTIRE chapter
    with no narrower topic in mind.

    Pass board/grade/subject if known, instead of book_id, and this will
    resolve the book_id itself; if resolution is ambiguous, the result's
    `candidate_books` lists the matches instead of guessing -- ask the user to
    narrow it down, or call list_books yourself.

    Only a subset of published books are indexed for search. If this returns
    no useful results for a book/chapter you expect to have content, fall
    back to get_chapter instead.

    The `images` result list has real textbook photos relevant to the query
    (`caption` + `url`) -- embed the relevant ones in your answer as markdown
    images, don't just describe them in words.
    """
    return tools.search_textbook(
        query=query,
        book_id=book_id,
        board=board,
        grade=grade,
        subject=subject,
        language=language,
        chapter=chapter,
        top_k_text=top_k_text,
        top_k_images=top_k_images,
    )


@mcp.tool()
def view_image(url: str) -> Image:
    """Fetch one textbook image's real pixels so you can actually see it.

    Use this before embedding an image whose caption looks relevant, to
    confirm it genuinely matches what you're explaining -- rather than only
    ever trusting the caption text. Pass a `url` exactly as returned by
    get_chapter or search_textbook; other URLs are refused.
    """
    data, mime_type = fetch_image(url)
    image_format = mime_type.split("/")[-1] if "/" in mime_type else "jpeg"
    return Image(data=data, format=image_format)


@mcp.tool()
def create_simulation(html: str) -> dict:
    """Host an interactive HTML/CSS/JS simulation and get back a shareable URL.

    Use this when the user asks for an interactive simulation or demo of a
    concept (e.g. "can you make a simulation of this?"), not a static image
    or diagram. Ground the FACTS/sequence/process in the real textbook
    content already fetched this conversation (get_chapter/search_textbook)
    -- but design the simulation's own visuals and interaction yourself.
    It does NOT need to replicate, resemble, or be built "around" the
    textbook's own images/diagrams/pages -- those are source material for
    correctness, not a visual template to copy. Build whatever visual
    representation (shapes, diagrams, animations, controls) best helps a
    student understand the concept interactively, free of the textbook's
    own illustration style. Write a COMPLETE, self-contained HTML page --
    inline <style>/<script>, no external files -- implementing the
    simulation, and pass it here. It's uploaded as-is; share the returned
    `url` with the user so they can open it in their own browser, where it
    runs live and interactively. Max 300KB; must be a real page (a <html>
    tag), not a fragment.

    If you haven't gathered this conversation's CLASSROOM PROFILE yet (see
    the server-level instructions), ask for it first -- the real ability
    level in particular should set how complex/wordy the simulation is.
    """
    return tools.create_simulation(html=html)


@mcp.tool()
def create_prep_sheet(prep_sheet: PrepSheetRequest) -> dict:
    """Render a 6-bucket lesson prep sheet to a PDF and get back a shareable URL.

    Use this for "create the prep material/prep sheet" requests -- NOT for
    "create a simulation" (use create_simulation for that instead).

    If you haven't gathered this conversation's CLASSROOM PROFILE yet (see
    the server-level instructions), ask for it first -- class size, real
    ability level, resource/seating/textbook/language toggles -- and factor
    it into everything below (e.g. Challenge's PLAY must fit a seated
    classroom if that's what the profile says).

    Before writing any bucket, assemble a SHARED CONTEXT in your own
    reasoning (don't send it as a field -- it just grounds what you write):
    the real textbook excerpt for this topic (from get_chapter/
    search_textbook, already fetched this conversation), the FLOOR
    (weakest-child fallback path, if the user gave one or it's inferable),
    the named misconception for this topic (if any), and -- only if an
    EARLIER topic was already prepped in THIS SAME conversation -- that
    earlier topic's Explore bullets, verbatim, from your own memory of
    generating them. If this is the first topic in the conversation, there
    is no previous Explore; proceed without it (see `refresher` below).

    Then write each bucket as structured fields -- never HTML, never
    inventing facts/numbers/terms the textbook excerpt doesn't contain --
    following these exact rules:

    **refresher** (omit this whole field entirely if there's no previous
    topic in this conversation -- don't send an empty one): exactly 3
    bullets, built ENTIRELY from the previous topic's Explore, introducing
    nothing new. (1) Name the real-life thing the previous Explore pointed
    students to, by name. (2) A genuine check-in on whether they actually
    noticed it -- not an invented question. (3) Turn whatever they noticed
    into the doorway to today's topic.

    **concept** (required): 3 bullets. Every definition/number/term must
    come from the textbook excerpt -- never invented or contradicted. Your
    teaching example may differ from the book's own illustration -- pick a
    SMALL object the teacher can hold and turn in their hand (a cup,
    matchbox, book); NEVER a full-size object like a chair or desk. Bullet 1
    is the easy entry: if a FLOOR exists, that sentence IS bullet 1 --
    don't invent a different easy case. At least one bullet must state the
    MECHANISM, not just the fact (e.g. "the straight edges touch flush, so
    nothing is left over", not just "it fits"). Set `watch` to the named
    misconception as a live if-then ("if a child says/thinks X, the teacher
    does Y") -- a concrete, physical demonstration of the wrong idea
    failing, not a generic "address misconceptions" line. Never demonstrate
    with the same object `challenge` uses below -- if Challenge returns to
    the book's own picture, Concept must use a smaller, different object.

    **real_life** (omit entirely if there's no genuine real-life tie-in for
    this topic): 3 bullets connecting the idea to the children's own world.
    Teacher-led only -- no "ask pairs to...", no group work, no task to go
    do (that belongs in `challenge`). Prefer concrete instances the
    textbook itself names; only invent a local one if the book names none.
    Each bullet names ONE real instance, connects it back to Concept's
    idea, then works it through aloud with the answer stated -- never leave
    a question unresolved. If this region has a common everyday word for
    the object, use it alongside the English term once (e.g. "a matka
    (water pot)") -- ONLY if you are confident it's a real, correct
    regional word; never guess at one. Narrate as shared knowledge everyone
    already has (the village well, the market) -- never "imagine your own
    X at home" (that's `explore`'s job, not this one's).

    **challenge** (required): stage PLAY -> REFLECT -> ACT within the
    bullets. If the textbook excerpt itself names an activity for this
    page (check for activity-tagged content from get_chapter), name the
    challenge in the book's own words and build PLAY/REFLECT/ACT around it.
    If the book sets no task, invent an appropriate grade-level activity
    yourself. PLAY must carry a GENUINE either/or -- a pair actually picks
    one path and the other goes unused, not "do step A then step B"
    dressed up as a choice. If a FLOOR exists, stage it as the easy
    fallback path inside PLAY itself, not a separate ungraded warm-up.
    REFLECT is a 30-second "what worked?" turn-and-tell -- never about
    mistakes. ACT applies the idea to one real problem with the worked
    answer stated in full -- the teacher should never have to compute live
    in front of the class. Use `images` (not `image`) if the book's own
    picture is relevant here.

    **level_set** (required): exactly 3 bullets, every child's independent
    evidence. (1) One clause recapping today's idea in the SAME wording
    `concept` used, then a partner self-check -- if the misconception is
    relevant, phrase the check as a genuine two-option pick (the wrong
    belief gets equal footing, not a yes/no that only ever collects yes).
    (2) A reflection on what was easiest or most interesting today -- never
    on errors. (3) A choice that literally leaves the room: something to
    go notice outside class, framed as an invitation, never homework,
    nothing to write or collect.

    **explore** (required): exactly 3 bullets. Each is a short headline
    plus a detail reporting the TEACHER'S act of telling the class -- every
    detail must start "Tell students that..." or "Tell students to...".
    Never phrase a detail as a direct command to the child (e.g. "Look at a
    chair from above.") -- that reads as a worksheet, not a teacher
    speaking. Tie each point to today's idea, using something the textbook
    itself named where possible. No pair work or discussion staged here --
    that happens in tomorrow's `refresher`. The third bullet must be
    specific and nameable enough for a future Refresher to recall it by
    name -- never a vague "notice things around you."

    Reuse real textbook image URLs from get_chapter/search_textbook where
    they genuinely fit a section -- don't invent URLs. The returned `url`
    points to a real PDF the user can open directly.
    """
    return tools.create_prep_sheet(prep_sheet=prep_sheet)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
