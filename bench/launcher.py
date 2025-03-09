from __future__ import annotations

import argparse
import contextlib
import os
import sys
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
from parsl.config import Config as ParslConfig

from aeris.exchange.redis import RedisExchange
from aeris.launcher.executor import ExecutorLauncher
from aeris.manager import Manager
from bench.parsl import get_htex_local_config

LauncherT_co = TypeVar('LauncherT_co', covariant=True)


@runtime_checkable
class LauncherConfig(Protocol[LauncherT_co]):
    @classmethod
    def from_args(cls, args: dict[str, Any], run_dir: str) -> Self: ...

    @contextlib.contextmanager
    def get_launcher(self) -> Generator[LauncherT_co]: ...


class AerisConfig:
    def __init__(
        self,
        *,
        redis_host: str,
        redis_port: int,
        parsl_config: ParslConfig,
    ) -> None:
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.parsl_config = parsl_config

    @classmethod
    def from_args(
        cls,
        args: dict[str, Any],
        run_dir: str,
    ) -> Self:
        parsl_config = args['parsl_config']
        if parsl_config == 'htex-local':
            config = get_htex_local_config(
                os.path.join(run_dir, 'parsl'),
                workers_per_node=args['workers_per_node'],
            )
        else:
            raise TypeError(f'Unknown parsl config type "{parsl_config}".')

        return cls(
            redis_host=args['redis_host'],
            redis_port=args['redis_port'],
            parsl_config=config,
        )

    @contextlib.contextmanager
    def get_launcher(self) -> Generator[Manager]:
        executor = ParslPoolExecutor(self.parsl_config)
        with Manager(
            exchange=RedisExchange(self.redis_host, self.redis_port),
            launcher=ExecutorLauncher(executor, close_exchange=True),
        ) as manager:
            yield manager


class DaskConfig:
    def __init__(
        self,
        *,
        scheduler: str | None = None,
        workers: int | None = None,
    ) -> None:
        self.scheduler = scheduler
        self.workers = workers

    @classmethod
    def from_args(cls, args: dict[str, Any], run_dir: str) -> Self:
        return cls(
            scheduler=args['dask_scheduler'],
            workers=args['workers_per_node'],
        )

    @contextlib.contextmanager
    def get_launcher(self) -> Generator[DaskClient]:
        client = DaskClient(
            address=self.scheduler,
            dashboard_address=None,
            worker_dashboard_address=None,
            n_workers=self.workers,
        )
        try:
            yield client
        finally:
            if self.scheduler is None:
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
    def __init__(self, *, address: str | None = None) -> None:
        self.address = address

    @classmethod
    def from_args(cls, args: dict[str, Any], run_dir: str) -> Self:
        return cls(address=args['ray_cluster'])

    @contextlib.contextmanager
    def get_launcher(self) -> Generator[RayClient]:
        ray.init(address=self.address)
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
