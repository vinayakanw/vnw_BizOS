"""Run the background scheduler as its own process:  python -m app.worker

Use this in production instead of starting the scheduler inside the API (set RUN_SCHEDULER_IN_API=false on the API).
Run exactly one worker. Overlap is harmless (each workflow runs once per lead) but wasteful.
"""

import asyncio
import logging

from app.automation import scheduler
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def main() -> None:
    if settings.scheduler_interval_seconds <= 0:
        raise SystemExit("SCHEDULER_INTERVAL_SECONDS is 0, the worker has nothing to do")
    asyncio.run(scheduler.loop())


if __name__ == "__main__":
    main()
