"""
База источников: возвращаем прямую ссылку на файл (без скачивания).
Маппинг форматов и площадок — см. SOURCES_BY_FORMAT.
Поиск по формату выполняется параллельно; затем проверяется «начинка» файла (название/автор).
"""
import asyncio
import logging
import re
from typing import Callable, Awaitable, Optional

import aiohttp

logger = logging.getLogger(__name__)

EXTENSIONS = {
    "fb2": ["fb2", "FB2"],
    "epub": ["epub", "EPUB", "epub3"],
    "pdf": ["pdf", "PDF"],
    "txt": ["txt", "TXT", "text/plain", "doc", "DOC"],
    "djvu": ["djvu", "DJVU"],
    "audio": ["mp3", "m4b", "MP3", "M4B", "mp4"],
}

DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/octet-stream,*/*",
}
MAX_FILE_SIZE = 48 * 1024 * 1024


def _norm(s: str, max_len: int = 150) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", " ", str(s).strip())[:max_len]
    return s


async def _download(url: str) -> Optional[bytes]:
    try:
        timeout = aiohttp.ClientTimeout(total=45, connect=15)
        async with aiohttp.ClientSession(timeout=timeout, headers=DOWNLOAD_HEADERS) as session:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return None
                if (resp.content_length or 0) > MAX_FILE_SIZE:
                    return None
                data = await resp.read()
                return data if len(data) > 100 else None
    except Exception as e:
        logger.debug("Download %s: %s", url[:50], e)
        return None


# ---------- LibGen ----------
def _libgen_search_sync(query: str, ext: str) -> list[dict]:
    try:
        from libgen_api import LibgenSearch
        s = LibgenSearch()
        if ext:
            r = s.search_title_filtered(query, {"Extension": ext}, exact_match=False)
        else:
            r = s.search_title(query)
        return r or []
    except Exception as e:
        logger.debug("LibGen search: %s", e)
        return []


def _libgen_resolve_sync(item: dict) -> list[str]:
    try:
        from libgen_api import LibgenSearch
        links = LibgenSearch().resolve_download_links(item)
        if not links:
            return []
        out = []
        for k in ("GET", "Cloudflare", "IPFS.io", "Infura"):
            u = links.get(k)
            if u and isinstance(u, str) and u.startswith("http"):
                out.append(u)
        return out[:4]
    except Exception:
        return []


async def get_url_libgen(title: str, author: str, fmt: str) -> Optional[str]:
    """Library Genesis — возвращаем первую прямую ссылку (без скачивания)."""
    q = _norm(f"{title} {author}")
    if len(q) < 2:
        return None
    loop = asyncio.get_event_loop()
    allowed = EXTENSIONS.get(fmt.lower(), [])
    for ext in allowed[:2]:
        items = await loop.run_in_executor(None, lambda qq=q, e=ext: _libgen_search_sync(qq, e))
        if not items:
            items = await loop.run_in_executor(None, lambda qq=q: _libgen_search_sync(qq, ""))
            items = [i for i in items if (i.get("Extension") or "").lower() == ext.lower()]
        for item in items[:5]:
            urls = await loop.run_in_executor(None, lambda i=item: _libgen_resolve_sync(i))
            for url in urls:
                if url and url.startswith("http"):
                    return url
    return None


# ---------- Internet Archive ----------
IA_SEARCH = "https://archive.org/advancedsearch.php"
IA_METADATA = "https://archive.org/metadata/{identifier}"
IA_DOWNLOAD = "https://archive.org/download/{identifier}/{filename}"


async def get_url_archive(title: str, author: str, fmt: str) -> Optional[str]:
    """Internet Archive — возвращаем первую подходящую ссылку."""
    ext_map = {"epub": ["epub", "epub3"], "pdf": ["pdf"], "txt": ["txt", "text", "chm"], "fb2": ["fb2"], "djvu": ["djvu"], "audio": ["mp3", "m4b", "ogg"]}
    want = ext_map.get(fmt.lower(), EXTENSIONS.get(fmt.lower(), []))
    q = f"title:({_norm(title, 80)}) AND mediatype:texts"
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(IA_SEARCH, params={"q": q, "fl[]": "identifier", "output": "json", "rows": 5}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        ids = (data.get("response", {}).get("docs") or [])[:3]
        for doc in ids:
            ident = doc.get("identifier")
            if not ident:
                continue
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(IA_METADATA.format(identifier=ident)) as meta_resp:
                    if meta_resp.status != 200:
                        continue
                    meta = await meta_resp.json()
            for f in (meta.get("files") or []):
                name = (f.get("name") or "").lower()
                fmt_ia = (f.get("format") or "").lower()
                if any(name.endswith("." + e) or e in name or e in fmt_ia for e in want):
                    fname = f.get("name", "")
                    if not fname or "/" in fname:
                        continue
                    return IA_DOWNLOAD.format(identifier=ident, filename=fname)
    except Exception as e:
        logger.debug("Archive: %s", e)
    return None


# ---------- Project Gutenberg (Gutendex) ----------
GUTENDEX = "https://gutendex.com/books"
FORMAT_MIME = {"epub": "application/epub+zip", "pdf": "application/pdf", "txt": "text/plain", "fb2": None, "audio": None}


async def get_url_gutenberg(title: str, author: str, fmt: str) -> Optional[str]:
    """Project Gutenberg — возвращаем ссылку на epub/pdf/txt."""
    mime = FORMAT_MIME.get(fmt.lower())
    if not mime:
        return None
    search = _norm(f"{title} {author}", 80)
    if len(search) < 2:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(GUTENDEX, params={"search": search}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        for book in (data.get("results") or [])[:5]:
            formats = book.get("formats") or {}
            url = formats.get(mime) or formats.get("text/html")
            if url and isinstance(url, str) and url.startswith("http"):
                return url
    except Exception as e:
        logger.debug("Gutenberg: %s", e)
    return None


# ---------- Площадки для TXT: lib.ru, royallib ----------
async def get_url_libru_txt(title: str, author: str, fmt: str) -> Optional[str]:
    """lib.ru — TXT, возвращаем первую ссылку на .txt."""
    if fmt.lower() != "txt":
        return None
    q = _norm(f"{author} {title}", 80)
    if len(q) < 2:
        return None
    try:
        search_url = "https://lib.ru/cgi-bin/seek.cgi"
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout, headers=DOWNLOAD_HEADERS) as session:
            async with session.get(search_url, params={"pattern": q, "encoding": "utf-8"}) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'href\s*=\s*["\']([^"\']+\.txt)(?:\?[^"\']*)?["\']', html, re.I):
            path = m.group(1)
            if path.startswith("/"):
                return "https://lib.ru" + path
            if path.startswith("http"):
                return path
            return "https://lib.ru/" + path.lstrip("/")
    except Exception as e:
        logger.debug("lib.ru: %s", e)
    return None


async def get_url_royallib(title: str, author: str, fmt: str) -> Optional[str]:
    """royallib.com — TXT, FB2, EPUB. Возвращаем первую ссылку на файл."""
    q = _norm(f"{title} {author}", 60)
    if len(q) < 2:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout, headers=DOWNLOAD_HEADERS) as session:
            async with session.get("https://royallib.com/search/", params={"q": q}) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text(encoding="utf-8", errors="replace")
            m = re.search(r'href\s*=\s*["\']([^"\']*?/book/[^"\']+)["\']', html)
            if not m:
                return None
            book_path = m.group(1).strip()
            if book_path.startswith("//"):
                book_path = "https:" + book_path
            elif not book_path.startswith("http"):
                book_path = "https://royallib.com/" + book_path.lstrip("/")
            async with session.get(book_path) as r2:
                if r2.status != 200:
                    return None
                page = await r2.text(encoding="utf-8", errors="replace")
            ext = "txt" if fmt.lower() == "txt" else "fb2" if fmt.lower() == "fb2" else "epub"
            pat = rf'href\s*=\s*["\']([^"\']*\.{re.escape(ext)})["\']'
            for m in re.finditer(pat, page, re.I):
                link = m.group(1).strip()
                if link.startswith("//"):
                    link = "https:" + link
                elif not link.startswith("http"):
                    link = "https://royallib.com/" + link.lstrip("/")
                if link.startswith("http"):
                    return link
    except Exception as e:
        logger.debug("royallib: %s", e)
    return None


# ---------- Flibusta (FB2, EPUB) ----------
async def get_url_flibusta(title: str, author: str, fmt: str) -> Optional[str]:
    """flibusta.is — FB2, EPUB. Возвращаем прямую ссылку на скачивание."""
    if fmt.lower() not in ("fb2", "epub"):
        return None
    q = _norm(f"{title} {author}", 80)
    if len(q) < 2:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers=DOWNLOAD_HEADERS) as session:
            async with session.get("https://flibusta.is/booksearch", params={"ask": q}) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text(encoding="utf-8", errors="replace")
            m = re.search(r'href\s*=\s*["\']/b/(\d+)["\']', html)
            if not m:
                return None
            return f"https://flibusta.is/b/{m.group(1)}/{fmt.lower()}"
    except Exception as e:
        logger.debug("flibusta: %s", e)
    return None


# ---------- Аудио: knigavuhe.org, akniga.org ----------
async def get_url_knigavuhe(title: str, author: str, fmt: str) -> Optional[str]:
    """knigavuhe.org — аудиокниги. Возвращаем первую ссылку на mp3/m4b."""
    if fmt.lower() != "audio":
        return None
    q = _norm(f"{title} {author}", 60)
    if len(q) < 2:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout, headers=DOWNLOAD_HEADERS) as session:
            async with session.get("https://knigavuhe.org/search/", params={"q": q}) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text(encoding="utf-8", errors="replace")
            m = re.search(r'href\s*=\s*["\']([^"\']*book/[^"\']+)["\']', html)
            if not m:
                return None
            link = m.group(1)
            if not link.startswith("http"):
                link = "https://knigavuhe.org" + link.lstrip("/")
            async with session.get(link) as r2:
                if r2.status != 200:
                    return None
                page = await r2.text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'href\s*=\s*["\']([^"\']*\.(?:mp3|m4b|mp4))["\']', page, re.I):
                u = m.group(1).strip()
                if u.startswith("http"):
                    return u
                return "https://knigavuhe.org/" + u.lstrip("/")
    except Exception as e:
        logger.debug("knigavuhe: %s", e)
    return None


async def get_url_akniga(title: str, author: str, fmt: str) -> Optional[str]:
    """akniga.org — аудиокниги. Возвращаем ссылку на страницу/файл."""
    if fmt.lower() != "audio":
        return None
    q = _norm(f"{title} {author}", 60)
    if len(q) < 2:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout, headers=DOWNLOAD_HEADERS) as session:
            async with session.get("https://akniga.org/search/", params={"q": q}) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text(encoding="utf-8", errors="replace")
            m = re.search(r'href\s*=\s*["\']([^"\']*/[^"\']+)["\']', html)
            if not m:
                return None
            link = m.group(1).strip()
            if link.startswith("//"):
                return "https:" + link
            if not link.startswith("http"):
                return "https://akniga.org/" + link.lstrip("/")
            return link
    except Exception as e:
        logger.debug("akniga: %s", e)
    return None


# ---------- Маппинг форматов и источников (возвращают URL, не файл) ----------
# Тип: (name, async get_url(title, author, fmt) -> str | None)
SourceUrlFn = Callable[[str, str, str], Awaitable[Optional[str]]]

SOURCES_BY_FORMAT: dict[str, list[tuple[str, SourceUrlFn]]] = {
    "txt": [
        ("lib.ru", get_url_libru_txt),
        ("royallib.com", get_url_royallib),
        ("LibGen", get_url_libgen),
        ("Internet Archive", get_url_archive),
        ("Project Gutenberg", get_url_gutenberg),
    ],
    "fb2": [
        ("flibusta.is", get_url_flibusta),
        ("royallib.com", get_url_royallib),
        ("LibGen", get_url_libgen),
        ("Internet Archive", get_url_archive),
    ],
    "epub": [
        ("flibusta.is", get_url_flibusta),
        ("royallib.com", get_url_royallib),
        ("LibGen", get_url_libgen),
        ("Internet Archive", get_url_archive),
        ("Project Gutenberg", get_url_gutenberg),
    ],
    "pdf": [
        ("LibGen", get_url_libgen),
        ("Internet Archive", get_url_archive),
        ("Project Gutenberg", get_url_gutenberg),
    ],
    "djvu": [
        ("Internet Archive", get_url_archive),
        ("LibGen", get_url_libgen),
    ],
    "audio": [
        ("knigavuhe.org", get_url_knigavuhe),
        ("akniga.org", get_url_akniga),
        ("LibGen", get_url_libgen),
    ],
}


async def find_link_any_source(
    title: str,
    author: str,
    fmt: str,
    *,
    validate_content: Callable[[str, str, str, str], Awaitable[bool]],
) -> Optional[tuple[str, str]]:
    """
    По формату опрашиваем площадки параллельно, получаем ссылки.
    Проверяем «начинку» первой порции файла (название/автор) и возвращаем первую валидную (url, source_name).
    """
    fmt_lower = (fmt or "").strip().lower()
    sources = SOURCES_BY_FORMAT.get(fmt_lower)
    if not sources:
        sources = [("LibGen", get_url_libgen), ("Internet Archive", get_url_archive)]
    tasks = [asyncio.create_task(fn(title, author, fmt)) for _, fn in sources]
    candidates: list[tuple[str, str]] = []
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
        for i, t in enumerate(tasks):
            if i >= len(sources):
                break
            try:
                if t.done() and not t.cancelled():
                    url = t.result()
                    if url and isinstance(url, str) and url.startswith("http"):
                        candidates.append((url, sources[i][0]))
            except Exception:
                pass
        for p in pending:
            try:
                p.cancel()
            except Exception:
                pass
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()

    for url, source_name in candidates:
        try:
            if await validate_content(url, title, author, fmt):
                return (url, source_name)
        except Exception as e:
            logger.debug("Validate %s: %s", source_name, e)
    return None
