"""Алиас для запуска: используйте main.py (один session, кэш, новый флоу)."""
import asyncio
import sys
from main import main

if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
