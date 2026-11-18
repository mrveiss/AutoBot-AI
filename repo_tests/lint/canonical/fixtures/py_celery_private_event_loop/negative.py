"""asyncio.run(body()) and new_event_loop() mentioned in a docstring are not calls."""

import asyncio

from celery import shared_task

from autobot_shared.worker_loop import run_in_worker_loop


async def body():
    await asyncio.sleep(0)  # asyncio.run(body()) in a comment
    return "asyncio.run(body())"


@shared_task
def uses_the_worker_loop():
    return run_in_worker_loop(body())
