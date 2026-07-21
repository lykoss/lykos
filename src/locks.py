import asyncio

__all__ = ["join_timer", "reaper"]

join_timer = asyncio.Lock()
reaper = asyncio.Lock()
wait = asyncio.Lock()
