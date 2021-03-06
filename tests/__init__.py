# -*- coding: utf-8 -*-

import asyncio
import atexit


def async_test(f):

    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        coro = asyncio.coroutine(f)
        loop.run_until_complete(coro(*args, **kwargs))

    return wrapper


def close_loop():
    try:
        asyncio.get_event_loop().close()
    except (AttributeError, RuntimeError, SystemError):
        pass


atexit.register(close_loop)
