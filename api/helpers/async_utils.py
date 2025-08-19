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


def run_async(func_or_coro, *args, **kwargs):
    """
    Submit a coroutine or synchronous function to the persistent background loop and wait synchronously.
    If a coroutine object or coroutine function is passed, it is scheduled as a coroutine.
    If a synchronous function is passed, it is run in the loop's executor.
    """
    # If it's a coroutine object, schedule it directly
    if asyncio.iscoroutine(func_or_coro):
        future = asyncio.run_coroutine_threadsafe(func_or_coro, _loop)
        return future.result()
    # If it's a coroutine function, call it with args/kwargs to get the coroutine object
    elif asyncio.iscoroutinefunction(func_or_coro):
        coro = func_or_coro(*args, **kwargs)
        future = asyncio.run_coroutine_threadsafe(coro, _loop)
        return future.result()
    # Otherwise, treat as synchronous function and run in executor
    else:
        future = asyncio.run_coroutine_threadsafe(
            _loop.run_in_executor(None, func_or_coro, *args, **kwargs), _loop
        )
        return future.result()