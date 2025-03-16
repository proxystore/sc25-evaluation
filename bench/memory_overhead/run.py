from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from typing import NamedTuple

import psutil
from proxystore.utils.timer import Timer

from aeris.logging import init_logging
from aeris.manager import Manager
from bench.argparse import add_general_options
from bench.argparse import add_launcher_groups
from bench.launcher import DaskClient
from bench.launcher import DaskConfig
from bench.launcher import get_launcher_config_from_args
from bench.launcher import is_aeris_launcher
from bench.launcher import is_dask_launcher
from bench.launcher import is_ray_launcher
from bench.launcher import LauncherConfig
from bench.launcher import RayClient
from bench.launcher import RayConfig
from bench.memory_overhead.actor import AerisActor
from bench.memory_overhead.actor import DaskActor
from bench.memory_overhead.actor import RayActor
from bench.results import CSVResultLogger

logger = logging.getLogger(__name__)
SAMPLE_INTERVAL = 1
SAMPLE_COUNT = 5


class Result(NamedTuple):
    framework: str
    timestamp: float
    active_actors: int
    memory_used: float


def get_user_memory() -> float:
    current_user_id = os.getuid()
    total_memory = 0
    for process in psutil.process_iter(['uids', 'memory_info']):
        try:
            if process.info['uids'].real == current_user_id:
                total_memory += process.info['memory_info'].rss
        except psutil.Error:
            pass  # Handle errors like AccessDenied
    return total_memory


def run_benchmark_aeris(
    manager: Manager,
    num_actors: int,
    result_logger: CSVResultLogger,
) -> list[Result]:
    logger.info('Running warmup task...')
    manager.launcher._executor.submit(sum, [1, 2, 3]).result(timeout=60)

    logger.info('Spawning %d actor(s)...', num_actors)
    handles = [manager.launch(AerisActor()) for _ in range(num_actors)]
    for handle in handles:
        handle.action('noop').result(timeout=30)

    logger.info(
        'Samping memory over %.3f seconds...',
        SAMPLE_INTERVAL * SAMPLE_COUNT,
    )
    results: list[Result] = []
    for _ in range(SAMPLE_COUNT):
        result = Result(
            framework=f'AERIS+{type(manager.launcher._executor).__name__}',
            timestamp=time.time(),
            active_actors=num_actors,
            memory_used=get_user_memory(),
        )
        results.append(result)
        time.sleep(SAMPLE_INTERVAL)

    logger.info('Shutting down all actors...')
    for handle in handles:
        handle.shutdown()
    for handle in handles:
        manager.wait(handle.agent_id)
    logger.info('Shutdown all actors')
    return results


def run_benchmark_dask(
    client: DaskClient,
    num_actors: int,
    result_logger: CSVResultLogger,
) -> list[Result]:
    logger.info('Spawning %d actor(s)...', num_actors)
    actor_futures = [
        client.submit(DaskActor, actor=True) for _ in range(num_actors)
    ]
    for future in actor_futures:
        handle = future.result()
        handle.noop().result(timeout=30)

    logger.info(
        'Samping memory over %.3f seconds...',
        SAMPLE_INTERVAL * SAMPLE_COUNT,
    )
    results: list[Result] = []
    for _ in range(SAMPLE_COUNT):
        result = Result(
            framework='Dask',
            timestamp=time.time(),
            active_actors=num_actors,
            memory_used=get_user_memory(),
        )
        results.append(result)
        time.sleep(SAMPLE_INTERVAL)

    logger.info('Shutting down all actors...')
    for future in actor_futures:
        client.cancel(future)
        future.exception()
    logger.info('Shutdown all actors')
    return results


def run_benchmark_ray(
    client: RayClient,
    num_actors: int,
    result_logger: CSVResultLogger,
) -> list[Result]:
    logger.info('Spawning %d actor(s)...', num_actors)
    actor_refs = [
        RayActor.options(
            max_concurrency=1,
            num_cpus=1,
            num_gpus=0,
            memory=int(1e9),
            object_store_memory=int(1e8),
        ).remote()
        for _ in range(num_actors)
    ]
    for ref in actor_refs:
        action = ref.noop.remote()
        client.get(action, timeout=40)

    logger.info(
        'Samping memory over %.3f seconds...',
        SAMPLE_INTERVAL * SAMPLE_COUNT,
    )
    results: list[Result] = []
    for _ in range(SAMPLE_COUNT):
        result = Result(
            framework='Ray',
            timestamp=time.time(),
            active_actors=num_actors,
            memory_used=get_user_memory(),
        )
        results.append(result)
        time.sleep(SAMPLE_INTERVAL)

    # Let cluster shutdown take care of actor shutdown
    # logger.info('Shutting down all actors...')
    # exit_refs = [ref.exit.remote() for ref in actor_refs]
    # for ref in exit_refs:
    #     with contextlib.suppress(ray.exceptions.RayActorError):
    #         client.get(ref)
    # logger.info('Shutdown all actors')
    return results


def run_benchmark(
    launcher: Any,
    num_actors: int,
    result_logger: CSVResultLogger,
) -> list[Result]:
    if is_aeris_launcher(launcher):
        return run_benchmark_aeris(launcher, num_actors, result_logger)
    elif is_dask_launcher(launcher):
        return run_benchmark_dask(launcher, num_actors, result_logger)
    elif is_ray_launcher(launcher):
        return run_benchmark_ray(launcher, num_actors, result_logger)
    else:
        raise TypeError(f'Unsupported launcher type: {type(launcher)}.')


def run(
    *,
    launcher_config: LauncherConfig[Any],
    num_actors: list[int],
    repeat: int,
    run_dir: str,
) -> None:
    timer = Timer().start()
    logger.info('Starting benchmark...')

    with CSVResultLogger(
        os.path.join(run_dir, 'results.csv'),
        Result,
    ) as result_logger:
        for _ in range(repeat):
            for actors in num_actors:
                if isinstance(launcher_config, (DaskConfig, RayConfig)):
                    launcher_config.workers = actors
                else:
                    launcher_config.workers_per_node = actors
                with launcher_config.get_launcher() as launcher:
                    results = run_benchmark(launcher, actors, result_logger)
                    for result in results:
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
        '--num-actors',
        type=int,
        nargs='+',
        help='number of actors to test',
    )
    add_general_options(parser)
    add_launcher_groups(parser, argv, required=True)
    args = parser.parse_args(argv)

    run_dir = os.path.join(
        args.run_dir,
        'memory-overhead',
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
        num_actors=args.num_actors,
        repeat=args.repeat,
        run_dir=run_dir,
    )

    return 0
