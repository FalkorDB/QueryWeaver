"""Off-loop embedding helpers.

``EmbeddingsModel.embed`` and ``get_vector_size`` are blocking network calls.
Called directly from an async method they block the event loop, which stops
every open stream from flushing keepalives — the same failure mode as the
analysis and SQL-execution stages in the 2026-07-29 incident. Async callers go
through these helpers so the offload (and the timeout bounds inside the model)
apply in one place.
"""

import asyncio
from typing import List, Union

from api.config import Config


async def embed_off_loop(text: Union[str, list]) -> List[List[float]]:
    """Embed *text* in a worker thread. Returns one vector per input."""
    return await asyncio.to_thread(Config.EMBEDDING_MODEL.embed, text)


async def embed_one_off_loop(text: str) -> List[float]:
    """Embed a single string in a worker thread and return its vector."""
    vectors = await embed_off_loop(text)
    return vectors[0]


async def vector_size_off_loop() -> int:
    """Probe the embedding dimensionality in a worker thread."""
    return await asyncio.to_thread(Config.EMBEDDING_MODEL.get_vector_size)
