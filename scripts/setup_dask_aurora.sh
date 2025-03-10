#!/bin/bash

# start_dask_aurora.sh
# Usage: 
# mpiexec -n NNODES * NUM_WORKERS_PER_NODE --ppn NUM_WORKERS_PER_NODE ./start_dask_aurora.sh WORKER_TYPE NUM_WORKERS_PER_NODE
# Examples on two nodes:
# mpiexec -n 12 --ppn 6 ./scripts/start_dask_aurora.sh gpu 6
# mpiexec -n 208 --ppn 104 ./scripts/start_dask_aurora.sh cpu 104

WORKER_TYPE=$1
NUM_WORKERS_PER_NODE=$2
# if using 12 GPU workers, assign one worker per tile, otherwise use one worker per GPU (2 tiles)
if [ $NUM_WORKERS_PER_NODE = 12 ] && [ $WORKER_TYPE = 'gpu' ]; then
    export ZE_FLAT_DEVICE_HIERARCHY=FLAT
    export ZE_ENABLE_PCI_ID_DEVICE_ORDER=1
else
    export ZE_FLAT_DEVICE_HIERARCHY=COMPOSITE
fi

# Number of threads per worker (208 CPU threads per node divided by num workers)
NTHREADS=$(( 208 / NUM_WORKERS_PER_NODE ))  # 208 / 12 ≈ 17
# Memory limit per worker (1100GB RAM per node divided by num workers)
MEMORY_PER_WORKER=$(( 1100 / NUM_WORKERS_PER_NODE ))GB  # 1100GB / 12 ≈ 91GB
LOCAL_DIRECTORY=~/dask-local-directory
DASK_SCHEDULER_PORT=${DASK_SCHEDULER_PORT:-8786}

# Start Dask scheduler on rank 0
if [ $PALS_RANKID = 0 ]; then
    # Purge Dask worker, log directories and config directories
    rm -rf ${LOCAL_DIRECTORY}/* /tmp/dask-workers/*  ~/.config/dask
    mkdir -p ${LOCAL_DIRECTORY}/logs /tmp/dask-workers
    # Setup scheduler
    nohup dask scheduler --port ${DASK_SCHEDULER_PORT} --scheduler-file ${LOCAL_DIRECTORY}/scheduler.json > ${LOCAL_DIRECTORY}/logs/$HOSTNAME-scheduler.log 2>&1 &
fi
sleep 10
# Setup workers
if [ $WORKER_TYPE = 'gpu' ]; then
    ZE_AFFINITY_MASK=$PALS_LOCAL_RANKID dask worker \
        --resources "GPU=1" --memory-limit ${MEMORY_PER_WORKER} \
        --nthreads ${NTHREADS}  --local-directory /tmp/dask-workers \
        --scheduler-file ${LOCAL_DIRECTORY}/scheduler.json >> ${LOCAL_DIRECTORY}/logs/$HOSTNAME-worker.log 2>&1
else
    dask worker \
        --nthreads ${NTHREADS} --local-directory /tmp/dask-workers \
        --scheduler-file ${LOCAL_DIRECTORY}/scheduler.json >> ${LOCAL_DIRECTORY}/logs/$HOSTNAME-worker.log 2>&1
fi
