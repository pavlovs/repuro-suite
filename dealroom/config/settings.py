from pathlib import Path
import os

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = Path(os.getenv("DEALROOM_DB_PATH", str(DATA_DIR / "dealroom.db")))
GOLDEN_DIR = DATA_DIR / "golden"
GOLDEN_CORPUS_DIR = BASE_DIR / "config" / "golden"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# OneDrive deal folders — already synced locally
DEALS_DIR = Path(
    os.getenv(
        "DEALS_DIR",
        str(
            Path.home()
            / "Documents"
            / "OneDrive - Kamu Kapital"
            / "Dokumente - Kamu Kapital"
            / "3_Deals"
            / "3_Targets"
        ),
    )
)

ALLEX_PIPELINE_DB = Path(
    os.getenv(
        "ALLEX_PIPELINE_DB",
        str(BASE_DIR.parent / "lead-pipeline" / "data" / "pipeline.db"),
    )
)
