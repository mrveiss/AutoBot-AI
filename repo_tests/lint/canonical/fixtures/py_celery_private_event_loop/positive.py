import asyncio
import asyncio as aio
from asyncio import new_event_loop
from asyncio import run as r

import anyio
from asgiref.sync import async_to_sync
from celery import shared_task

from autobot_shared.async_compat import run_or_schedule


async def body():
    return 1


@shared_task
def every_spelling():
    asyncio.run(body())  # 1
    aio.run(body())  # 2 (module alias)
    r(body())  # 3 (from-import alias)
    loop = new_event_loop()  # 4
    loop.run_until_complete(body())  # 5
    asyncio.get_event_loop()  # 6
    asyncio.set_event_loop(None)  # 7
    asyncio.Runner()  # 8
    anyio.run(body)  # 9
    async_to_sync(body)()  # 10
    run_or_schedule(body())  # 11
