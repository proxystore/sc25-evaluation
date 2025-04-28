from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
import time
from collections.abc import Sequence
from concurrent.futures import FIRST_EXCEPTION
from concurrent.futures import Future
from concurrent.futures import wait
from datetime import datetime
from typing import Any
from typing import NamedTuple

import ray
from academy.logging import init_logging
from academy.manager import Manager
from dask.distributed import wait as dask_wait
from proxystore.utils.timer import Timer

from bench.action_throughput.actor import AerisActor
from bench.action_throughput.actor import DaskActor
from bench.action_throughput.actor import RayActor
from bench.argparse import add_general_options
from bench.argparse import add_launcher_groups
from bench.launcher import DaskClient
from bench.launcher import get_launcher_config_from_args
from bench.launcher import is_academy_launcher
from bench.launcher import is_dask_launcher
from bench.launcher import is_ray_launcher
from bench.launcher import LauncherConfig
from bench.launcher import RayClient
from bench.results import CSVResultLogger

logger = logging.getLogger(__name__)


class Result(NamedTuple):
    framework: str
    actions_per_actor: int
    action_sleep: int
    num_nodes: int
    num_workers_per_node: int
    num_actors: int
    runtime: float


def run_benchmark_academy(
    num_actors: int,
    actions_per_actor: int,
    action_sleep: int,
    repeat: int,
    manager: Manager,
) -> list[float]:
    logger.info('Submitting %d actors...', num_actors)
    with Timer() as submit_timer:
        handles = [manager.launch(AerisActor()) for _ in range(num_actors)]
    logger.info('Submitted actors in %.3fs', submit_timer.elapsed_s)

    logger.warning('Waiting 12 seconds...')
    time.sleep(10)

    logger.info('Pinging all actors...')
    with Timer() as ping_timer:
        ops = [handle.action('noop') for handle in handles]
        for op in ops:
            op.result(timeout=60)
    logger.info('Pinged all actors in %.3fs', ping_timer.elapsed_s)

    runtimes: list[float] = []
    for i in range(repeat):
        logger.info('Submitting bag of tasks %d/%d...', i + 1, repeat)
        futures: Future[None] = []
        with Timer() as bag_timer:
            for _ in range(actions_per_actor):
                for handle in handles:
                    futures.append(handle.action('noop', action_sleep))
            wait(futures, return_when=FIRST_EXCEPTION)
            for future in futures:
                if future.exception() is not None:
                    raise future.exception()
        logger.info('Finished bag of tasks in %.3fs', bag_timer.elapsed_s)
        runtimes.append(bag_timer.elapsed_s)

    logger.info('Shutting down all actors...')
    with Timer() as shutdown_timer:
        for handle in handles:
            handle.shutdown()
        for handle in handles:
            manager.wait(handle.agent_id)
    logger.info('Shutdown all actors in %.3fs', shutdown_timer.elapsed_s)

    return runtimes


def run_benchmark_dask(
    num_actors: int,
    actions_per_actor: int,
    action_sleep: int,
    repeat: int,
    client: DaskClient,
) -> list[float]:
    logger.info('Submitting %d actors...', num_actors)
    with Timer() as submit_timer:
        handles = [
            client.submit(DaskActor, actor=True) for _ in range(num_actors)
        ]
    logger.info('Submitted actors in %.3fs', submit_timer.elapsed_s)

    logger.info('Pinging all actors...')
    with Timer() as ping_timer:
        ops = [handle.result().noop() for handle in handles]
        for op in ops:
            op.result(timeout=30)
    logger.info('Pinged all actors in %.3fs', ping_timer.elapsed_s)

    runtimes: list[float] = []
    for i in range(repeat):
        logger.info('Submitting bag of tasks %d/%d...', i + 1, repeat)
        futures = []
        with Timer() as bag_timer:
            for _ in range(actions_per_actor):
                for handle in handles:
                    futures.append(handle.result().noop(action_sleep))
            dask_wait(futures)
            for future in futures:
                future.result()
        logger.info('Finished bag of tasks in %.3fs', bag_timer.elapsed_s)
        runtimes.append(bag_timer.elapsed_s)

    logger.info('Shutting down all actors...')
    with Timer() as shutdown_timer:
        for handle in handles:
            client.cancel(handle)
        for handle in handles:
            handle.exception()
    logger.info('Shutdown all actors in %.3fs', shutdown_timer.elapsed_s)

    return runtimes


def run_benchmark_ray(
    num_actors: int,
    actions_per_actor: int,
    action_sleep: int,
    repeat: int,
    client: RayClient,
) -> list[float]:
    logger.info('Submitting %d actors...', num_actors)
    with Timer() as submit_timer:
        handles = [
            RayActor.options(max_concurrency=1).remote()
            for _ in range(num_actors)  # type: ignore[attr-defined]
        ]
    logger.info('Submitted actors in %.3fs', submit_timer.elapsed_s)

    logger.info('Pinging all actors...')
    with Timer() as ping_timer:
        ops = [handle.noop.remote() for handle in handles]
        for op in ops:
            client.get(op, timeout=30)
    logger.info('Pinged all actors in %.3fs', ping_timer.elapsed_s)

    runtimes: list[float] = []
    for i in range(repeat):
        logger.info('Submitting bag of tasks %d/%d...', i + 1, repeat)
        ops = []
        with Timer() as bag_timer:
            for _ in range(actions_per_actor):
                for handle in handles:
                    ops.append(handle.noop.remote(action_sleep))
            ray.wait(ops)
            for op in ops:
                client.get(op)
        logger.info('Finished bag of tasks in %.3fs', bag_timer.elapsed_s)
        runtimes.append(bag_timer.elapsed_s)

    logger.info('Shutting down all actors...')
    with Timer() as shutdown_timer:
        refs = [handle.exit.remote() for handle in handles]
        for ref in refs:
            with contextlib.suppress(ray.exceptions.RayActorError):
                client.get(ref)
    logger.info('Shutdown all actors in %.3fs', shutdown_timer.elapsed_s)

    return runtimes


def run_benchmark(
    num_actors: int,
    actions_per_actor: int,
    action_sleep: int,
    repeat: int,
    launcher: Any,
) -> list[float]:
    if is_academy_launcher(launcher):
        return run_benchmark_academy(
            num_actors,
            actions_per_actor,
            action_sleep,
            repeat,
            launcher,
        )
    elif is_dask_launcher(launcher):
        return run_benchmark_dask(
            num_actors,
            actions_per_actor,
            action_sleep,
            repeat,
            launcher,
        )
    elif is_ray_launcher(launcher):
        return run_benchmark_ray(
            num_actors,
            actions_per_actor,
            action_sleep,
            repeat,
            launcher,
        )
    else:
        raise TypeError(f'Unsupported launcher type: {type(launcher)}.')


def run(
    *,
    launcher_config: LauncherConfig[Any],
    actions_per_actor: int,
    action_sleep: float,
    num_nodes: int,
    num_workers_per_node: int,
    repeat: int,
    run_dir: str,
) -> None:
    timer = Timer().start()
    logger.info('Starting benchmark...')

    num_actors = num_nodes * num_workers_per_node

    with launcher_config.get_launcher() as launcher:
        logger.info('Running warmup task on launcher...')
        if is_academy_launcher(launcher):
            launcher.launcher._executor.submit(sum, [1, 2, 3]).result()
        elif is_dask_launcher(launcher):
            launcher.submit(sum, [1, 2, 3]).result()
        elif is_ray_launcher(launcher):
            ref = launcher.remote(lambda x: sum(x)).remote([1, 2, 3])
            launcher.get(ref)
        else:
            raise TypeError(f'Unsupported launcher type: {type(launcher)}.')
        logger.info('Warmup task completed')

        with CSVResultLogger(
            os.path.join(run_dir, 'results.csv'),
            Result,
        ) as result_logger:
            runtimes = run_benchmark(
                num_actors,
                actions_per_actor,
                action_sleep,
                repeat,
                launcher,
            )
            for runtime in runtimes:
                result = Result(
                    framework=launcher_config.name,
                    actions_per_actor=actions_per_actor,
                    action_sleep=action_sleep,
                    num_nodes=num_nodes,
                    num_workers_per_node=num_workers_per_node,
                    num_actors=num_actors,
                    runtime=runtime,
                )
                result_logger.log(result)
        logger.info('Saved results to %s', result_logger.filepath)

    timer.stop()
    logger.info('Completed benchmark in %.3fs', timer.elapsed_s)


def main(argv: Sequence[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--actions-per-actor',
        type=int,
        required=True,
        help='number of actions per worker',
    )
    parser.add_argument(
        '--action-sleep',
        default=0,
        type=float,
        help='action sleep',
    )
    add_general_options(parser)
    add_launcher_groups(parser, argv, required=True)
    args = parser.parse_args(argv)

    run_dir = os.path.join(
        args.run_dir,
        'action-throughput',
        datetime.now().strftime('%Y-%m-%d-%H-%M-%S'),
    )
    init_logging(
        level=args.log_level,
        logfile=os.path.join(run_dir, 'log.txt'),
        color=False,
        extra=False,
    )

    logger.info('Args: %s', vars(args))
    launcher_config = get_launcher_config_from_args(args, run_dir)

    run(
        launcher_config=launcher_config,
        actions_per_actor=args.actions_per_actor,
        action_sleep=args.action_sleep,
        num_nodes=args.num_nodes,
        num_workers_per_node=args.workers_per_node,
        repeat=args.repeat,
        run_dir=run_dir,
    )

    return 0
