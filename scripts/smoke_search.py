"""Run a few hybrid searches against the live index and print the top hits.

    .venv/bin/python scripts/smoke_search.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.search_engine import get_search_engine  # noqa: E402

QUERIES = [
    ("a dinosaur escaping during a thunderstorm", {}),
    ("two men talking in a diner late at night", {}),
    ("someone dancing down a long staircase", {}),
    ("astronauts facing a giant wave", {"fusion": "LINEAR", "vector_weight": 0.8}),
    ("kiss in the rain", {"genre": "romance"}),
    ("a chase with cars and explosions", {"year_from": 2000, "year_to": 2020}),
]


def main() -> int:
    engine = get_search_engine()
    if not engine.check_connection():
        print("Redis not reachable", file=sys.stderr)
        return 1
    print("index:", engine.index_info())
    for query, opts in QUERIES:
        out = engine.hybrid_search(query, num_results=3, **opts)
        print(f"\n>> {query!r} {opts or ''}  [{out['backend']}, {out['fusion']}]")
        for r in out["results"]:
            print(
                f"   #{r['rank']} {r['title']} - {r['movie']} ({r['year']}) [{r['genre']}]"
                f"  hybrid={r['hybrid_score']} vsim={r['vector_similarity']} text={r['text_score']}"
            )
    print("\ngenres:", engine.genres())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
