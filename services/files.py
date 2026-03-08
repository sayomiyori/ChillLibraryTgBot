"""
Поиск ссылки на книгу по формату: возвращаем URL (без скачивания).
Проверяем «начинку» файла по первым байтам (название/автор), чтобы отсечь не ту книгу.
"""
import logging
from typing import Optional

from services.book_sources import find_link_any_source
from services.content_check import validate_file_content

logger = logging.getLogger(__name__)

EXTENSION_MAP = {
    "fb2": ["fb2", "FB2"],
    "epub": ["epub", "EPUB", "epub3"],
    "pdf": ["pdf", "PDF"],
    "txt": ["txt", "TXT", "doc", "DOC"],
    "audio": ["mp3", "m4b", "MP3", "M4B", "mp4"],
}
FILE_EXTENSION = {k: v[0] for k, v in EXTENSION_MAP.items()}


async def find_download_link(
    book_title: str,
    author: str,
    fmt: str,
    book_id: Optional[str] = None,
) -> Optional[tuple[str, str]]:
    """
    Найти прямую ссылку на файл книги в нужном формате.
    Проверяется содержимое (название/автор в начале файла).
    Возвращает (url, source_name) или None.
    """
    fmt_lower = (fmt or "").strip().lower()
    if fmt_lower not in EXTENSION_MAP:
        logger.warning("Unknown format: %s", fmt)
        return None
    query = ((book_title or "") + " " + (author or "")).strip()
    if len(query) < 2:
        return None

    # 1) Google Books — прямая ссылка на PDF/EPUB (если есть book_id)
    if book_id and fmt_lower in ("epub", "pdf"):
        from services.books_api import get_book_by_id
        book = await get_book_by_id(book_id)
        if book:
            url = book.get("download_epub") if fmt_lower == "epub" else book.get("download_pdf")
            if url and isinstance(url, str) and url.startswith("http"):
                if await validate_file_content(url, book_title or "", author or "", fmt):
                    return (url, "Google Books")

    # 2) Площадки по формату: параллельный поиск URL + проверка начинки
    return await find_link_any_source(
        book_title or "",
        author or "",
        fmt,
        validate_content=validate_file_content,
    )
