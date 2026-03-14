"""
Поиск книги по цитате через Groq (llama-3.3-70b-versatile).
Замена Gemini для устранения таймаутов на Railway.
"""
import asyncio
import json
import logging
from typing import Optional

from config import GROQ_API_KEY

logger = logging.getLogger(__name__)

QUOTE_CONFIDENCE_THRESHOLD = 0.65  # ниже — возвращаем None
QUOTE_TIMEOUT = 10.0

SYSTEM_PROMPT = """Ты эксперт по мировой и русской литературе.
Твоя задача — определить, из какой книги цитата.

Уровни уверенности:
- 0.9-1.0: ты точно знаешь эту книгу и цитату
- 0.7-0.9: очень вероятно, характерный стиль/детали автора
- 0.5-0.7: возможно, но не уверен
- ниже 0.5: не знаешь

ВАЖНО:
- Первые предложения известных книг — ты должен знать (Муму, Война и мир, Анна Каренина и др.)
- Не путай книги по косвенным признакам (Москва ≠ Булгаков автоматически)
- Лучше честное низкое confidence, чем неверный ответ с высоким

Верни ТОЛЬКО валидный JSON:
{"book": "название книги", "author": "автор", "confidence": 0.0-1.0, "found": true/false, "reasoning": "кратко почему именно эта книга"}"""


async def find_by_quote(quote_text: str) -> Optional[dict]:
    """
    Определить книгу по цитате через Groq.
    Возвращает {"title": str, "author": str, "confidence": int 0-100} или None.
    При confidence < 0.5 (или found=false) возвращается None.
    """
    quote_text = (quote_text or "").strip()
    if not quote_text or not GROQ_API_KEY:
        if not GROQ_API_KEY:
            logger.debug("find_by_quote: GROQ_API_KEY not set")
        return None

    user_content = f'Identify the book by this quote:\n\n"{quote_text[:1500]}"'

    try:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=GROQ_API_KEY)
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
                max_tokens=300,
            ),
            timeout=QUOTE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("find_by_quote: timeout %.1fs", QUOTE_TIMEOUT)
        return None
    except Exception as e:
        logger.error("find_by_quote: %s", e, exc_info=True)
        return None

    content = (response.choices[0].message.content or "").strip()
    if not content:
        return None

    # Извлечь JSON из ответа
    start = content.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(content)):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    content = content[start : i + 1]
                    break
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.debug("find_by_quote: invalid JSON %s", content[:150])
        return None

    book = (data.get("book") or data.get("title") or "").strip()
    author = (data.get("author") or "").strip()
    confidence = float(data.get("confidence", 0.0))
    reasoning = (data.get("reasoning") or "").strip()
    logger.info(
        "Groq quote: book=%s, confidence=%s, reasoning=%s",
        book or "(empty)",
        confidence,
        (reasoning or "")[:120],
    )

    if data.get("found") is False:
        return None

    if confidence < QUOTE_CONFIDENCE_THRESHOLD:
        return None

    title = book
    if not title:
        return None

    # Перекрёстная проверка: первое предложение книги совпадает с цитатой?
    if not await _cross_check_quote(client, quote_text[:500], title, author):
        logger.debug("find_by_quote: cross-check failed for %s - %s", title, author)
        return None

    confidence_pct = min(100, max(0, int(round(confidence * 100))))
    return {
        "title": title,
        "author": author or "Неизвестный автор",
        "confidence": confidence_pct,
    }


async def _cross_check_quote(client, quote: str, book_title: str, author: str) -> bool:
    """Спросить Groq: первое предложение книги '{title}' автора '{author}' совпадает с цитатой? YES/NO."""
    prompt = (
        f'The first sentence of the book "{book_title}" by {author} — '
        f'does it match this quote? Answer only YES or NO.\n\nQuote: "{quote[:400]}"\n\nAnswer:'
    )
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=10,
            ),
            timeout=5.0,
        )
    except Exception as e:
        logger.debug("find_by_quote cross_check: %s", e)
        return True  # при ошибке проверки не отбрасываем результат
    text = (response.choices[0].message.content or "").strip().upper()
    # Strict match: only reject if the entire response is "NO"/"НЕТ",
    # not a substring (e.g. "NO" should not match "KNOWN" or "WONDERFUL")
    cleaned = text.strip().rstrip(".")
    if cleaned in ("NO", "НЕТ"):
        return False
    return True
