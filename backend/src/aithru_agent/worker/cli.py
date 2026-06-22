from __future__ import annotations

import argparse
import asyncio
from typing import Sequence

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRun
from aithru_agent.settings import AgentSettings

from .service import AgentWorkerLoopPolicy


async def run_worker_once(settings: AgentSettings | None = None) -> AgentRun | None:
    runtime = create_agent_runtime(settings=settings)
    return await runtime.worker.work_once()


async def drain_worker(
    *,
    settings: AgentSettings | None = None,
    limit: int | None = None,
) -> list[AgentRun]:
    runtime = create_agent_runtime(settings=settings)
    return await runtime.worker.drain(limit=limit)


async def loop_worker(
    *,
    settings: AgentSettings | None = None,
    limit: int | None = None,
    poll_interval_seconds: float = 1.0,
    idle_timeout_seconds: float | None = None,
) -> list[AgentRun]:
    runtime = create_agent_runtime(settings=settings)
    return await runtime.worker.run_loop(
        policy=AgentWorkerLoopPolicy(
            poll_interval_seconds=poll_interval_seconds,
            idle_timeout_seconds=idle_timeout_seconds,
        ),
        limit=limit,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aithru-agent-worker")
    parser.add_argument("--once", action="store_true", help="Process at most one queued run.")
    parser.add_argument("--loop", action="store_true", help="Keep polling for queued or retry-ready runs.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum queued runs to drain.")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Seconds to wait between idle loop polls.")
    parser.add_argument("--idle-timeout", type=float, default=None, help="Stop loop after this many idle seconds.")
    parser.add_argument("--sqlite-path", default=None, help="Use SQLite persistence at this path.")
    args = parser.parse_args(argv)

    settings = _settings_from_args(args)
    if args.once:
        run = asyncio.run(run_worker_once(settings))
        if run is None:
            print("no queued runs")
        else:
            print(f"processed {run.id} status={run.status}")
        return 0

    if args.loop:
        runs = asyncio.run(
            loop_worker(
                settings=settings,
                limit=args.limit,
                poll_interval_seconds=args.poll_interval,
                idle_timeout_seconds=args.idle_timeout,
            )
        )
        print(f"processed {len(runs)} run(s)")
        return 0

    runs = asyncio.run(drain_worker(settings=settings, limit=args.limit))
    print(f"processed {len(runs)} run(s)")
    return 0


def _settings_from_args(args: argparse.Namespace) -> AgentSettings:
    settings = AgentSettings.from_env()
    if args.sqlite_path:
        return settings.model_copy(
            update={"persistence_backend": "sqlite", "sqlite_path": args.sqlite_path},
        )
    return settings
