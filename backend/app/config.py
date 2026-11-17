"""Central settings. Everything else imports paths and the fixed 'today' from here."""
from datetime import date
from pathlib import Path
import os

BACKEND_DIR = Path(__file__).resolve().parent.parent
ARCHITECTURE_DIR = BACKEND_DIR.parent / "architecture"   # architecture diagrams served at /architecture


def _load_env_file(path: Path) -> None:
    """Read KEY=value lines from backend/.env into the environment (no extra dependency).
    Real environment variables win over the file."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(BACKEND_DIR / ".env")

DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw"          # what the "source systems" export (messy)
DOCS_DIR = DATA_DIR / "docs"        # unstructured documents
DB_PATH = DATA_DIR / "briefing.db"  # clean warehouse built by ingestion
AUDIT_DIR = DATA_DIR / "audit"
EVAL_DIR = BACKEND_DIR / "eval"

# The demo world is frozen on this date so results are reproducible.
TODAY = date(2026, 11, 16)

# Vector search. Embeddings run locally (no API key; document text never leaves the machine).
MODELS_DIR = DATA_DIR / "models"
EMBED_PROVIDER = os.environ.get("EMBED_PROVIDER", "local")   # local | voyage
EMBED_MODEL = "BAAI/bge-small-en-v1.5"   # local model: 384-dim, ~70 MB ONNX
VOYAGE_EMBED_MODEL = os.environ.get("VOYAGE_EMBED_MODEL", "voyage-finance-2")

# Reranking: hybrid search picks RERANK_CANDIDATES chunks, then a cross-encoder (reads question and chunk
# together) reorders them. Runs locally via fastembed. Decided by measurement (eval/retrieval.py):
#   - briefing agents gather SETS of passages: recall matters and they run ~15 searches -> no reranker
#     (hybrid recall@5 0.989 vs 0.955 with reranker; 25 ms vs ~1.3 s per search)
#   - chat answers ONE question: the best passage first matters -> reranker on
#     (hit@1 0.955 vs 0.864; one extra second next to a ~10 s answer)
RERANK_ENABLED = os.environ.get("RERANK", "0") == "1"          # default for agents
CHAT_RERANK = os.environ.get("CHAT_RERANK", "1") == "1"        # chat follow-up questions
RERANK_MODEL = os.environ.get("RERANK_MODEL", "jinaai/jina-reranker-v1-turbo-en")
RERANK_CANDIDATES = 20

# News: two items are the same story if same client, within this many days, and this similar
NEWS_STORY_WINDOW_DAYS = 7
NEWS_SAME_STORY_SIM = 0.85

# Chunking: max words per chunk (~300 tokens, well under the 512-token limit of the local model)
CHUNK_MAX_WORDS = 220
# Empty = in-process Qdrant (prototype). In production point this at a Qdrant server, e.g. http://qdrant:6333
QDRANT_URL = os.environ.get("QDRANT_URL", "")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# Entity-resolution thresholds (deterministic code, not the LLM).
AUTO_MERGE_THRESHOLD = 0.90
REVIEW_THRESHOLD = 0.70

# LLM settings. With no key the system runs in offline (rule-based) mode.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_MODE = os.environ.get("LLM_MODE", "auto")  # auto | offline | anthropic

# Browser origins allowed to call the API (the Next.js dev server).
FRONTEND_ORIGINS = os.environ.get(
    "FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")


def resolved_llm_mode() -> str:
    """'anthropic' only when asked for (or auto) and a key exists; otherwise 'offline'."""
    if LLM_MODE == "offline":
        return "offline"
    return "anthropic" if ANTHROPIC_API_KEY else "offline"
