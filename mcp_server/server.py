"""Remote MCP server exposing EduTeach's published textbook content to Claude.

Three tools, mirroring core/tools.py:
  - list_books       : discover a book_id from board/grade/subject/language
  - get_chapter      : exact, full-content lookup once the book/chapter is known
  - search_textbook  : semantic search for a topic when the exact location isn't known

Run locally:   python -m mcp_server.server
Deployed:      streamable-http transport, bound to 0.0.0.0:$PORT (see Dockerfile)
"""

import os

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from core import tools

mcp = FastMCP(
    name="eduteach-textbook-connector",
    instructions=(
        "Tools for grounding answers in real, published school-textbook content "
        "(TS SCERT boards so far). If the user names a specific textbook/chapter, "
        "call list_books (if you don't already have the exact book_id) then "
        "get_chapter for the full, authoritative text. Only use search_textbook "
        "when the user asks about a topic without naming where to find it -- it "
        "only covers a subset of books that have been semantically indexed. "
        "The underlying services are free-tier and can take ~20-30s to wake up "
        "from idle -- if a tool call errors saying the service is waking up or "
        "didn't respond in time, simply call the same tool again once; it will "
        "usually succeed on the retry."
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
    calling get_chapter.
    """
    return tools.list_books(board=board, grade=grade, subject=subject, language=language)


@mcp.tool()
def get_chapter(book_id: str, chapter_number: int) -> dict:
    """Fetch one chapter's full, clean text and image URLs by exact book_id and number.

    Prefer this over search_textbook whenever the user names a specific
    textbook/chapter directly -- it returns the complete chapter, covers every
    published book, and costs no embedding/search overhead.
    """
    return tools.get_chapter(book_id=book_id, chapter_number=chapter_number)


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


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
