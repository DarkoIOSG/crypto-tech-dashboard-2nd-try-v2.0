"""Vercel serverless entry point.

Vercel's @vercel/python builder looks for a module-level `app` (ASGI) or
`handler` (WSGI) object. We expose the FastAPI ASGI app from main_api.py.

All traffic is routed here by vercel.json. The app serves both:
  - /api/*          — backend API endpoints
  - /               — frontend SPA (index.html)
  - /login.html     — access-gate page
  - /css, /js, /lib — static assets
"""

import sys
from pathlib import Path

# Make the project root (crypto-tech-dashboard/) importable as a package root,
# regardless of where Vercel runs this file from.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.main_api import app  # noqa: E402 — intentional late import

__all__ = ["app"]
