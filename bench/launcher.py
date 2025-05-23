from __future__ import annotations

import argparse
import contextlib
import json
import logging
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import ThreadPoolExecutor
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
from academy.exchange.hybrid import HybridExchange
from academy.exchange.proxystore import ProxyStoreExchange
from academy.exchange.redis import RedisExchange
from academy.launcher.executor import ExecutorLauncher
from academy.manager import Manager
from dask.distributed import Client as DaskClient
from globus_compute_sdk import Executor as GCExecutor
from parsl.concurrent import ParslPoolExecutor
from proxystore.connectors.endpoint import EndpointConnector
from proxystore.store import Store
from proxystore.store.executor import ProxyAlways

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
        interface: str | None = None,
        gc_endpoint: str | None = None,
        ps_endpoints: list[str] | None = None,
    ) -> None:
        self.name = 'academy'
        self.exchange = exchange
        self.executor = executor
        self.run_dir = run_dir
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.workers_per_node = workers_per_node
        self.interface = interface
        self.gc_endpoint = gc_endpoint
        self.ps_endpoints = ps_endpoints

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
            interface=args['interface'],
            gc_endpoint=args['gc_endpoint'],
            ps_endpoints=args['ps_endpoints'],
        )

    @contextlib.contextmanager
    def get_launcher(self) -> Generator[Manager]:
        if self.executor == 'process-pool':
            mp_context = multiprocessing.get_context('spawn')
            executor = ProcessPoolExecutor(
                self.workers_per_node,
                mp_context=mp_context,
            )
        elif self.executor == 'thread-pool':
            executor = ThreadPoolExecutor(self.workers_per_node)
        elif self.executor == 'globus-compute':
            assert self.gc_endpoint is not None
            executor = GCExecutor(self.gc_endpoint, batch_size=1)
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
            exchange = HybridExchange(
                self.redis_host,
                self.redis_port,
                interface=self.interface,
            )
        else:
            raise ValueError(f'Unsupported exchange type "{self.exchange}".')

        if self.ps_endpoints is not None:
            # from proxystore_ex.connectors.dim.zmq import ZeroMQConnector
            # connector = ZeroMQConnector(25780, interface='hsn0', timeout=1)
            connector = EndpointConnector(self.ps_endpoints)
            store = Store(
                'exchange',
                connector,
                cache_size=0,
                register=True,
            )
            exchange = ProxyStoreExchange(
                exchange,
                store,
                should_proxy=ProxyAlways(),
                resolve_async=False,
            )

        with Manager(
            exchange=exchange,
            launcher=ExecutorLauncher(
                executor,
                close_exchange=self.exchange != 'thread-pool',
            ),
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
                'worker_dashboard_address': None,
                'n_workers': self.workers,
                'threads_per_worker': 1,
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
    # We lose typing on these methods but we the Academy and Dask configs
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
    if name == 'academy':
        return AerisConfig.from_args(options, run_dir)
    elif name == 'dask':
        return DaskConfig.from_args(options, run_dir)
    elif name == 'ray':
        return RayConfig.from_args(options, run_dir)
    else:
        raise TypeError(f'Launcher type "{name}" is not supported.')


def is_academy_launcher(launcher: Any) -> TypeIs[Manager]:
    return isinstance(launcher, Manager)


def is_dask_launcher(launcher: Any) -> TypeIs[DaskClient]:
    return isinstance(launcher, DaskClient)


def is_ray_launcher(launcher: Any) -> TypeIs[RayClient]:
    return isinstance(launcher, RayClient)
