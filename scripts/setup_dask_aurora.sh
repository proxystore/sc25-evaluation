#!/bin/bash -e

# Usage:
#   ./start_dask_aurora.sh NUM_NODES WORKERS_PER_NODE
# Example:
#   ./start_dask_aurora.sh 2 208
#   source start_dask_aurora.sh 2 208

NUM_NODES=${1:-1}
NUM_WORKERS_PER_NODE=${2:-104}
# Number of threads per worker (208 CPU threads per node divided by num workers)
NTHREADS=$(( 208 / NUM_WORKERS_PER_NODE ))  # 208 / 12 ≈ 17
# Memory limit per worker (1100GB RAM per node divided by num workers)
MEMORY_PER_WORKER=$(( 1100 / NUM_WORKERS_PER_NODE ))GB  # 1100GB / 12 ≈ 91GB
DASK_SCHEDULER_HOST=$(hostname -f)
DASK_SCHEDULER_PORT=${DASK_SCHEDULER_PORT:-8786}
DASK_LOG_DIRECTORY="/flare/proxystore/jgpaul/agents/cache/dask/$PBS_JOBID"
export DASK_SCHEDULER_ADDRESS="$DASK_SCHEDULER_HOST:$DASK_SCHEDULER_PORT"

mkdir -p ${DASK_LOG_DIRECTORY}

nohup dask scheduler \
    --port ${DASK_SCHEDULER_PORT} --no-dashboard --no-show \
    &> ${DASK_LOG_DIRECTORY}/scheduler.log &

echo "Started Dask scheduler at $DASK_SCHEDULER_ADDRESS"
sleep 10

mpiexec -n $NUM_NODES --ppn 1 \
    dask worker $DASK_SCHEDULER_ADDRESS \
        --nworkers ${NUM_WORKERS_PER_NODE} \
        --nthreads 1 \
        --memory-limit ${MEMORY_PER_WORKER} --no-dashboard \
        --local-directory /tmp/dask-workers \
    &> ${DASK_LOG_DIRECTORY}/workers.log &
# --nthreads ${NTHREADS} \
echo "Started Dask workers on $NUM_NODES nodes"
