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
        "already have the exact book_id) then get_chapter for the full, "
        "authoritative text. If list_books returns MORE THAN ONE match for what "
        "the user asked (e.g. once multiple state boards publish the same "
        "grade/subject), do not guess which one they meant and do not call "
        "get_chapter yet -- ask the user to clarify, naming the real options "
        "(e.g. \"I found this for Telangana SCERT, AP SCERT, and CBSE -- which "
        "one does your school follow?\"), then proceed once they answer. Only "
        "skip asking when there's exactly one match, or the user already named "
        "the board. Call list_chapters first "
        "if you need to see what a book covers, or to pick the right chapter "
        "number, without paying the cost of fetching full content just to see "
        "titles. Only use search_textbook "
        "when the user asks about a topic without naming where to find it -- it "
        "only covers a subset of books that have been semantically indexed. "
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
        "simulation), call create_prep_sheet with the 6-bucket content "
        "(Refresher, Concept, Real Life, Challenge, Level Set, Explore) drawn "
        "from the textbook content already fetched in this conversation -- "
        "write the content yourself as structured fields (title/minutes/"
        "bullets/images/watch), never as HTML. Only include `refresher` if an "
        "earlier lesson was actually discussed earlier in this same "
        "conversation (use your own memory of it -- there is no tool for "
        "this); omit it entirely for a first lesson. Only include `real_life` "
        "if the topic has a genuine real-life tie-in. Reuse real image URLs "
        "from get_chapter/search_textbook where they fit a section, don't "
        "invent image URLs."
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

    Prefer this over search_textbook whenever the user names a specific
    textbook/chapter directly -- it returns the complete chapter, covers every
    published book, and costs no embedding/search overhead.

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

    Use this only when the user asks about a topic without naming an exact
    chapter. Pass board/grade/subject if known, instead of book_id, and this
    will resolve the book_id itself; if resolution is ambiguous, the result's
    `candidate_books` lists the matches instead of guessing -- ask the user to
    narrow it down, or call list_books yourself.

    Only a subset of published books are indexed for search. If this returns
    no useful results for a book you expect to have content, fall back to
    list_books + get_chapter instead.

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
    or diagram. Write a COMPLETE, self-contained HTML page -- inline
    <style>/<script>, no external files -- implementing the simulation, and
    pass it here. It's uploaded as-is; share the returned `url` with the user
    so they can open it in their own browser, where it runs live and
    interactively. Max 300KB; must be a real page (a <html> tag), not a
    fragment.
    """
    return tools.create_simulation(html=html)


@mcp.tool()
def create_prep_sheet(prep_sheet: PrepSheetRequest) -> dict:
    """Render a 6-bucket lesson prep sheet to a PDF and get back a shareable URL.

    Use this for "create the prep material/prep sheet" requests -- NOT for
    "create a simulation" (use create_simulation for that instead). Pass
    structured content, not HTML: `topic`, optional one-line `goal`/`floor`,
    and the 6 buckets -- `refresher` (only if an earlier lesson in this
    conversation needs recapping, omit otherwise), `concept` (required),
    `real_life` (only if there's a genuine tie-in, omit otherwise),
    `challenge`, `level_set`, `explore` (all required). Each bucket is
    {title, minutes?, bullets[], image? (one) or images? (several), watch?
    (a likely misconception + one-line fix)}. Reuse real textbook image URLs
    from get_chapter/search_textbook where relevant -- don't invent URLs.
    The returned `url` points to a real PDF the user can open directly.
    """
    return tools.create_prep_sheet(prep_sheet=prep_sheet)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
