"""
CLI ingest: embed clip descriptions and build the Redis index.

    python -m backend.ingest                 # loads resources/clips.json
    python -m backend.ingest path/to/my.json # loads a custom clips file
    python -m backend.ingest --clear         # drops index and deletes clip:* keys
"""
import sys
from pathlib import Path

from .search_engine import get_search_engine


def main(argv: list[str]) -> int:
    engine = get_search_engine()
    if not engine.check_connection():
        print("Cannot reach Redis. Check REDIS_URL in .env", file=sys.stderr)
        return 1

    if "--clear" in argv:
        deleted = engine.clear()
        print(f"Cleared index and deleted {deleted} clip keys")
        return 0

    path = Path(argv[1]) if len(argv) > 1 else None
    count = engine.ingest_clips(path)
    info = engine.index_info()
    print(f"Loaded {count} clips. Index '{info.get('name')}' has {info.get('num_docs')} docs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
