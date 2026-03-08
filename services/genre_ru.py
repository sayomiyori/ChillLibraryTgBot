"""Перевод жанров (категорий Google Books) на русский."""
from typing import List

# Частые категории Google Books (EN) -> русский
GENRE_RU = {
    "fiction": "Художественная литература",
    "literary criticism": "Литературная критика",
    "poetry": "Поэзия",
    "drama": "Драматургия",
    "biography & autobiography": "Биография и автобиография",
    "biography": "Биография",
    "autobiography": "Автобиография",
    "history": "История",
    "science": "Наука",
    "computers": "Компьютеры и IT",
    "technology": "Технологии",
    "business & economics": "Бизнес и экономика",
    "business": "Бизнес",
    "economics": "Экономика",
    "philosophy": "Философия",
    "psychology": "Психология",
    "religion": "Религия",
    "self-help": "Саморазвитие",
    "cooking": "Кулинария",
    "health & fitness": "Здоровье и фитнес",
    "sports": "Спорт",
    "travel": "Путешествия",
    "art": "Искусство",
    "music": "Музыка",
    "photography": "Фотография",
    "architecture": "Архитектура",
    "law": "Право",
    "political science": "Политология",
    "education": "Образование",
    "language arts": "Языкознание",
    "literature": "Литература",
    "romance": "Любовный роман",
    "mystery": "Детектив",
    "thriller": "Триллер",
    "horror": "Ужасы",
    "fantasy": "Фэнтези",
    "science fiction": "Научная фантастика",
    "comics": "Комиксы",
    "graphic novels": "Графические романы",
    "juvenile fiction": "Детская литература",
    "young adult": "Молодёжная литература",
    "children": "Детская литература",
    "humor": "Юмор",
    "essays": "Эссе",
    "literary collections": "Литературные сборники",
    "short stories": "Рассказы",
    "novel": "Роман",
    "prose": "Проза",
    "criticism": "Критика",
    "social science": "Социальные науки",
    "mathematics": "Математика",
    "medical": "Медицина",
    "nature": "Природа",
    "pets": "Домашние животные",
    "gardening": "Садоводство",
    "crafts & hobbies": "Рукоделие и хобби",
    "antiques & collectibles": "Антиквариат",
    "house & home": "Дом и быт",
    "family": "Семья",
    "reference": "Справочная литература",
    "foreign language study": "Изучение языков",
    "literary criticism / general": "Литературная критика",
    "fiction / general": "Художественная литература",
    "history / general": "История",
    "body, mind & spirit": "Тело, разум и дух",
    "true crime": "Криминал",
    "adventure": "Приключения",
    "action": "Экшн",
    "suspense": "Саспенс",
    "western": "Вестерн",
    "classics": "Классика",
    "contemporary": "Современная проза",
    "historical": "Историческая проза",
}


def genres_to_russian(categories: List[str]) -> str:
    """Переводит список категорий на русский (через запятую, до 3 шт.)."""
    if not categories:
        return ""
    result = []
    for cat in categories[:3]:
        c = str(cat or "").strip().lower()
        if not c:
            continue
        ru = GENRE_RU.get(c) or GENRE_RU.get(c.split("/")[0].strip()) or GENRE_RU.get(c.split(" & ")[0].strip())
        result.append(ru if ru else cat.strip())
    return ", ".join(result) if result else ""
