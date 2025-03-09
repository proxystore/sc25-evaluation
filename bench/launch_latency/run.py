from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from proxystore.utils.timer import Timer

from aeris.logging import init_logging
from aeris.manager import Manager
from bench.argparse import add_general_options
from bench.argparse import add_launcher_groups
from bench.launch_latency.actor import AerisActor
from bench.launch_latency.actor import DaskActor
from bench.launch_latency.actor import RayActor
from bench.launch_latency.utils import Result
from bench.launch_latency.utils import Times
from bench.launcher import DaskClient
from bench.launcher import get_launcher_config_from_args
from bench.launcher import is_aeris_launcher
from bench.launcher import is_dask_launcher
from bench.launcher import is_ray_launcher
from bench.launcher import LauncherConfig
from bench.launcher import RayClient
from bench.results import CSVResultLogger

logger = logging.getLogger(__name__)


def run_benchmark_aeris(num_actors: int, manager: Manager) -> Times:
    logger.info('Submitting %d actors...', num_actors)
    with Timer() as submit_timer:
        handles = [manager.launch(AerisActor()) for _ in range(num_actors)]
    logger.info('Submitted actors in %.3fs', submit_timer.elapsed_s)

    logger.info('Pinging all actors...')
    with Timer() as ping_timer:
        for handle in handles:
            handle.action('noop').result(timeout=30)
    logger.info('Pinged all actors in %.3fs', ping_timer.elapsed_s)

    logger.info('Shutting down all actors...')
    with Timer() as shutdown_timer:
        for handle in handles:
            handle.shutdown()
        for handle in handles:
            manager.wait(handle.agent_id)
    logger.info('Shutdown all actors in %.3fs', shutdown_timer.elapsed_s)

    times = Times(
        startup=submit_timer.elapsed_s + ping_timer.elapsed_s,
        shutdown=shutdown_timer.elapsed_s,
    )
    return times


def run_benchmark_dask(num_actors: int, client: DaskClient) -> Times:
    logger.info('Submitting %d actors...', num_actors)
    with Timer() as submit_timer:
        handles = [
            client.submit(DaskActor, actor=True) for _ in range(num_actors)
        ]
    logger.info('Submitted actors in %.3fs', submit_timer.elapsed_s)

    logger.info('Pinging all actors...')
    with Timer() as ping_timer:
        for handle in handles:
            actor = handle.result()
            actor.noop().result(timeout=30)
    logger.info('Pinged all actors in %.3fs', ping_timer.elapsed_s)

    logger.info('Shutting down all actors...')
    with Timer() as shutdown_timer:
        for handle in handles:
            client.cancel(handle)
            handle.exception()
    logger.info('Shutdown all actors in %.3fs', shutdown_timer.elapsed_s)

    times = Times(
        startup=submit_timer.elapsed_s + ping_timer.elapsed_s,
        shutdown=shutdown_timer.elapsed_s,
    )
    return times


def run_benchmark_ray(num_actors: int, client: RayClient) -> Times:
    logger.info('Submitting %d actors...', num_actors)
    with Timer() as submit_timer:
        handles = [
            RayActor.remote()
            for _ in range(num_actors)  # type: ignore[attr-defined]
        ]
    logger.info('Submitted actors in %.3fs', submit_timer.elapsed_s)

    logger.info('Pinging all actors...')
    with Timer() as ping_timer:
        for handle in handles:
            ref = handle.noop.remote()
            client.get(ref, timeout=30)
    logger.info('Pinged all actors in %.3fs', ping_timer.elapsed_s)

    logger.info('Shutting down all actors...')
    with Timer() as shutdown_timer:
        for handle in handles:
            client.kill(handle)
    logger.info('Shutdown all actors in %.3fs', shutdown_timer.elapsed_s)

    times = Times(
        startup=submit_timer.elapsed_s + ping_timer.elapsed_s,
        shutdown=shutdown_timer.elapsed_s,
    )
    return times


def run_benchmark(num_actors: int, launcher: Any) -> Times:
    if is_aeris_launcher(launcher):
        return run_benchmark_aeris(num_actors, launcher)
    elif is_dask_launcher(launcher):
        return run_benchmark_dask(num_actors, launcher)
    elif is_ray_launcher(launcher):
        return run_benchmark_ray(num_actors, launcher)
    else:
        raise TypeError(f'Unsupported launcher type: {type(launcher)}.')


def run(
    *,
    launcher_config: LauncherConfig[Any],
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
        if is_aeris_launcher(launcher):
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
            for i in range(repeat):
                times = run_benchmark(num_actors, launcher)
                result = Result(
                    framework='aeris',
                    num_nodes=num_nodes,
                    num_workers_per_node=num_workers_per_node,
                    num_actors=num_actors,
                    startup_time=times.startup,
                    shutdown_time=times.shutdown,
                )
                result_logger.log(result)
                logger.info('Result %d/%d: %s', i + 1, repeat, result)
        logger.info('Saved results to %s', result_logger.filepath)

    timer.stop()
    logger.info('Completed benchmark in %.3fs', timer.elapsed_s)


def main(argv: Sequence[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    add_general_options(parser)
    add_launcher_groups(parser, argv, required=True)
    args = parser.parse_args(argv)

    run_dir = os.path.join(
        args.run_dir,
        'launch-latency',
        datetime.now().strftime('%Y-%m-%d-%H-%M-%S'),
    )
    init_logging(
        level=args.log_level,
        logfile=os.path.join(run_dir, 'log.txt'),
    )

    launcher_config = get_launcher_config_from_args(args, run_dir)

    run(
        launcher_config=launcher_config,
        num_nodes=args.num_nodes,
        num_workers_per_node=args.workers_per_node,
        repeat=args.repeat,
        run_dir=run_dir,
    )

    return 0
