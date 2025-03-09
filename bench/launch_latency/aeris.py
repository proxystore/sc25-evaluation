from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from datetime import datetime

from parsl.concurrent import ParslPoolExecutor
from proxystore.utils.timer import Timer

from aeris.exchange.redis import RedisExchange
from aeris.launcher.executor import ExecutorLauncher
from aeris.logging import init_logging
from aeris.manager import Manager
from bench.launch_latency.actor import AerisActor
from bench.launch_latency.utils import Result
from bench.launch_latency.utils import Times
from bench.parsl import get_htex_local_config
from bench.results import CSVResultLogger

logger = logging.getLogger(__name__)


def run_benchmark(
    num_actors: int,
    manager: Manager,
) -> Times:
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


def run(
    *,
    num_nodes: int,
    num_workers_per_node: int,
    parsl_config: str,
    redis_host: str,
    redis_port: int,
    repeat: int,
    run_dir: str,
) -> None:
    timer = Timer().start()
    logger.info('Starting benchmark...')

    if parsl_config == 'htex-local':
        config = get_htex_local_config(
            os.path.join(run_dir, 'parsl'),
            workers_per_node=num_workers_per_node,
        )
    else:
        raise TypeError(f'Unknown parsl config type "{parsl_config}".')

    executor = ParslPoolExecutor(config)
    # import multiprocessing
    # from concurrent.futures import ProcessPoolExecutor

    # context = multiprocessing.get_context('spawn')
    # executor = ProcessPoolExecutor(num_workers_per_node, mp_context=context)
    # executor = ThreadPoolExecutor(num_workers_per_node)
    num_actors = num_nodes * num_workers_per_node

    logger.info('Running warmup task on executor...')
    executor.submit(sum, [1, 2, 3]).result()
    logger.info('Warmup task completed')

    with Manager(
        exchange=RedisExchange(redis_host, redis_port),
        launcher=ExecutorLauncher(executor, close_exchange=False),
    ) as manager:
        with CSVResultLogger(
            os.path.join(run_dir, 'results.csv'),
            Result,
        ) as result_logger:
            for i in range(repeat):
                times = run_benchmark(num_actors, manager)
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

    timer.stop()
    logger.info('Completed benchmark in %.3fs', timer.elapsed_s)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('--num-nodes', type=int, required=True)
    parser.add_argument('--num-workers-per-node', type=int, required=True)
    parser.add_argument(
        '--parsl-config',
        choices=['htex-local'],
        required=True,
    )
    parser.add_argument('--redis-host', type=str, required=True)
    parser.add_argument('--redis-port', type=int, required=True)
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--run-dir', default='runs/launch-latency')

    argv = argv if argv is not None else sys.argv[1:]
    args = parser.parse_args(argv)

    run_dir = os.path.join(
        args.run_dir,
        datetime.now().strftime('%Y-%m-%d-%H-%M-%S'),
    )
    init_logging(level=logging.DEBUG, logfile=os.path.join(run_dir, 'log.txt'))

    run(
        num_nodes=args.num_nodes,
        num_workers_per_node=args.num_workers_per_node,
        parsl_config=args.parsl_config,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        repeat=args.repeat,
        run_dir=run_dir,
    )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
