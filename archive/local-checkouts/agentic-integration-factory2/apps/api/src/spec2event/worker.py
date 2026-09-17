from __future__ import annotations

import time

from redis import Redis
from rq import Worker

from spec2event.config import get_settings


def main() -> None:
    settings = get_settings()
    if settings.enable_rq:
        connection = Redis.from_url(settings.redis_url)
        worker = Worker(["spec2event"], connection=connection)
        worker.work()
    else:
        print("ENABLE_RQ is false; in-process job execution is active.")
        while True:
            time.sleep(60)


if __name__ == "__main__":
    main()
