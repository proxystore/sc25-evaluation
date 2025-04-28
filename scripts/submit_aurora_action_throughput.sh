#!/bin/bash -e
#PBS -A proxystore
#PBS -N agents-action-throughput
#PBS -l filesystems=flare
#PBS -l place=scatter
#PBS -j oe

NUM_NODES=`wc -l < $PBS_NODEFILE`
NUM_RANKS=52
NUM_WORKERS=$(( NUM_NODES * NUM_RANKS ))
echo "NODES: $NUM_NODES; RANKS: $NUM_RANKS; WORKERS: $NUM_WORKERS"

DEFAULT_ARGS=" --num-nodes $NUM_NODES --workers-per-node $NUM_RANKS "
DEFAULT_ARGS+=" --repeat 1 --actions-per-actor 100 "
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

python -m bench.action_throughput $DEFAULT_ARGS \
    --launcher academy --executor htex-aurora-cpu --redis-host $HEAD_NODE_IP --redis-port $REDIS_PORT

kill $REDIS
echo "Redis server stopped"

############
# RUN DASK #
############

source scripts/setup_dask_aurora.sh $NUM_NODES $NUM_RANKS
# # --dask-shutdown flag should cause workers and scheduler to exit
python -m bench.action_throughput $DEFAULT_ARGS --launcher dask --dask-scheduler $DASK_SCHEDULER_ADDRESS --dask-shutdown

###########
# RUN RAY #
###########

export RAY_CPU_PER_NODE=$NUM_RANKS
export RAY_GPU_PER_NODE=0
source scripts/setup_ray_aurora.sh
start_ray_cluster
python -m bench.action_throughput $DEFAULT_ARGS --launcher ray --ray-cluster $RAY_HEAD_IP:6379
mpiexec -n $NUM_NODES --ppn 1 ray stop -g 30
