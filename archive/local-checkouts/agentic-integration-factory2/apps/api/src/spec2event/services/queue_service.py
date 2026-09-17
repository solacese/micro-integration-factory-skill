from __future__ import annotations

import threading

from redis import Redis
from rq import Queue

from spec2event.config import get_settings
from spec2event.services import pipeline


def enqueue_generation(run_id: str, auto_build: bool = False, auto_deploy: bool = False) -> None:
    _enqueue(pipeline.generation_pipeline, run_id, auto_build, auto_deploy)


def enqueue_build(run_id: str) -> None:
    _enqueue(pipeline.build_pipeline, run_id)


def enqueue_deploy(run_id: str) -> None:
    _enqueue(pipeline.deploy_pipeline, run_id)


def _enqueue(function, *args) -> None:
    settings = get_settings()
    if settings.enable_rq:
        queue = Queue("spec2event", connection=Redis.from_url(settings.redis_url))
        queue.enqueue(function, *args)
        return
    thread = threading.Thread(target=function, args=args, daemon=True)
    thread.start()
