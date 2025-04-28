# SC25 Academy Evaluation

Benchmarks and evaluation code for the SC25 submission on [Academy](https://github.com/proxystore/academy).

## Installation

The `bench/` package contains all of the microbenchmarks for the paper.

```bash
python -m venv venv
. venv/bin/activate
pip install -e .
```

This installs the requirements for `notebooks/` as well, but the analysis specific requirements are also defined in `notebooks/requirements.txt`.

## Running Benchmarks

Each benchmark is an executable module in the `bench` package. E.g.,
```bash
python -m bench.action_latency --help
```

## Performing Analysis

All results used in the paper are provided in `data/`, and all figures have an associated Jupyter Notebook in `notebooks/`.
