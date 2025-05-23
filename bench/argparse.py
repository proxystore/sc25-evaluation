from __future__ import annotations

import argparse
from typing import Sequence

from bench.parsl import PARSL_CONFIGS


def add_general_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        '--log-level',
        choices=['ERROR', 'WARNING', 'INFO', 'DEBUG'],
        default='INFO',
        help='logging level',
    )
    parser.add_argument(
        '--repeat',
        type=int,
        default=1,
        help='benchmark repeat',
    )
    parser.add_argument('--run-dir', default='runs/', help='run directory')


def add_launcher_groups(
    parser: argparse.ArgumentParser,
    argv: Sequence[str] = (),
    required: bool = True,
) -> None:
    parser.add_argument(
        '--launcher',
        choices=['academy', 'dask', 'ray'],
        required=True,
        help='launcher framework to use',
    )
    parser.add_argument(
        '--num-nodes',
        type=int,
        required=True,
        help='number of nodes in cluster',
    )
    parser.add_argument(
        '--workers-per-node',
        type=int,
        required=True,
        help='number of workers per node in cluster',
    )
    arg_str = ''.join(argv)
    add_academy_parser_group(
        parser,
        required='--launcher academy' in arg_str,
    )
    add_dask_parser_group(
        parser,
        required='--launcher dask' in arg_str,
    )
    add_ray_parser_group(
        parser,
        required='--launcher ray' in arg_str,
    )


def add_academy_parser_group(
    parser: argparse.ArgumentParser,
    required: bool = True,
) -> None:
    group = parser.add_argument_group(title='Academy Configuration')

    group.add_argument(
        '--exchange',
        choices=['hybrid', 'redis'],
        default='redis',
        help='exchange type',
    )
    group.add_argument(
        '--executor',
        choices=[
            'globus-compute',
            'thread-pool',
            'process-pool',
            *PARSL_CONFIGS.keys(),
        ],
        required=required,
    )
    group.add_argument(
        '--redis-host',
        type=str,
        required=required,
        help='redis host',
    )
    group.add_argument(
        '--redis-port',
        type=int,
        required=required,
        help='redis port',
    )
    group.add_argument(
        '--interface',
        default=None,
        help='interface to use with hybrid exchange',
    )
    group.add_argument(
        '--gc-endpoint',
        default=None,
        help='globus compute endpoint uuid',
    )
    group.add_argument(
        '--ps-endpoints',
        nargs='+',
        default=None,
        help='use proxystore endpoints for data transfer',
    )


def add_dask_parser_group(
    parser: argparse.ArgumentParser,
    required: bool = True,
) -> None:
    group = parser.add_argument_group(title='Dask Configuration')

    group.add_argument(
        '--dask-scheduler',
        default=None,
        metavar='ADDR',
        help='dask scheduler address (default uses LocalCluster)',
    )
    group.add_argument(
        '--dask-shutdown',
        action='store_true',
        help='shutdown the connected scheduler and workers',
    )


def add_ray_parser_group(
    parser: argparse.ArgumentParser,
    required: bool = True,
) -> None:
    group = parser.add_argument_group(title='Ray Configuration')

    group.add_argument(
        '--ray-cluster',
        default=None,
        metavar='ADDR',
        help='ray cluster address (default creates local cluster)',
    )
