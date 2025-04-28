#!/bin/bash -e
#PBS -A proxystore
#PBS -N agents-memory-overhead
#PBS -q debug
#PBS -l walltime=01:00:00
#PBS -l select=1
#PBS -l filesystems=flare
#PBS -l place=scatter
#PBS -j oe

NUM_NODES=`wc -l < $PBS_NODEFILE`
NUM_RANKS=104
NUM_WORKERS=$(( NUM_NODES * NUM_RANKS ))
echo "NODES: $NUM_NODES; RANKS: $NUM_RANKS; WORKERS: $NUM_WORKERS"

DEFAULT_ARGS=" --repeat 3 --num-nodes $NUM_NODES --workers-per-node $NUM_RANKS "
DEFAULT_ARGS+=" --num-actors 1 2 4 8 16 32 52 104 "
DEFAULT_ARGS+=" --run-dir /flare/proxystore/jgpaul/agents/sc25-evaluation/runs-prod "
 
module load python/3.10.13
cd /flare/proxystore/jgpaul/agents/sc25-evaluation
. ../venv/bin/activate
echo $PWD

HEAD_NODE_IP=$(getent hosts "$(hostname).hsn.cm.aurora.alcf.anl.gov" | awk '{ print $1 }' | sort | head -n 1)

#############
# RUN ACADEMY #
#############

REDIS_PORT=6389
redis-server --port $REDIS_PORT --save "" --appendonly no --protected-mode no &> /dev/null &
REDIS=$!
echo "Redis server started"

python -m bench.memory_overhead $DEFAULT_ARGS \
    --launcher academy --executor process-pool --redis-host $HEAD_NODE_IP --redis-port $REDIS_PORT
python -m bench.memory_overhead $DEFAULT_ARGS \
    --launcher academy --executor htex-aurora-local --redis-host $HEAD_NODE_IP --redis-port $REDIS_PORT

kill $REDIS
echo "Redis server stopped"

############
# RUN DASK #
############

python -m bench.memory_overhead $DEFAULT_ARGS --launcher dask

###########
# RUN RAY #
###########

python -m bench.memory_overhead $DEFAULT_ARGS --launcher ray
