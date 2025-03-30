from __future__ import annotations

import argparse
import contextlib
import json
import logging
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from typing import Any
from typing import Generator
from typing import Protocol
from typing import runtime_checkable
from typing import TypeVar

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

if sys.version_info >= (3, 13):
    from typing import TypeIs
else:
    from typing_extensions import TypeIs

import ray
from dask.distributed import Client as DaskClient
from parsl.concurrent import ParslPoolExecutor

from aeris.exchange.hybrid import HybridExchange
from aeris.exchange.redis import RedisExchange
from aeris.launcher.executor import ExecutorLauncher
from aeris.manager import Manager
from bench.parsl import PARSL_CONFIGS

logger = logging.getLogger(__name__)

LauncherT_co = TypeVar('LauncherT_co', covariant=True)


@runtime_checkable
class LauncherConfig(Protocol[LauncherT_co]):
    name: str

    @classmethod
    def from_args(cls, args: dict[str, Any], run_dir: str) -> Self: ...

    @contextlib.contextmanager
    def get_launcher(self) -> Generator[LauncherT_co]: ...


class AerisConfig:
    def __init__(
        self,
        *,
        exchange: str,
        executor: str,
        redis_host: str,
        redis_port: int,
        run_dir: str,
        workers_per_node: int,
    ) -> None:
        self.name = 'aeris'
        self.exchange = exchange
        self.executor = executor
        self.run_dir = run_dir
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.workers_per_node = workers_per_node

    @classmethod
    def from_args(
        cls,
        args: dict[str, Any],
        run_dir: str,
    ) -> Self:
        return cls(
            exchange=args['exchange'],
            executor=args['executor'],
            redis_host=args['redis_host'],
            redis_port=args['redis_port'],
            run_dir=run_dir,
            workers_per_node=args['workers_per_node'],
        )

    @contextlib.contextmanager
    def get_launcher(self) -> Generator[Manager]:
        if self.executor == 'process-pool':
            mp_context = multiprocessing.get_context('spawn')
            executor = ProcessPoolExecutor(
                self.workers_per_node,
                mp_context=mp_context,
            )
        else:
            try:
                config = PARSL_CONFIGS[self.executor](
                    os.path.join(self.run_dir, 'parsl'),
                    workers_per_node=self.workers_per_node,
                )
            except KeyError as e:
                raise TypeError(
                    f'Unknown parsl config type "{self.executor}".',
                ) from e
            executor = ParslPoolExecutor(config)

        if self.exchange == 'redis':
            exchange = RedisExchange(self.redis_host, self.redis_port)
        elif self.exchange == 'hybrid':
            exchange = HybridExchange(self.redis_host, self.redis_port)
        else:
            raise ValueError(f'Unsupported exchange type "{self.exchange}".')
        with Manager(
            exchange=exchange,
            launcher=ExecutorLauncher(executor, close_exchange=True),
        ) as manager:
            yield manager


class DaskConfig:
    def __init__(
        self,
        *,
        scheduler: str | None = None,
        shutdown: bool = False,
        nodes: int = 1,
        workers: int = 1,
    ) -> None:
        self.name = 'dask'
        self.scheduler = scheduler
        self.shutdown = shutdown
        self.nodes = nodes
        self.workers = workers

    @classmethod
    def from_args(cls, args: dict[str, Any], run_dir: str) -> Self:
        scheduler = args['dask_scheduler']
        return cls(
            scheduler=scheduler,
            shutdown=args['dask_shutdown'],
            nodes=args['num_nodes'] if scheduler is not None else 1,
            workers=args['workers_per_node'],
        )

    @contextlib.contextmanager
    def get_launcher(self) -> Generator[DaskClient]:
        if self.scheduler is not None:
            try:
                # See if the scheduler is a filepath
                with open(self.scheduler, 'r') as f:
                    scheduler_config = json.load(f)
                    scheduler = scheduler_config['address']
            except OSError:
                # Otherwise its an address
                scheduler = self.scheduler
            kwargs = {}
        else:
            scheduler = None
            kwargs = {
                'dashboard_address': None,
                'include_dashboard': False,
                'worker_dashboard_address': None,
                'n_workers': self.workers,
            }

        client = DaskClient(address=scheduler, **kwargs)
        try:
            logger.info('Waiting for all workers to connect...')
            client.wait_for_workers(self.nodes * self.workers, timeout=300)
            logger.info(
                'Connected Dask workers: %s',
                len(client.scheduler_info()['workers']),
            )
            yield client
        finally:
            if self.scheduler is None or self.shutdown:
                client.shutdown()
            client.close()


class RayClient:
    # We lose typing on these methods but we the AERIS and Dask configs
    # yield objects that can be used to submit code, whereas ray uses
    # functions defined on the ray module so we wrap them here for
    # consistency.
    def remote(self, *args: Any, **kwargs: Any) -> Any:
        return ray.remote(*args, **kwargs)

    def cancel(self, *args: Any, **kwargs: Any) -> Any:
        return ray.cancel(*args, **kwargs)

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return ray.get(*args, **kwargs)

    def kill(self, *args: Any, **kwargs: Any) -> Any:
        return ray.kill(*args, **kwargs)


class RayConfig:
    def __init__(
        self,
        *,
        address: str | None = None,
        workers: int | None = None,
    ) -> None:
        self.name = 'ray'
        self.address = address
        self.workers = workers

    @classmethod
    def from_args(cls, args: dict[str, Any], run_dir: str) -> Self:
        return cls(
            address=args['ray_cluster'],
            workers=args['workers_per_node'],
        )

    @contextlib.contextmanager
    def get_launcher(self) -> Generator[RayClient]:
        ray.init(
            address=self.address,
            # configure_logging=False,
            # log_to_driver=False,
            object_store_memory=100_000_000 if self.address is None else None,
            include_dashboard=False if self.address is None else None,
            num_cpus=self.workers if self.address is None else None,
            num_gpus=0 if self.address is None else None,
            _temp_dir='/tmp/ray' if self.address is None else None,
        )
        try:
            yield RayClient()
        finally:
            ray.shutdown()


def get_launcher_config_from_args(
    args: argparse.Namespace,
    run_dir: str,
) -> LauncherConfig[Any]:
    options = vars(args)
    name = options['launcher']
    if name == 'aeris':
        return AerisConfig.from_args(options, run_dir)
    elif name == 'dask':
        return DaskConfig.from_args(options, run_dir)
    elif name == 'ray':
        return RayConfig.from_args(options, run_dir)
    else:
        raise TypeError(f'Launcher type "{name}" is not supported.')


def is_aeris_launcher(launcher: Any) -> TypeIs[Manager]:
    return isinstance(launcher, Manager)


def is_dask_launcher(launcher: Any) -> TypeIs[DaskClient]:
    return isinstance(launcher, DaskClient)


def is_ray_launcher(launcher: Any) -> TypeIs[RayClient]:
    return isinstance(launcher, RayClient)
