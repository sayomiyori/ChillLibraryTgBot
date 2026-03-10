"""Поиск ссылок на форматы книг: LibGen зеркала, Anna's Archive, Open Library, Gutenberg.

Таймаут 5 сек на источник; параллельные запросы к зеркалам; первый ответ — в результат.
При старте бота проверяются доступные зеркала (Railway DNS).
"""
import asyncio
import json
import logging
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 5.0
MIRROR_CHECK_TIMEOUT = 3.0
WANTED_EXTENSIONS = {"epub", "fb2", "pdf", "txt", "djvu", "mobi"}
HTML_SEARCH_TIMEOUT = 8.0
SEARCH_PATHS = [
    "/index.php",   # стандартный поиск
    "/search.php",  # альтернативный путь
    "/fiction/",    # раздел художественной литературы
]

LIBGEN_MIRRORS = [
    "http://libgen.is",
    "http://libgen.st",
    "http://libgen.rs",
    "http://libgen.li",
    "http://libgen.gs",
    "https://libgen.buzz",
    "https://libgen.fun",
]

# Заполняется при старте бота через check_available_mirrors()
AVAILABLE_MIRRORS: List[str] = []


def prepare_queries(title: str, author: str) -> List[str]:
    """
    Варианты запроса для LibGen: только title, title + фамилия, транслит.
    LibGen плохо ищет по инициалам (Тургенев И.С.) — берём только фамилию.
    """
    title = (title or "").strip()
    author = (author or "").strip()
    if not title:
        return []

    queries = [title]

    # Фамилия без инициалов: "Тургенев И.С." → "Тургенев", убираем точки и запятые
    author_clean = re.sub(r"[.,]", "", author)
    parts = author_clean.split()
    if parts:
        surname = parts[0].strip()
        if surname and surname not in (title, ""):
            queries.append(f"{title} {surname}".strip())

    # Транслит при кириллице
    if title and any("\u0400" <= c <= "\u04FF" for c in title):
        try:
            from transliterate import translit
            title_en = translit(title, "ru", reversed=True)
            if title_en and title_en != title:
                queries.append(title_en)
                if parts and surname:
                    try:
                        surname_en = translit(surname, "ru", reversed=True)
                        if surname_en:
                            queries.append(f"{title_en} {surname_en}".strip())
                    except Exception:
                        pass
        except Exception:
            pass

    # Уникальные, не пустые, минимум 2 символа
    seen = set()
    out = []
    for q in queries:
        q = q.strip()
        if len(q) >= 2 and q not in seen:
            seen.add(q)
            out.append(q)
    return out


async def _libgen_json_one(
    session: aiohttp.ClientSession,
    base_url: str,
    query: str,
) -> List[Dict[str, Any]]:
    """Один запрос к LibGen JSON API. Таймаут 5 сек. Кириллица в query через quote()."""
    raw = query.strip()
    q = quote(raw, safe="")
    url = f"{base_url.rstrip('/')}/json.php?title={q}&fields=id,title,author,extension,md5"
    try:
        t0 = time.perf_counter()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
            elapsed = time.perf_counter() - t0
            text = await resp.text(encoding="utf-8", errors="replace")
            if resp.status != 200:
                logger.warning(
                    "LibGen: зеркало %s недоступно: status=%s, запрос: %s",
                    base_url, resp.status, raw[:50],
                )
                return []
            try:
                data = json.loads(text)
            except Exception:
                data = []
            if isinstance(data, dict):
                items = data.get("data") or []
            else:
                items = data if isinstance(data, list) else []
            logger.info(
                "LibGen запрос: %s -> статус %s, результатов: %s (%.2fs)",
                url[:80] + "..." if len(url) > 80 else url,
                resp.status,
                len(items),
                elapsed,
            )
            logger.debug("LibGen ответ (первые 200 символов): %s", (text or "")[:200])
            return items
    except asyncio.TimeoutError:
        logger.warning("LibGen: зеркало %s недоступно: timeout", base_url)
        return []
    except Exception as e:
        logger.warning("LibGen: зеркало %s недоступно: %s", base_url, e)
        return []


def _get_mirrors_to_use() -> List[str]:
    """Использовать проверенные при старте зеркала или полный список."""
    return AVAILABLE_MIRRORS if AVAILABLE_MIRRORS else LIBGEN_MIRRORS


async def _fetch_first_libgen(query: str) -> List[Dict[str, Any]]:
    """Параллельно опрашиваем зеркала; первый успешный непустой ответ — возвращаем."""
    if not query or len(query.strip()) < 2:
        return []

    mirrors = _get_mirrors_to_use()

    async def fetch_one(base: str) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession() as session:
            return await _libgen_json_one(session, base, query)

    tasks = [asyncio.create_task(fetch_one(base)) for base in mirrors]
    try:
        for coro in asyncio.as_completed(tasks):
            try:
                result = await asyncio.wait_for(coro, timeout=REQUEST_TIMEOUT + 0.5)
                if result:
                    for t in tasks:
                        if not t.done():
                            t.cancel()
                    return result
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                continue
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
    logger.error("LibGen: все зеркала недоступны для запроса '%s'", query[:50])
    return []


# ------ Скачивание файла по ссылке ------

DOWNLOAD_MAX_BYTES = 50 * 1024 * 1024  # 50 MB — лимит Telegram для send_document


async def download_book(
    session: Optional[aiohttp.ClientSession],
    download_url: str,
) -> Optional[Tuple[bytes, str]]:
    """
    Скачивает файл по ссылке LibGen. Редиректы разрешены.
    Возвращает (bytes, filename) или None при ошибке/таймауте/файл > 50MB.
    """
    if not download_url:
        return None
    use_session = session
    if use_session is None:
        use_session = aiohttp.ClientSession()
    try:
        async with use_session.get(
            download_url,
            timeout=aiohttp.ClientTimeout(total=30),
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                logger.warning("Skachivanie %s: status %s", download_url[:80], resp.status)
                return None
            content_length = resp.headers.get("Content-Length")
            if content_length:
                try:
                    size = int(content_length)
                    if size > DOWNLOAD_MAX_BYTES:
                        logger.warning("Fajl slishkom bolshoj: %s bajt", content_length)
                        return None
                except (ValueError, TypeError):
                    pass
            file_bytes = await resp.read()
            if len(file_bytes) > DOWNLOAD_MAX_BYTES:
                logger.warning("Fajl slishkom bolshoj: %s bajt", len(file_bytes))
                return None
            content_disposition = resp.headers.get("Content-Disposition") or ""
            if "filename=" in content_disposition:
                filename = content_disposition.split("filename=")[-1].strip('"\' \t')
            else:
                md5 = ""
                if "md5=" in download_url:
                    md5 = download_url.split("md5=")[-1].split("&")[0].strip()[:32]
                filename = f"book_{md5 or 'unknown'}.bin"
            logger.info("Skachano: %s, razmer: %s bajt", filename[:60], len(file_bytes))
            return (file_bytes, filename)
    except asyncio.TimeoutError:
        logger.error("Tajmaut skachivaniya: %s", download_url[:80])
        return None
    except Exception as e:
        logger.error("Oshibka skachivaniya %s: %s", download_url[:80], e)
        return None
    finally:
        if session is None and use_session is not None:
            await use_session.close()


# ------ LibGen HTML (художественная литература; /json.php только для статей) ------

async def get_md5_by_edition_id(
    session: aiohttp.ClientSession,
    edition_id: str,
    mirror: str,
) -> Optional[str]:
    """
    Страница издания libgen.li: edition.php?id=... — на ней есть ссылка get.php?md5=...
    для скачивания. Извлекаем md5.
    """
    url = f"{mirror.rstrip('/')}/edition.php?id={edition_id}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                logger.warning("LibGen edition %s: status %s", edition_id, resp.status)
                return None
            html = await resp.text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.debug("LibGen get_md5_by_edition_id %s: %s", edition_id, e)
        return None

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a.get("href") or ""
            if "get.php?md5=" in href:
                md5 = href.split("md5=")[-1].split("&")[0].strip()
                if len(md5) == 32:
                    logger.info("LibGen: md5 dlya edition %s: %s", edition_id, md5)
                    return md5
    except Exception:
        pass

    matches = re.findall(r"\b([a-fA-F0-9]{32})\b", html)
    if matches:
        logger.info("LibGen: md5 iz HTML stranicy edition %s: %s", edition_id, matches[0])
        return matches[0]

    logger.debug("LibGen edition %s HTML (pervye 1000):\n%s", edition_id, html[:1000])
    return None


ALLOWED_EXTENSIONS = ("epub", "fb2", "pdf", "mobi", "djvu")
LIBGEN_ROW_SEMAPHORE = 5  # макс. одновременных запросов к edition.php


async def _process_one_row(
    session: aiohttp.ClientSession,
    row: Any,
    mirror: str,
    base: str,
    required_lang: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Обработка одной строки таблицы: язык, название из <a>/<b>, edition_id → md5."""
    cols = row.find_all("td")
    if len(cols) < 8:
        return None

    if required_lang and len(cols) > 4:
        lang_cell = (cols[4].get_text(strip=True) or "").lower()
        if required_lang.lower() not in lang_cell:
            return None

    title_col = cols[0]
    for tag in title_col.find_all("span", class_="badge"):
        tag.decompose()
    for tag in title_col.find_all("nobr"):
        tag.decompose()

    edition_id = None
    md5 = None
    title = ""
    for a_tag in title_col.find_all("a", href=True):
        href = a_tag.get("href") or ""
        if "md5=" in href.lower():
            raw = href.split("md5=")[-1].split("&")[0].strip()
            if len(raw) == 32:
                md5 = raw
                title = (a_tag.get_text(strip=True) or "").strip()
                break
        if "edition.php?id=" in href.lower():
            edition_id = href.split("id=")[-1].split("&")[0].strip()
            title = (a_tag.get_text(strip=True) or "").strip()
            break

    bold = title_col.find("b")
    if bold:
        for i in bold.find_all("i"):
            i.decompose()
        clean_title = (bold.get_text(strip=True) or "").strip()
        if clean_title:
            title = clean_title
    if not title and title_col:
        title = (title_col.get_text(strip=True) or "").strip()

    if not edition_id and not md5:
        return None

    author = (cols[1].get_text(strip=True) or "").replace("(Author)", "").strip().rstrip(";").strip()
    extension = (cols[7].get_text(strip=True) or "").lower().strip()
    if extension not in ALLOWED_EXTENSIONS:
        return None

    if edition_id and not md5:
        md5 = await get_md5_by_edition_id(session, edition_id, mirror)
    if not md5:
        return None

    return {
        "title": title,
        "author": author,
        "extension": extension,
        "download_url": f"{base}/get.php?md5={md5}",
        "md5": md5,
    }


async def search_libgen_html(
    session: aiohttp.ClientSession,
    query: str,
    mirror: str,
    required_lang: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Поиск по index.php LibGen.
    [0] Title, [1] Author, [4] Language, [7] Extension.
    Запросы к edition.php выполняются параллельно (семaphore=5).
    required_lang — фильтр по колонке Language (например "Russian").
    """
    raw_query = (query or "").strip()
    if not raw_query:
        return []

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    url = f"{mirror.rstrip('/')}/index.php"
    params = {
        "req": raw_query,
        "res": 25,
        "view": "simple",
        "phrase": 1,
        "column": "title",
    }
    if required_lang:
        params["lang"] = required_lang
    try:
        async with session.get(
            url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=HTML_SEARCH_TIMEOUT),
        ) as resp:
            if resp.status != 200:
                return []
            html = await resp.text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.debug("LibGen HTML %s: %s", mirror, e)
        return []

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", {"id": "tablelibgen"})
    if not table:
        return []

    rows = table.find_all("tr")
    logger.info("LibGen: naydeno strok: %s", len(rows))

    base = mirror.rstrip("/")
    sem = asyncio.Semaphore(LIBGEN_ROW_SEMAPHORE)

    async def limited(row: Any) -> Optional[Dict[str, Any]]:
        async with sem:
            return await _process_one_row(session, row, mirror, base, required_lang)

    raw_results = await asyncio.gather(
        *[limited(row) for row in rows[1:]],
        return_exceptions=True,
    )
    results = [
        r for r in raw_results
        if r is not None and not isinstance(r, Exception)
    ]
    logger.info("LibGen: raspoznano knig: %s", len(results))
    return results[:5]


LIBGEN_RU_MIRROR = "http://libgen.li"


async def search_libgen_ru(
    session: aiohttp.ClientSession,
    title: str,
) -> Optional[Dict[str, Any]]:
    """
    Ищет лучшее русское издание книги на LibGen.
    Возвращает один dict в формате карточки книги (zone=RU) или None.
    """
    title = (title or "").strip()
    if not title:
        return None

    results = await search_libgen_html(
        session, title, LIBGEN_RU_MIRROR, required_lang="Russian",
    )
    if not results:
        try:
            from transliterate import translit
            title_translit = translit(title, "ru", reversed=True)
            if title_translit and title_translit != title:
                results = await search_libgen_html(
                    session, title_translit, LIBGEN_RU_MIRROR, required_lang="Russian",
                )
        except Exception:
            pass

    if not results:
        logger.warning("LibGen RU: nichego ne najdeno dlya '%s'", title[:50])
        return None

    best = results[0]
    md5 = best.get("md5") or ""
    ext = (best.get("extension") or "").lower()
    download_url = best.get("download_url") or ""
    available_formats: Dict[str, str] = {}
    if ext and download_url:
        available_formats[ext] = download_url
    for item in results[1:]:
        if item.get("title") == best.get("title") and item.get("author") == best.get("author"):
            e = (item.get("extension") or "").lower()
            u = item.get("download_url") or ""
            if e and u and e not in available_formats:
                available_formats[e] = u

    return {
        "id": f"libgen_{md5}" if md5 else f"libgen_{hash(title)}",
        "title": best.get("title") or title,
        "author": best.get("author") or "",
        "zone": "RU",
        "flag": "\U0001f1f7\U0001f1fa",
        "lang_code": "ru",
        "language": "ru",
        "source": "libgen",
        "available_formats": available_formats,
        "md5": md5,
        "description": "",
        "cover_url": "",
        "rating": 0.0,
        "categories": [],
        "year": 0,
        "preview_link": None,
    }


OPEN_LIBRARY_SEARCH = "https://openlibrary.org/search.json"


async def search_open_library_ru(
    session: aiohttp.ClientSession,
    title: str,
) -> Optional[Dict[str, Any]]:
    """
    Fallback для RU: поиск русского издания в Open Library.
    Возвращает один dict в формате карточки или None.
    """
    title = (title or "").strip()
    if not title:
        return None
    params = {
        "title": title[:200],
        "language": "rus",
        "limit": 3,
    }
    try:
        async with session.get(
            OPEN_LIBRARY_SEARCH,
            params=params,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
    except Exception as e:
        logger.warning("Open Library RU: %s", e)
        return None

    docs = data.get("docs") or []
    if not docs:
        return None

    doc = docs[0]
    ol_title = doc.get("title") or title
    author_list = doc.get("author_name") or []
    author = ", ".join(author_list[:3]) if author_list else ""
    year = 0
    fp = doc.get("first_publish_year")
    if fp is not None:
        try:
            year = int(fp)
        except (TypeError, ValueError):
            pass
    cover_i = doc.get("cover_i")
    cover_url = f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg" if cover_i else ""
    work_key = doc.get("key") or ""
    book_id = f"ol_{work_key.replace('/works/', '')}" if work_key else f"ol_{hash(title)}"

    return {
        "id": book_id,
        "title": ol_title,
        "author": author,
        "zone": "RU",
        "flag": "\U0001f1f7\U0001f1fa",
        "lang_code": "ru",
        "source": "openlibrary",
        "description": (doc.get("first_sentence") or [""])[0] if isinstance(doc.get("first_sentence"), list) else (doc.get("first_sentence") or ""),
        "cover_url": cover_url,
        "rating": 0.0,
        "categories": [],
        "year": year,
        "preview_link": None,
        "available_formats": {},
    }


async def search_libgen_fiction(
    session: aiohttp.ClientSession,
    query: str,
    mirror: str,
) -> List[Dict[str, Any]]:
    """
    Отдельная диагностика раздела /fiction/.
    Сейчас используется только для логирования структуры.
    """
    raw_query = query.strip()
    if not raw_query:
        return []

    url = f"{mirror.rstrip('/')}/fiction/"
    params = {
        "q": raw_query,
        "criteria": "title",
        "language": "Russian",
        "format": "",
    }
    logger.info("LibGen fiction zapros: %s params=%s", url, params)
    try:
        async with session.get(
            url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=HTML_SEARCH_TIMEOUT),
        ) as resp:
            status = resp.status
            html = await resp.text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.debug("LibGen fiction %s: %s", mirror, e)
        return []

    logger.info(
        "LibGen fiction -> status=%s, len(html)=%s",
        status,
        len(html),
    )
    logger.debug(
        "LibGen fiction HTML (pervye 2000 simvolov):\n%s",
        html[:2000],
    )

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    logger.debug("LibGen fiction: naydeno tablic: %s", len(tables))
    for i, t in enumerate(tables):
        rows = len(t.find_all("tr"))
        logger.debug(
            "Fiction tablica %s: id=%s class=%s, strok=%s",
            i,
            t.get("id"),
            t.get("class"),
            rows,
        )

    # Пока возвращаем пустой список — парсер будет доработан после анализа логов
    return []


async def check_available_mirrors() -> List[str]:
    """
    При старте бота проверить, какие зеркала доступны (обход DNS/сетевых ограничений Railway).
    Возвращает список URL доступных зеркал. Результат сохраняется в AVAILABLE_MIRRORS.
    """
    global AVAILABLE_MIRRORS
    available: List[str] = []
    timeout = aiohttp.ClientTimeout(total=MIRROR_CHECK_TIMEOUT)
    async with aiohttp.ClientSession() as session:
        for base in LIBGEN_MIRRORS:
            url = f"{base.rstrip('/')}/json.php?title=test&fields=id"
            try:
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status < 500:
                        available.append(base)
                        logger.info("Zerkalo dostupno: %s", base)
                    else:
                        logger.warning("Zerkalo nedostupno: %s (status=%s)", base, resp.status)
            except Exception as e:
                logger.warning("Zerkalo nedostupno: %s (%s)", base, e)
    AVAILABLE_MIRRORS[:] = available
    return available


def _items_to_formats(items: List[Dict[str, Any]], base_download: str = "https://libgen.is") -> Dict[str, str]:
    """Собрать из списка записей LibGen словарь {extension: download_url}."""
    formats: Dict[str, str] = {}
    seen: Dict[str, bool] = defaultdict(bool)
    for item in items[:10]:
        md5 = (item.get("md5") or "").strip()
        if not md5:
            continue
        ext = (item.get("extension") or "").strip().lower()
        if ext not in WANTED_EXTENSIONS:
            continue
        if seen[ext]:
            continue
        seen[ext] = True
        url = f"{base_download.rstrip('/')}/get.php?md5={md5}"
        formats[ext] = url
    return formats


# ------ Anna's Archive (HTML) ------

ANNAS_SEARCH_URL = "https://annas-archive.org/search"
ANNAS_DOWNLOAD_BASE = "https://annas-archive.org"


async def search_annas_archive(title: str, author: str = "") -> Dict[str, str]:
    """Поиск на Anna's Archive (HTML). Возвращает {extension: url} при успехе."""
    query = f"{(title or '').strip()} {(author or '').strip()}".strip()
    if len(query) < 2:
        return {}

    url = f"{ANNAS_SEARCH_URL}?q={quote(query)}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                headers={"User-Agent": "Mozilla/5.0 (compatible; Bot/1.0)"},
            ) as resp:
                if resp.status != 200:
                    logger.warning("Anna's Archive: status=%s", resp.status)
                    return {}
                html = await resp.text(encoding="utf-8", errors="replace")
    except asyncio.TimeoutError:
        logger.warning("Anna's Archive: timeout")
        return {}
    except Exception as e:
        logger.warning("Anna's Archive: %s", e)
        return {}

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {}

    formats: Dict[str, str] = {}
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        # Anna's Archive: /md5/{hash} → скачивание через их домен
        if "/md5/" in href:
            m = re.search(r"/md5/([a-fA-F0-9]{32})", href)
            if m:
                md5 = m.group(1)
                annas_url = f"{ANNAS_DOWNLOAD_BASE}/md5/{md5}"
                if "epub" not in formats:
                    formats["epub"] = annas_url
                elif "pdf" not in formats:
                    formats["pdf"] = annas_url
                elif "fb2" not in formats:
                    formats["fb2"] = annas_url
                break
        if "md5=" in href:
            m = re.search(r"md5=([a-fA-F0-9]{32})", href)
            if m and "epub" not in formats:
                formats["epub"] = f"https://libgen.is/get.php?md5={m.group(1)}"
                break
        if href.startswith("/") and ("." in href):
            full = f"{ANNAS_DOWNLOAD_BASE}{href}"
            if full.endswith(".epub") and "epub" not in formats:
                formats["epub"] = full
            elif full.endswith(".pdf") and "pdf" not in formats:
                formats["pdf"] = full
            elif full.endswith(".fb2") and "fb2" not in formats:
                formats["fb2"] = full
    return formats


# ------ Open Library (epub fallback) ------

OPENLIBRARY_SEARCH = "https://openlibrary.org/search.json"


async def search_open_library_formats(title: str, author: str = "") -> Dict[str, str]:
    """Open Library — надёжный fallback для epub. Таймаут 5 сек. Пробуем ia (archive.org) и edition_key."""
    q = f"{(title or '').strip()} {(author or '').strip()}".strip()
    if len(q) < 2:
        return {}

    formats: Dict[str, str] = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                OPENLIBRARY_SEARCH,
                params={"q": q, "limit": 5},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
    except Exception as e:
        logger.debug("Open Library: %s", e)
        return {}

    docs = data.get("docs") or []
    for doc in docs[:5]:
        # Сначала пробуем Internet Archive ID — epub на archive.org
        ia_ids = doc.get("ia") or []
        if ia_ids:
            archive_id = ia_ids[0]
            if archive_id:
                formats["epub"] = f"https://archive.org/download/{archive_id}/{archive_id}.epub"
                break
        edition_keys = doc.get("edition_key") or []
        for key in edition_keys[:1]:
            if not key:
                continue
            formats["epub"] = f"https://openlibrary.org/books/{key}.epub"
            break
        if formats:
            break
    return formats


# ------ Gutenberg (epub для классики) ------

GUTENDEX_URL = "https://gutendex.com/books"


async def search_gutenberg_formats(title: str, author: str = "") -> Dict[str, str]:
    """Project Gutenberg через Gutendex. Таймаут 5 сек. Возвращает epub при наличии."""
    q = f"{(title or '').strip()} {(author or '').strip()}".strip()
    if len(q) < 2:
        return {}

    formats: Dict[str, str] = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                GUTENDEX_URL,
                params={"search": q},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
    except Exception as e:
        logger.debug("Gutenberg: %s", e)
        return {}

    for book in (data.get("results") or [])[:3]:
        fmt = book.get("formats") or {}
        epub = fmt.get("application/epub+zip") or fmt.get("application/x-epub+zip")
        if epub and "epub" not in formats:
            formats["epub"] = epub
            break
    return formats


# ------ Главная функция ------

async def get_download_formats(title: str, author: str) -> Dict[str, str]:
    """
    1. Anna's Archive (5s)
    2. LibGen зеркала параллельно (5s), первый ответ
    3. Open Library epub (5s)
    4. Gutenberg epub (5s)
    Общее время не более ~8 сек за счёт параллели и таймаутов.
    """
    query = f"{(title or '').strip()} {(author or '').strip()}".strip()
    if len(query) < 2:
        return {}

    formats: Dict[str, str] = {}

    # 1. Anna's Archive
    annas = await search_annas_archive(title, author)
    if annas:
        formats.update(annas)
        logger.info("LibGen: форматы получены через Anna's Archive")
        if len(formats) >= 2:
            return formats

    # 2. LibGen HTML (index.php — для художественной литературы; json.php только для статей)
    query_list = prepare_queries(title, author)
    if not query_list:
        query_list = [query] if len(query.strip()) >= 2 else []
    if query_list:
        mirrors = _get_mirrors_to_use()
        wanted_book = {"epub", "fb2", "pdf", "mobi"}
        async with aiohttp.ClientSession() as session:
            for q in query_list:
                for mirror in mirrors:
                    results = await search_libgen_html(session, q, mirror)
                    if results:
                        for item in results:
                            ext = (item.get("extension") or "").lower()
                            if ext in wanted_book and ext not in formats:
                                formats[ext] = item.get("download_url") or ""
                        if formats:
                            logger.info(
                                "LibGen nashol dlya '%s': %s",
                                q[:50],
                                list(formats.keys()),
                            )
                            break
                if formats:
                    break

    # 3. Open Library (epub)
    if "epub" not in formats:
        ol = await search_open_library_formats(title, author)
        if ol.get("epub"):
            formats["epub"] = ol["epub"]
            logger.info("Open Library nashol epub dlya '%s'", (title or "")[:40])

    # 4. Gutenberg (epub)
    if "epub" not in formats:
        gb = await search_gutenberg_formats(title, author)
        if gb.get("epub"):
            formats["epub"] = gb["epub"]
            logger.info("LibGen: epub poluchen cherez Gutenberg")

    logger.info("Itogo formatov dlya '%s': %s", (title or query)[:50], formats)
    return formats
