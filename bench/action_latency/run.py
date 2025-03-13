from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from typing import NamedTuple

import ray
from proxystore.utils.data import readable_to_bytes
from proxystore.utils.timer import Timer

from aeris.logging import init_logging
from aeris.manager import Manager
from bench.action_latency.actor import AerisReplyActor
from bench.action_latency.actor import AerisRequestActor
from bench.action_latency.actor import DaskReplyActor
from bench.action_latency.actor import DaskRequestActor
from bench.action_latency.actor import RayReplyActor
from bench.action_latency.actor import RayRequestActor
from bench.argparse import add_general_options
from bench.argparse import add_launcher_groups
from bench.launcher import DaskClient
from bench.launcher import get_launcher_config_from_args
from bench.launcher import is_aeris_launcher
from bench.launcher import is_dask_launcher
from bench.launcher import is_ray_launcher
from bench.launcher import LauncherConfig
from bench.launcher import RayClient
from bench.results import CSVResultLogger

logger = logging.getLogger(__name__)


class Result(NamedTuple):
    framework: str
    trials: int
    data_size_bytes: int
    mean_latency_s: float
    stdev_latency_s: float


def run_benchmark_aeris(
    manager: Manager,
    data_sizes: list[int],
    repeat: int,
    result_logger: CSVResultLogger,
) -> None:
    logger.info('Starting actors...')
    reply_handle = manager.launch(AerisReplyActor())
    request_handle = manager.launch(AerisRequestActor(reply_handle))
    # reply_handle.action('noop').result(timeout=30)
    # request_handle.action('noop').result(timeout=30)
    logger.info('Started actors')

    for data_size in data_sizes:
        logger.info(
            'Running with %d bytes for %d trials...',
            data_size,
            repeat,
        )
        with Timer() as timer:
            future = request_handle.action(
                'run',
                size=data_size,
                trials=repeat,
            )
            mean, std = future.result()
        result = Result(
            framework='aeris',
            trials=repeat,
            data_size_bytes=data_size,
            mean_latency_s=mean,
            stdev_latency_s=std,
        )
        result_logger.log(result)
        logger.info('Completed in %fs: %s', timer.elapsed_s, result)

    logger.info('Shutting down all actors...')
    request_handle.shutdown()
    reply_handle.shutdown()
    manager.wait(request_handle.agent_id)
    manager.wait(reply_handle.agent_id)
    logger.info('Shutdown all actors')


def run_benchmark_dask(
    client: DaskClient,
    data_sizes: list[int],
    repeat: int,
    result_logger: CSVResultLogger,
) -> None:
    logger.info('Starting actors...')
    reply_future = client.submit(DaskReplyActor, actor=True)
    request_future = client.submit(DaskRequestActor, reply_future, actor=True)
    reply_handle = reply_future.result()
    request_handle = request_future.result()
    reply_handle.noop().result(timeout=30)
    request_handle.noop().result(timeout=30)
    logger.info('Started actors')

    for data_size in data_sizes:
        logger.info(
            'Running with %d bytes for %d trials...',
            data_size,
            repeat,
        )
        with Timer() as timer:
            future = request_handle.run(size=data_size, trials=repeat)
            mean, std = future.result()
        result = Result(
            framework='dask',
            trials=repeat,
            data_size_bytes=data_size,
            mean_latency_s=mean,
            stdev_latency_s=std,
        )
        result_logger.log(result)
        logger.info('Completed in %fs: %s', timer.elapsed_s, result)

    logger.info('Shutting down all actors...')
    client.cancel(reply_future)
    client.cancel(request_future)
    reply_future.exception()
    request_future.exception()
    logger.info('Shutdown all actors')


def run_benchmark_ray(
    client: RayClient,
    data_sizes: list[int],
    repeat: int,
    result_logger: CSVResultLogger,
) -> None:
    logger.info('Starting actors...')
    reply_actor = RayReplyActor.remote()
    request_actor = RayRequestActor.remote(reply_actor)
    client.get(reply_actor.noop.remote(), timeout=30)
    client.get(request_actor.noop.remote(), timeout=30)
    logger.info('Started actors')

    for data_size in data_sizes:
        logger.info(
            'Running with %d bytes for %d trials...',
            data_size,
            repeat,
        )
        with Timer() as timer:
            ref = request_actor.run.remote(size=data_size, trials=repeat)
            mean, std = client.get(ref)
        result = Result(
            framework='ray',
            trials=repeat,
            data_size_bytes=data_size,
            mean_latency_s=mean,
            stdev_latency_s=std,
        )
        result_logger.log(result)
        logger.info('Completed in %fs: %s', timer.elapsed_s, result)

    logger.info('Shutting down all actors...')
    with contextlib.suppress(ray.exceptions.RayActorError):
        client.get(reply_actor.exit.remote())
        client.get(request_actor.exit.remote())
    logger.info('Shutdown all actors')


def run_benchmark(
    launcher: Any,
    data_sizes: list[int],
    repeat: int,
    result_logger: CSVResultLogger,
) -> None:
    if is_aeris_launcher(launcher):
        return run_benchmark_aeris(launcher, data_sizes, repeat, result_logger)
    elif is_dask_launcher(launcher):
        return run_benchmark_dask(launcher, data_sizes, repeat, result_logger)
    elif is_ray_launcher(launcher):
        return run_benchmark_ray(launcher, data_sizes, repeat, result_logger)
    else:
        raise TypeError(f'Unsupported launcher type: {type(launcher)}.')


def run(
    *,
    launcher_config: LauncherConfig[Any],
    data_sizes: list[int],
    repeat: int,
    run_dir: str,
) -> None:
    timer = Timer().start()
    logger.info('Starting benchmark...')

    with launcher_config.get_launcher() as launcher:
        with CSVResultLogger(
            os.path.join(run_dir, 'results.csv'),
            Result,
        ) as result_logger:
            run_benchmark(launcher, data_sizes, repeat, result_logger)
        logger.info('Saved results to %s', result_logger.filepath)

    timer.stop()
    logger.info('Completed benchmark in %.3fs', timer.elapsed_s)


def main(argv: Sequence[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--data-sizes',
        type=str,
        nargs='+',
        help='data sizes to test',
    )
    add_general_options(parser)
    add_launcher_groups(parser, argv, required=True)
    args = parser.parse_args(argv)

    run_dir = os.path.join(
        args.run_dir,
        'action-latency',
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
        data_sizes=[readable_to_bytes(x) for x in args.data_sizes],
        repeat=args.repeat,
        run_dir=run_dir,
    )

    return 0
