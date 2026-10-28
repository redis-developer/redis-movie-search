"""
FastAPI backend for the Video Clip Searcher.

    GET  /api/health   Redis + index status
    GET  /api/genres   distinct genre tags for the filter dropdown
    POST /api/search   hybrid text + vector search over clip descriptions
    POST /api/ingest   embed resources/clips.json and build the index
    POST /api/clear    drop the index and delete clip:* keys
"""
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from redis import Redis

from .config import (
    DEFAULT_FUSION,
    DEFAULT_NUM_RESULTS,
    DEFAULT_VECTOR_WEIGHT,
    MAX_NUM_RESULTS,
    REDIS_URL,
)
from .search_engine import VideoClipSearchEngine, get_search_engine

app = FastAPI(
    title="Video Clip Searcher API",
    description="Describe a scene; Redis hybrid search (BM25 + vector) finds the clip.",
    version="1.0.0",
)


def _allowed_origins() -> List[str]:
    origins = ["http://localhost:5173", "http://localhost:3000"]
    codespace = os.getenv("CODESPACE_NAME")
    if codespace:
        origins += [f"https://{codespace}-{port}.app.github.dev" for port in (5173, 3000, 8000)]
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------- models

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language description of the scene")
    num_results: int = Field(DEFAULT_NUM_RESULTS, ge=1, le=MAX_NUM_RESULTS)
    genre: Optional[str] = Field(None, description="Genre tag filter, e.g. action")
    year_from: Optional[int] = Field(None, ge=1900, le=2100)
    year_to: Optional[int] = Field(None, ge=1900, le=2100)
    fusion: str = Field(DEFAULT_FUSION, pattern="^(?i)(rrf|linear)$", description="RRF or LINEAR")
    vector_weight: float = Field(
        DEFAULT_VECTOR_WEIGHT, ge=0.0, le=1.0,
        description="LINEAR only: 1 = pure vector similarity, 0 = pure BM25 text",
    )


class ClipResult(BaseModel):
    rank: int
    id: str
    title: str
    movie: str
    year: Optional[int] = None
    genre: str
    director: str = ""
    duration_seconds: Optional[int] = None
    description: str
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    hybrid_score: Optional[float] = None
    text_score: Optional[float] = None
    vector_similarity: Optional[float] = None


class SearchResponse(BaseModel):
    query: str
    results: List[ClipResult]
    count: int
    backend: str
    fusion: str
    took_ms: int


class HealthResponse(BaseModel):
    status: str
    redis_connected: bool
    index_exists: bool
    index_info: Dict[str, Any]


# ------------------------------------------------------------------ helpers

def _engine() -> VideoClipSearchEngine:
    try:
        return get_search_engine()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Search engine unavailable: {exc}") from exc


# ---------------------------------------------------------------- endpoints

@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health() -> HealthResponse:
    redis_connected = False
    try:
        redis_connected = bool(Redis.from_url(REDIS_URL, socket_connect_timeout=2.0).ping())
    except Exception:  # noqa: BLE001
        redis_connected = False

    index_exists, index_info = False, {}
    if redis_connected:
        try:
            engine = get_search_engine()
            index_exists = engine.index_exists()
            index_info = engine.index_info() if index_exists else {"hint": "Run POST /api/ingest"}
        except Exception as exc:  # noqa: BLE001
            index_info = {"error": str(exc)}

    status = "healthy" if redis_connected and index_exists else "degraded" if redis_connected else "unhealthy"
    return HealthResponse(
        status=status, redis_connected=redis_connected, index_exists=index_exists, index_info=index_info
    )


@app.get("/api/genres", tags=["Search"])
async def genres() -> Dict[str, List[str]]:
    return {"genres": _engine().genres()}


@app.post("/api/search", response_model=SearchResponse, tags=["Search"])
async def search(request: SearchRequest) -> SearchResponse:
    """Hybrid search: BM25 over clip text fused with cosine KNN over embeddings."""
    engine = _engine()
    if not engine.index_exists():
        raise HTTPException(status_code=409, detail="Index not found. Run POST /api/ingest first.")

    started = time.perf_counter()
    try:
        out = engine.hybrid_search(
            query=request.query,
            num_results=request.num_results,
            genre=request.genre,
            year_from=request.year_from,
            year_to=request.year_to,
            fusion=request.fusion,
            vector_weight=request.vector_weight,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}") from exc

    return SearchResponse(
        query=request.query,
        results=out["results"],
        count=len(out["results"]),
        backend=out["backend"],
        fusion=out["fusion"],
        took_ms=int((time.perf_counter() - started) * 1000),
    )


@app.post("/api/ingest", tags=["Admin"])
async def ingest() -> Dict[str, Any]:
    """Embed resources/clips.json, write clip:* hashes and build the index."""
    try:
        count = _engine().ingest_clips()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Ingest failed: {exc}") from exc
    return {"status": "success", "clips_loaded": count}


@app.post("/api/clear", tags=["Admin"])
async def clear() -> Dict[str, Any]:
    """Drop the index and delete every clip hash."""
    try:
        deleted = _engine().clear()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Clear failed: {exc}") from exc
    return {"status": "success", "keys_deleted": deleted}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
