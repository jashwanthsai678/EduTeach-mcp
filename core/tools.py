"""Protocol-agnostic tool implementations shared by the MCP server and (later)
the REST/OpenAPI wrapper for ChatGPT Actions.

Routing rule this module encodes: when the caller already knows exactly which
book/chapter they want, go straight to the catalog API (get_chapter) -- full,
clean content, no embedding cost, works for all 8 published books. Semantic
search (search_textbook) is the fallback for "I don't know which chapter has
this topic" queries, and only covers the subset of books currently indexed
in Qdrant.
"""

from core import catalog_client, retrieval_client, simulation_client
from core.prep_sheet_schema import PrepSheetRequest


def list_books(
    board: str | None = None,
    grade: str | None = None,
    subject: str | None = None,
    language: str | None = None,
) -> list[dict]:
    """List published textbooks, optionally filtered by board/grade/subject/language.

    Use this first when you need a book_id but only know it in natural language
    (e.g. "Class 5 EVS") -- match the returned book_id against what the user said,
    then pass it to get_chapter.
    """
    return catalog_client.list_books(board=board, grade=grade, subject=subject, language=language)


def get_chapter(book_id: str, chapter_number: int) -> dict:
    """Fetch one chapter's full, clean text + image URLs by exact book_id and number.

    Use this whenever the user names a specific textbook/chapter directly.
    It returns the complete chapter, not a fuzzy top-k slice -- prefer this over
    search_textbook whenever you already know where to look.
    """
    return catalog_client.get_chapter(book_id=book_id, chapter_number=chapter_number)


def list_chapters(book_id: str) -> list[dict]:
    """List a book's published chapters (number, title, page range) -- no content or images.

    Use this to see what a book covers, or to pick the right chapter_number
    before calling get_chapter, without paying the cost of fetching full
    chapter content (and every image) just to see titles.
    """
    return catalog_client.list_chapters(book_id=book_id)


def _resolve_book_id(
    board: str | None, grade: str | None, subject: str | None, language: str | None
) -> tuple[str | None, list[dict]]:
    """Best-effort book_id lookup from natural-language filters.

    Returns (book_id, candidates). book_id is set only when exactly one book
    matches; otherwise the caller gets the candidate list back to disambiguate
    instead of silently guessing.
    """
    if not any([board, grade, subject, language]):
        return None, []
    matches = catalog_client.list_books(board=board, grade=grade, subject=subject, language=language)
    if len(matches) == 1:
        return matches[0]["book_id"], matches
    return None, matches


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
    """Semantic search for a topic/concept across indexed textbook content.

    Use this when the user asks about a topic without naming an exact chapter
    (e.g. "explain photosynthesis for class 5"). If board/grade/subject are
    given instead of book_id, this resolves them to a book_id first; if that
    resolution is ambiguous, the result includes `candidate_books` instead of
    search results so the caller can ask the user to narrow it down or call
    list_books itself.

    Note: only a subset of published books are indexed for semantic search.
    If this returns no results for a book you expect to have content, fall
    back to list_chapters + get_chapter instead.
    """
    resolved_book_id = book_id
    candidates: list[dict] = []
    if resolved_book_id is None:
        resolved_book_id, candidates = _resolve_book_id(board, grade, subject, language)
        if resolved_book_id is None and candidates:
            return {
                "ambiguous": True,
                "candidate_books": candidates,
                "text": [],
                "images": [],
            }

    result = retrieval_client.retrieve_content(
        query=query,
        book_id=resolved_book_id,
        chapter=chapter,
        top_k_text=top_k_text,
        top_k_images=top_k_images,
    )
    result["ambiguous"] = False
    result["resolved_book_id"] = resolved_book_id
    return result


def create_simulation(html: str) -> dict:
    """Host a self-contained interactive HTML/CSS/JS page and get back a public URL.

    Use this when the user asks for an interactive simulation/demo of a concept
    (not a static image). Write a complete, self-contained HTML page (inline
    <style>/<script>, no external file dependencies) and pass it here -- it
    gets uploaded as-is and the returned url can be shared directly with the
    user to open in their own browser, where it runs live.
    """
    return simulation_client.create_simulation(html=html)


def create_prep_sheet(prep_sheet: PrepSheetRequest) -> dict:
    """Render the 6-bucket lesson prep sheet to a PDF and get back a public URL.

    Use this when the user asks for a prep sheet / lesson-prep material (not a
    simulation). Unlike create_simulation, this doesn't take raw HTML -- pass
    the structured content (topic, goal, floor, and each bucket's title/
    minutes/bullets/images/watch-for) and the service lays it out using
    EduTeach's real prep-sheet design.
    """
    return simulation_client.create_prep_sheet(
        data=prep_sheet.model_dump(exclude_none=True)
    )
