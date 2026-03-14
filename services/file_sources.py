"""
Рабочие источники по форматам: FB2, EPUB, TXT, PDF, DJVU, Аудио.
Браузерные заголовки в каждом запросе, quote(query, safe="") для кириллицы.
Источники для СНГ: Litres, Mybook, Rusneb, Libking, Fictionbook, Coollib и др.
"""
import asyncio
import logging
import time
from typing import Any, Callable, Optional
from urllib.parse import quote

import aiohttp
from bs4 import BeautifulSoup

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None  # fallback: проверка только по word_hits

from config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

TIMEOUT = aiohttp.ClientTimeout(connect=6, total=14)


async def _fetch_html(
    session: aiohttp.ClientSession, url: str
) -> tuple[Optional[str], int, Optional[str]]:
    """
    Возвращает (html, status_code, error).
    status=200 и html не None — успех; иначе status (403, 404 и т.д.) или 0 при исключении, error — текст ошибки.
    """
    try:
        async with session.get(url, headers=BROWSER_HEADERS, timeout=TIMEOUT) as resp:
            status = resp.status
            if status != 200:
                return (None, status, None)
            text = await resp.text(encoding="utf-8", errors="replace")
            return (text, status, None)
    except asyncio.TimeoutError as e:
        return (None, 0, f"timeout: {e}")
    except aiohttp.ClientError as e:
        return (None, 0, f"client: {e}")
    except Exception as e:
        return (None, 0, f"{type(e).__name__}: {e}")


async def _fetch_json(session: aiohttp.ClientSession, url: str) -> Optional[dict]:
    try:
        async with session.get(url, headers=BROWSER_HEADERS, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return await resp.json()
    except Exception as e:
        logger.debug("fetch_json %s: %s", url[:60], e)
        return None


# ─── УНИВЕРСАЛЬНЫЙ ПАРСЕР (СНГ, без VPN) ─────────────────────────────────
# Litres убран из поиска файлов (403, блокирует ботов); остаётся только в кнопке «Купить»
SOURCES_CONFIG: dict[str, dict[str, Any]] = {
    "mybook": {
        "name": "mybook",
        "url": "https://mybook.ru/search/?q={query}",
        "selectors": [
            "a[href*='/author/'][href*='/read/']",
            "a[href^='/author/'][href*='/read/']",
        ],
        "base_url": "https://mybook.ru",
        "formats": ["FB2", "EPUB"],
    },
    "rusneb": {
        "name": "rusneb",
        "url": "https://rusneb.ru/search/?q={query}",
        "selectors": [
            "a.search-list__item_link",
            "a.search-result__content-main-read-button",
            "a[href^='/catalog/'].search-list__item_link",
        ],
        "base_url": "https://rusneb.ru",
        "formats": ["FB2", "EPUB", "TXT", "PDF", "DJVU"],
    },
    "libking": {
        "name": "libking",
        "url": "https://libking.ru/search/?q={query}",
        "selectors": ["a.mov-t", ".book-title a", "h3 a", ".title a"],
        "base_url": "https://libking.ru",
        "formats": ["FB2", "EPUB", "TXT"],
    },
    # fictionbook — 404, URL поиска сменился; вернуть при наличии актуального URL
    # "fictionbook": {
    #     "name": "fictionbook",
    #     "url": "https://fictionbook.ru/search/?q={query}",
    #     "selectors": [".book_title a", "h2 a", ".title a"],
    #     "base_url": "https://fictionbook.ru",
    #     "formats": ["FB2"],
    # },
    "loveread": {
        "name": "loveread",
        "url": "https://loveread.ec/search.php?searchTXT={query}",
        "selectors": [".blRead a", ".blockBook .blRead a", ".name_book a", "h3 a", ".title a"],
        "base_url": "https://loveread.ec",
        "formats": ["FB2", "EPUB", "TXT"],
    },
    # coollib — 404, поиск через https://coollib.net/b (форма с полями); вернуть при актуальном URL
    # "coollib": {
    #     "name": "coollib",
    #     "url": "https://coollib.net/search?q={query}",
    #     "selectors": [".book-title a", "h3 a", ".title a"],
    #     "base_url": "https://coollib.net",
    #     "formats": ["FB2", "EPUB", "TXT"],
    # },
    "readli": {
        "name": "readli",
        "url": "https://readli.net/search/?q={query}",
        "selectors": [".book__link", ".book-item__link", "h4.book__title a", ".book__title a", "h2 a"],
        "base_url": "https://readli.net",
        "formats": ["FB2", "EPUB", "TXT"],
    },
    # online-knigi — 403, сайт блокирует ботов; раскомментировать после проверки с новыми headers
    # "online-knigi": {
    #     "name": "online-knigi",
    #     "url": "https://online-knigi.com/search?query={query}",
    #     "selectors": [".book-title a", ".title a", "h2 a", "h3 a", ".book_title a"],
    #     "base_url": "https://online-knigi.com",
    #     "formats": ["FB2", "EPUB", "TXT"],
    # },
    "elib": {
        "name": "elib",
        "url": "https://elib.rsl.ru/search?q={query}",
        "selectors": [".search-result a", ".title a", "a[href*='/view/']"],
        "base_url": "https://elib.rsl.ru",
        "formats": ["PDF", "DJVU"],
    },
    "elibrary": {
        "name": "elibrary",
        "url": "https://elibrary.ru/query_results.asp?query={query}",
        "selectors": [".bold a", "a[href*='item.asp']"],
        "base_url": "https://elibrary.ru",
        "formats": ["PDF", "DJVU"],
    },
    "biblioclub": {
        "name": "biblioclub",
        "url": "https://biblioclub.ru/index.php?page=book_search&query={query}",
        "selectors": [".book-title a", "a[href*='/book/']"],
        "base_url": "https://biblioclub.ru",
        "formats": ["PDF", "DJVU"],
    },
    "mave": {
        "name": "mave",
        "url": "https://mave.digital/search?q={query}",
        "selectors": [".book-title a", ".title a", "a[href*='/audiobook/']", "a[href*='/book/']"],
        "base_url": "https://mave.digital",
        "formats": ["Аудио"],
    },
    "zvukiknig": {
        "name": "zvukiknig",
        "url": "https://zvukiknig.cc/search?q={query}",
        "selectors": [
            ".book-title a", "h2.title a", "h3 a",
            ".title a", ".name a",
            "[class*='book'] a", "[class*='title'] a",
        ],
        "base_url": "https://zvukiknig.cc",
        "formats": ["Аудио"],
    },
    "audiobazar": {
        "name": "audiobazar",
        "url": "https://audiobazar.ru/search/?q={query}",
        "selectors": [
            ".product-title a", "h2 a", ".title a",
            "h3 a", ".name a",
            "[class*='product'] a", "[class*='title'] a",
        ],
        "base_url": "https://audiobazar.ru",
        "formats": ["Аудио"],
    },
    "libbox": {
        "name": "libbox",
        "url": "https://libbox.ru/search/?q={query}",
        "selectors": [".book__name a", "h2 a", "a[href*='/book/']", "[class*='book'] a"],
        "base_url": "https://libbox.ru",
        "formats": ["Аудио"],
    },
}


async def _parse_source(
    session: aiohttp.ClientSession,
    config: dict[str, Any],
    source_name: str,
    query: str,
) -> Optional[str]:
    """Парсит одну запись из SOURCES_CONFIG."""
    url = config["url"].replace("{query}", quote(query, safe=""))
    html, status, err = await _fetch_html(session, url)
    if not html:
        status_str = str(status) if status else "—"
        err_str = (err or "—").strip()[:80]
        logger.warning(
            "[%s] страница не загрузилась | status=%s | %s | %s",
            source_name,
            status_str,
            err_str,
            url[:50],
        )
        return None
    soup = BeautifulSoup(html, "lxml")
    base = config.get("base_url", "")
    query_lower = query.lower()
    query_words = query_lower.split()
    skip_in_href = ("login", "register", "logout", "#", "javascript", "mailto")
    for selector in config.get("selectors", []):
        elements = soup.select(selector)
        if not elements:
            logger.warning("[%s] selector '%s' не найден", source_name, selector)
            continue
        for el in elements:
            href = el.get("href", "").strip()
            text = (el.get_text(strip=True) or "").lower()
            if not href or not text:
                continue
            if any(s in href.lower() for s in skip_in_href):
                continue
            if "mybook" in config.get("base_url", ""):
                parts = [p for p in href.split("/") if p]
                if len(parts) < 3:
                    continue
            word_hits = sum(1 for w in query_words if len(w) > 1 and w in text)
            if fuzz is not None:
                score = fuzz.partial_ratio(query_lower, text)
            else:
                score = 100.0 if (query_lower in text or word_hits >= 1) else 0.0
            if score >= 60 or word_hits >= 1:
                if not href.startswith("http"):
                    href = base.rstrip("/") + "/" + href.lstrip("/")
                logger.info("[%s] селектор '%s' score=%s -> %s", source_name, selector, score, href[:60])
                return href
        logger.warning(
            "[%s] selector '%s' найден, но ни одна ссылка не подошла по тексту",
            source_name,
            selector,
        )
    all_links = soup.find_all("a", href=True)
    logger.info("[%s] всего ссылок на странице: %s", source_name, len(all_links))
    for a in all_links[:20]:
        logger.info("[%s]   href='%s' text='%s'", source_name, a.get("href", "")[:50], (a.get_text(strip=True) or "")[:30])
    return None


async def _smart_parse(
    session: aiohttp.ClientSession,
    url: str,
    query: str,
    base_url: str,
    source_name: str,
) -> Optional[str]:
    """Поиск ссылки по тексту (60% слов запроса) или по URL-паттернам книжных сайтов."""
    html, status, err = await _fetch_html(session, url)
    if not html:
        status_str = str(status) if status else "—"
        logger.warning(
            "[%s] smart_parse: нет HTML | status=%s | %s",
            source_name,
            status_str,
            (err or "—")[:60],
        )
        return None
    soup = BeautifulSoup(html, "lxml")
    query_lower = query.lower()
    title_words = [w for w in query_lower.split() if len(w) > 1]
    skip_in_href = ("login", "register", "logout", "cart", "mailto:", "javascript:", "#", "policy")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(s in href.lower() for s in skip_in_href):
            continue
        text = (a.get_text(strip=True) or "").lower()
        if not title_words:
            continue
        matches = sum(1 for w in title_words if w in text)
        if matches >= len(title_words) * 0.6:
            word_hits = sum(1 for w in title_words if w in text)
            if fuzz is not None:
                score = fuzz.partial_ratio(query_lower, text)
            else:
                score = 100.0 if (query_lower in text or word_hits >= 1) else 0.0
            if score >= 60 or word_hits >= 1:
                if not href.startswith("http"):
                    href = base_url.rstrip("/") + "/" + href.lstrip("/")
                logger.info("[%s] найдено по тексту score=%s: '%s' -> %s", source_name, score, text[:40], href[:60])
                return href
    book_patterns = ("/book/", "/books/", "/read/", "/fiction/", "/lib/", "/b/", "/kniga/", "/chitat/", "/catalog/")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(p in href for p in book_patterns):
            text = (a.get_text(strip=True) or "").lower()
            word_hits = sum(1 for w in title_words if w in text) if title_words else 0
            if fuzz is not None:
                score = fuzz.partial_ratio(query_lower, text)
            else:
                score = 100.0 if (query_lower in text or word_hits >= 1) else 0.0
            if score >= 60 or word_hits >= 1:
                if not href.startswith("http"):
                    href = base_url.rstrip("/") + "/" + href.lstrip("/")
                logger.info("[%s] найдено по URL-паттерну score=%s: %s", source_name, score, href[:60])
                return href
    return None


async def search_universal(
    session: aiohttp.ClientSession,
    query: str,
    format: str,
) -> Optional[str]:
    """Поиск по SOURCES_CONFIG: сначала селекторы, при неудаче — умный поиск по тексту/URL."""
    fmt = (format or "").strip().upper()
    if fmt == "AUDIO":
        fmt = "Аудио"
    sources = [
        (name, cfg)
        for name, cfg in SOURCES_CONFIG.items()
        if fmt in cfg.get("formats", [])
    ]
    if not sources:
        return None

    async def try_source(name: str, cfg: dict[str, Any]) -> Optional[str]:
        result = await _parse_source(session, cfg, name, query)
        if result:
            return result
        url = cfg["url"].replace("{query}", quote(query, safe=""))
        return await _smart_parse(session, url, query, cfg.get("base_url", ""), name)

    tasks = [asyncio.create_task(try_source(name, cfg)) for name, cfg in sources]
    try:
        async for coro in asyncio.as_completed(tasks):
            result = await coro
            if result:
                for t in tasks:
                    if not t.done():
                        t.cancel()
                return result
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
    return None


# ─── BOOKMATE (API) ─────────────────────────────────
async def search_bookmate(session: aiohttp.ClientSession, query: str) -> Optional[str]:
    """Bookmate API — поиск книг, возвращает ссылку на первую подходящую книгу."""
    q = quote(query, safe="")
    url = f"https://api.bookmate.com/api/v5/search?query={q}&per_page=5"
    data = await _fetch_json(session, url)
    if not data:
        return None
    results = data.get("response") or data.get("results") or []
    if not results:
        return None
    first = results[0] if isinstance(results, list) else results
    if isinstance(first, dict):
        link = first.get("url") or first.get("link") or first.get("id")
        if link and isinstance(link, str) and link.startswith("http"):
            logger.info("[bookmate] -> OK %s", link[:60])
            return link
        uuid = first.get("uuid") or first.get("id")
        if uuid:
            return f"https://bookmate.com/books/{uuid}"
    return None


# ─── Z-LIB ─────────────────────────────────────────
async def search_zlib(
    session: aiohttp.ClientSession,
    query: str,
    format: str,
) -> Optional[str]:
    fmt = (format or "pdf").lower()
    query_encoded = quote(query, safe="")
    url = f"https://z-lib.gs/search?q={query_encoded}&extension={fmt}"
    html, status, err = await _fetch_html(session, url)
    if not html:
        logger.warning(
            "[%s] z-lib.gs → нет ответа | status=%s | %s",
            fmt.upper(),
            status,
            (err or "—")[:60],
        )
        return None
    soup = BeautifulSoup(html, "lxml")
    selectors = [
        "h3.book-title a",
        ".book-item__title a",
        ".title a",
        "z-bookcard",
        "[itemprop='name'] a",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get("href"):
            href = el["href"]
            if not href.startswith("http"):
                href = "https://z-lib.gs" + href
            logger.info("[%s] z-lib.gs найдено: %s", fmt.upper(), href[:60])
            return href
    for a in soup.find_all("a", href=True):
        if "/book/" in a["href"]:
            href = a["href"]
            if not href.startswith("http"):
                href = "https://z-lib.gs" + href
            logger.info("[%s] z-lib.gs найдено: %s", fmt.upper(), href[:60])
            return href
    logger.warning("[%s] z-lib.gs → не найдено для '%s'", fmt.upper(), query[:40])
    return None


# ─── ARCHIVE.ORG ───────────────────────────────────
async def search_archive_org(
    session: aiohttp.ClientSession,
    query: str,
    format: str,
) -> Optional[str]:
    fmt_map = {"djvu": "DjVu", "pdf": "PDF", "epub": "EPUB", "txt": "TXT", "fb2": "FB2"}
    fmt = fmt_map.get((format or "").lower(), (format or "").upper())
    query_encoded = quote(query, safe="")
    api_url = (
        f"https://archive.org/advancedsearch.php"
        f"?q={query_encoded}+AND+mediatype:texts"
        f"&fl[]=identifier,title,format"
        f"&output=json&rows=10"
    )
    data = await _fetch_json(session, api_url)
    if not data:
        logger.warning("[%s] archive.org → нет ответа", format)
        return None
    docs = data.get("response", {}).get("docs", [])
    for doc in docs:
        identifier = doc.get("identifier", "")
        if not identifier:
            continue
        meta_url = f"https://archive.org/metadata/{identifier}"
        meta = await _fetch_json(session, meta_url)
        if not meta:
            continue
        files = meta.get("files") or []
        for f in files:
            fname = f.get("name", "")
            if fname.lower().endswith(f".{(format or '').lower()}"):
                fname_enc = quote(fname, safe="")
                link = f"https://archive.org/download/{identifier}/{fname_enc}"
                logger.info("[%s] archive.org найдено: %s", format, link[:60])
                return link
    logger.warning("[%s] archive.org → не найдено", format)
    return None


# ─── OPEN LIBRARY (FB2/EPUB/PDF) ───────────────────
async def search_openlibrary(
    session: aiohttp.ClientSession,
    query: str,
    format: str,
) -> Optional[str]:
    query_encoded = quote(query, safe="")
    api = f"https://openlibrary.org/search.json?q={query_encoded}&limit=5"
    data = await _fetch_json(session, api)
    if not data:
        return None
    for doc in data.get("docs", []):
        for key in (doc.get("edition_key") or [])[:3]:
            edition_url = f"https://openlibrary.org/books/{key}.json"
            edition = await _fetch_json(session, edition_url)
            if not edition:
                continue
            formats_available = edition.get("formats", {}) or {}
            if (format or "").lower() in str(formats_available).lower():
                link = f"https://openlibrary.org/books/{key}"
                logger.info("[%s] openlibrary найдено: %s", format, link[:60])
                return link
    return None


# ─── GUTENBERG (EPUB/TXT) ───────────────────────────
async def search_gutenberg(session: aiohttp.ClientSession, query: str) -> Optional[str]:
    query_encoded = quote(query, safe="")
    api = f"https://www.gutenberg.org/ebooks/search/?query={query_encoded}&submit_search=Go"
    html, status, err = await _fetch_html(session, api)
    if not html:
        logger.warning(
            "[EPUB] gutenberg → нет ответа | status=%s | %s",
            status,
            (err or "—")[:60],
        )
        return None
    soup = BeautifulSoup(html, "lxml")
    book_link = soup.select_one("li.booklink a, .result-set li a")
    if not book_link or not book_link.get("href"):
        return None
    href = book_link["href"]
    book_id = href.rstrip("/").split("/")[-1]
    if not book_id.isdigit():
        return None
    epub_url = f"https://www.gutenberg.org/ebooks/{book_id}.epub.images"
    logger.info("[EPUB] gutenberg найдено: %s", epub_url)
    return epub_url


# ─── KNIGAVUHE (Аудио) ──────────────────────────────
async def search_knigavuhe(session: aiohttp.ClientSession, query: str) -> Optional[str]:
    query_encoded = quote(query, safe="")
    url = f"https://knigavuhe.org/search/?q={query_encoded}"
    html, status, err = await _fetch_html(session, url)
    if not html:
        logger.warning(
            "[Аудио] knigavuhe → нет ответа | status=%s | %s",
            status,
            (err or "—")[:60],
        )
        return None
    soup = BeautifulSoup(html, "lxml")
    for sel in (".kniga-title a", ".book-title a", ".search-result a", "h2 a", "h3 a"):
        el = soup.select_one(sel)
        if el and el.get("href"):
            href = el["href"]
            if not href.startswith("http"):
                href = "https://knigavuhe.org" + href
            logger.info("[Аудио] knigavuhe найдено: %s", href[:60])
            return href
    return None


# ─── AKNIGA (Аудио) ─────────────────────────────────
async def search_akniga(session: aiohttp.ClientSession, query: str) -> Optional[str]:
    query_encoded = quote(query, safe="")
    url = f"https://akniga.org/search/q/{query_encoded}/"
    html, status, err = await _fetch_html(session, url)
    if not html:
        logger.warning(
            "[Аудио] akniga → нет ответа | status=%s | %s",
            status,
            (err or "—")[:60],
        )
        return None
    soup = BeautifulSoup(html, "lxml")
    el = soup.select_one(".desc--title a, .book-title a, h2.title a")
    if el and el.get("href"):
        href = el["href"]
        if not href.startswith("http"):
            href = "https://akniga.org" + href
        logger.info("[Аудио] akniga найдено: %s", href[:60])
        return href
    return None


# ─── LIBRIVOX (Аудио, английские книги) ─────────────
async def search_librivox(session: aiohttp.ClientSession, query: str) -> Optional[str]:
    query_encoded = quote(query, safe="")
    api = f"https://librivox.org/api/feed/audiobooks?title={query_encoded}&format=json"
    data = await _fetch_json(session, api)
    if not data:
        return None
    books = data.get("books", [])
    if books:
        url = books[0].get("url_zip_file") or books[0].get("url_rss_feed")
        if url:
            logger.info("[Аудио] librivox найдено: %s", url[:60])
            return url
    return None


# ─── GOOGLE BOOKS (PDF) ─────────────────────────────
async def search_google_books(session: aiohttp.ClientSession, query: str) -> Optional[str]:
    if not GOOGLE_API_KEY:
        return None
    query_encoded = quote(query, safe="")
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {"q": query, "key": GOOGLE_API_KEY, "maxResults": 5}
    try:
        async with session.get(url, params=params, headers=BROWSER_HEADERS, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
    except Exception:
        return None
    for item in (data.get("items") or [])[:3]:
        acc = (item.get("accessInfo") or {})
        pdf = acc.get("pdf") or {}
        link = pdf.get("acsTokenLink") or pdf.get("downloadLink")
        if link and isinstance(link, str) and link.startswith("http"):
            logger.info("[PDF] Google Books найдено: %s", link[:60])
            return link
    return None


# ─── FORMAT_SOURCES: (name, fn(session, query) -> str|None) ─────────────────
def _mk_fb2(s: Any, q: str) -> Any:
    return search_zlib(s, q, "fb2")


def _mk_universal_fb2(s: Any, q: str) -> Any:
    return search_universal(s, q, "FB2")


def _mk_universal_epub(s: Any, q: str) -> Any:
    return search_universal(s, q, "EPUB")


def _mk_universal_txt(s: Any, q: str) -> Any:
    return search_universal(s, q, "TXT")


def _mk_universal_pdf(s: Any, q: str) -> Any:
    return search_universal(s, q, "PDF")


def _mk_universal_djvu(s: Any, q: str) -> Any:
    return search_universal(s, q, "DJVU")


def _mk_universal_audio(s: Any, q: str) -> Any:
    return search_universal(s, q, "Аудио")


def _mk_archive_fb2(s: Any, q: str) -> Any:
    return search_archive_org(s, q, "FB2")


def _mk_epub_zlib(s: Any, q: str) -> Any:
    return search_zlib(s, q, "epub")


def _mk_epub_archive(s: Any, q: str) -> Any:
    return search_archive_org(s, q, "EPUB")


def _mk_txt_zlib(s: Any, q: str) -> Any:
    return search_zlib(s, q, "txt")


def _mk_txt_archive(s: Any, q: str) -> Any:
    return search_archive_org(s, q, "TXT")


def _mk_pdf_google(s: Any, q: str) -> Any:
    return search_google_books(s, q)


def _mk_pdf_zlib(s: Any, q: str) -> Any:
    return search_zlib(s, q, "pdf")


def _mk_pdf_archive(s: Any, q: str) -> Any:
    return search_archive_org(s, q, "PDF")


def _mk_djvu_archive(s: Any, q: str) -> Any:
    return search_archive_org(s, q, "DJVU")


def _mk_djvu_zlib(s: Any, q: str) -> Any:
    return search_zlib(s, q, "djvu")


FORMAT_SOURCES: dict[str, list[tuple[str, Callable[[Any, str], Any]]]] = {
    "fb2": [
        ("z-lib.gs", _mk_fb2),
        ("universal", _mk_universal_fb2),
        ("bookmate", search_bookmate),
        ("archive.org", _mk_archive_fb2),
    ],
    "epub": [
        ("z-lib.gs", _mk_epub_zlib),
        ("gutenberg", search_gutenberg),
        ("universal", _mk_universal_epub),
        ("bookmate", search_bookmate),
        ("archive.org", _mk_epub_archive),
    ],
    "txt": [
        ("z-lib.gs", _mk_txt_zlib),
        ("universal", _mk_universal_txt),
        ("bookmate", search_bookmate),
        ("archive.org", _mk_txt_archive),
    ],
    "pdf": [
        ("Google Books", _mk_pdf_google),
        ("z-lib.gs", _mk_pdf_zlib),
        ("universal", _mk_universal_pdf),
        ("archive.org", _mk_pdf_archive),
    ],
    "djvu": [
        ("archive.org", _mk_djvu_archive),
        ("z-lib.gs", _mk_djvu_zlib),
        ("universal", _mk_universal_djvu),
    ],
    "audio": [
        ("knigavuhe", search_knigavuhe),
        ("akniga", search_akniga),
        ("universal", _mk_universal_audio),
        ("librivox", search_librivox),
    ],
}

# Только незаблокированные в РФ/СНГ источники (без прокси): Litres, Mybook, Rusneb, Coollib и др.
SAFE_SOURCES: dict[str, list[tuple[str, Callable[[Any, str], Any]]]] = {
    "fb2": [
        ("universal", _mk_universal_fb2),
        ("bookmate", search_bookmate),
        ("archive.org", _mk_archive_fb2),
    ],
    "epub": [
        ("gutenberg", search_gutenberg),
        ("universal", _mk_universal_epub),
        ("bookmate", search_bookmate),
        ("archive.org", _mk_epub_archive),
    ],
    "txt": [
        ("universal", _mk_universal_txt),
        ("bookmate", search_bookmate),
        ("archive.org", _mk_txt_archive),
        ("gutenberg", search_gutenberg),
    ],
    "pdf": [
        ("Google Books", _mk_pdf_google),
        ("universal", _mk_universal_pdf),
        ("archive.org", _mk_pdf_archive),
    ],
    "djvu": [
        ("archive.org", _mk_djvu_archive),
        ("universal", _mk_universal_djvu),
    ],
    "audio": [
        ("librivox", search_librivox),
        ("knigavuhe", search_knigavuhe),
        ("universal", _mk_universal_audio),
    ],
}


def _query_ru(title: str, author: str) -> str:
    return f"{title or ''} {author or ''}".strip()


def _query_en(title: str, author: str) -> str:
    try:
        from transliterate import translit
        return translit(f"{title or ''} {author or ''}".strip(), "ru", reversed=True)
    except Exception:
        return f"{title or ''} {author or ''}".strip()


# ─── ДИАГНОСТИКА ───────────────────────────────────
async def diagnose_sources(
    session: Optional[aiohttp.ClientSession] = None,
    title: str = "Муму",
    author: str = "Тургенев",
) -> None:
    """
    Тест всех источников — подробный отчёт.
    Вызов: python -c "import asyncio; from services.file_sources import diagnose_sources; asyncio.run(diagnose_sources(None))"
    """
    print("=== DIAGNOSTICS ===\n")
    query = f"{title} {author}".strip()
    own_session = False
    if session is None:
        connector = aiohttp.TCPConnector(ssl=False)
        session = aiohttp.ClientSession(headers=BROWSER_HEADERS, connector=connector)
        own_session = True
    try:
        test_cases = [
            ("FB2", "search_zlib", search_zlib(session, query, "fb2")),
            ("EPUB", "search_gutenberg", search_gutenberg(session, query)),
            ("DJVU", "search_archive_org", search_archive_org(session, query, "DJVU")),
            ("Аудио", "search_knigavuhe", search_knigavuhe(session, query)),
            ("Аудио", "search_akniga", search_akniga(session, query)),
            ("Аудио", "search_librivox", search_librivox(session, query)),
        ]
        for fmt, name, coro in test_cases:
            try:
                t0 = time.time()
                result = await coro
                elapsed = time.time() - t0
                status = "OK" if result else "FAIL"
                out = result or "ne najdeno"
                print(f"{status} [{fmt}] {name}: {out[:80]} ({elapsed:.1f}s)")
            except Exception as e:
                print(f"ERR [{fmt}] {name}: {e!r}")
    finally:
        if own_session and not session.closed:
            await session.close()
    print("\n=== END ===")


# Google fallback (для file_search)
async def google_fallback_search(
    session: aiohttp.ClientSession,
    title: str,
    author: str,
    fmt: str,
) -> list[str]:
    from config import GOOGLE_CSE_CX
    cx = (GOOGLE_CSE_CX or "").strip()
    if not GOOGLE_API_KEY or not cx:
        return []
    query = f"{title} {author} скачать {fmt} бесплатно"
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"q": query, "key": GOOGLE_API_KEY, "cx": cx, "num": 5}
    trusted = ["flibusta", "royallib", "lib.ru", "z-lib", "archive.org", "knigavuhe", "akniga", "litres"]
    try:
        async with session.get(url, params=params, headers=BROWSER_HEADERS, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
        items = data.get("items") or []
        return [r["link"] for r in items if any(d in r.get("link", "") for d in trusted)][:5]
    except Exception:
        return []
