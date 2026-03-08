"""Ссылки «Где купить» — поиск в магазинах."""
from urllib.parse import quote_plus


def get_buy_links(title: str, author: str) -> list[tuple[str, str]]:
    """Возвращает список (название_магазина, url)."""
    q = f"{title} {author}".strip()
    encoded = quote_plus(q)
    return [
        ("Лабиринт", f"https://www.labirint.ru/search/{encoded}/"),
        ("Wildberries", f"https://www.wildberries.ru/catalog/0/search.aspx?search={encoded}"),
        ("Ozon", f"https://www.ozon.ru/search/?text={encoded}"),
        ("Litres", f"https://www.litres.ru/search/?q={encoded}"),
        ("Читай-город", f"https://www.chitai-gorod.ru/search/result/?q={encoded}"),
    ]
