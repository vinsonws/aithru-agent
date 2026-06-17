from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from typing import Sequence

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRun
from aithru_agent.settings import AgentSettings


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aithru-agent-worker")
    parser.add_argument("--once", action="store_true", help="Process at most one queued run.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum queued runs to drain.")
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

    runs = asyncio.run(drain_worker(settings=settings, limit=args.limit))
    print(f"processed {len(runs)} run(s)")
    return 0


def _settings_from_args(args: argparse.Namespace) -> AgentSettings:
    settings = AgentSettings.from_env()
    if args.sqlite_path:
        return replace(settings, persistence_backend="sqlite", sqlite_path=args.sqlite_path)
    return settings
