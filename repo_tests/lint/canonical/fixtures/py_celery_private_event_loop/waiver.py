import asyncio

from celery import shared_task


async def body():
    return 1


@shared_task
def waived():
    return asyncio.run(body())  # canonical: ignore py-celery-private-event-loop
