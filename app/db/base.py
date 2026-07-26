"""Metadata target for Alembic.

Importing `app.models` pulls in every model, so `Base.metadata` is complete
by the time autogenerate inspects it.
"""

from app.models import Base

__all__ = ["Base"]
