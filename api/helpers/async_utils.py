# async_utils.py
import asyncio
import threading

# Create a background event loop and start it in a thread
_loop = asyncio.new_event_loop()

def _start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

_thread = threading.Thread(target=_start_loop, args=(_loop,), daemon=True)
_thread.start()


def run_async(coro):
    """
    Submit a coroutine to the persistent background loop and wait synchronously.
    """
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result()
