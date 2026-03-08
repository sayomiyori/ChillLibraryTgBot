"""
Один поисковый запрос через search_universal — пишет в errors_log.txt только строки с FAIL.
Запуск из корня проекта: python scripts/run_one_search_log_errors.py
"""
import asyncio
import logging
import sys
from pathlib import Path

# корень проекта в PYTHONPATH
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Файл для строк с ошибками (избегаем Unicode в консоли Windows)
_log_file = _root / "errors_log.txt"
_file_stream = open(_log_file, "w", encoding="utf-8")


class FilterErrors(logging.Filter):
    def filter(self, record):
        return "\u274c" in (record.getMessage() or "")


handler = logging.StreamHandler(_file_stream)
handler.setFormatter(logging.Formatter("%(message)s"))
handler.addFilter(FilterErrors())
for name in ("services.file_sources", "services.file_search"):
    lgr = logging.getLogger(name)
    lgr.handlers.clear()
    lgr.addHandler(handler)
    lgr.setLevel(logging.INFO)


async def main():
    import aiohttp
    from services.file_sources import SOURCES_CONFIG, _parse_source, _smart_parse
    from urllib.parse import quote

    query = "Муму Тургенев"
    fmt = "FB2"
    # Все источники для FB2/EPUB/TXT
    sources = [(n, c) for n, c in SOURCES_CONFIG.items() if fmt in c.get("formats", [])]
    connector = aiohttp.TCPConnector(ssl=True)
    async with aiohttp.ClientSession(connector=connector, trust_env=True) as session:
        _file_stream.write(f"Query: {query} | format: {fmt} | sources: {len(sources)}\n--- errors ---\n")
        _file_stream.flush()
        for name, cfg in sources:
            await _parse_source(session, cfg, name, query)
            url = cfg["url"].replace("{query}", quote(query, safe=""))
            await _smart_parse(session, url, query, cfg.get("base_url", ""), name)
        _file_stream.write("--- end ---\n")
        _file_stream.flush()
    print("Done. See errors_log.txt")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        _file_stream.close()
