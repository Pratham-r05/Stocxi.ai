"""Vercel serverless entrypoint that exposes the FastAPI app."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from main import app
