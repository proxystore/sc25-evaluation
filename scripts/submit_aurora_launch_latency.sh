#!/bin/bash -ex
#PBS -A proxystore
#PBS -N agents-launch-latency
#PBS -l walltime=00:30:00
#PBS -l filesystems=flare
#PBS -l place=scatter

NUM_NODES=`wc -l < $PBS_NODEFILE`
NUM_RANKS=6
NUM_WORKERS=$(( NUM_NODES * NUM_RANKS ))
echo "NODES: $NUM_NODES; RANKS: $NUM_RANKS; WORKERS: $NUM_WORKERS"

DEFAULT_ARGS=" --repeat 6 --num-nodes $NUM_NODES --workers-per-node $NUM_RANKS "
DEFAULT_ARGS+=" --run-dir /flare/proxystore/jgpaul/agents/sc25-evaluation/runs "
 
# module load python/3.10.13
# cd /flare/proxystore/jgpaul/agents/sc25-evaluation
# . ../venv/bin/activate
# echo $PWD

HEAD_NODE_IP=$(getent hosts "$(hostname).hsn.cm.aurora.alcf.anl.gov" | awk '{ print $1 }' | sort | head -n 1)

#############
# RUN AERIS #
#############

# REDIS_PORT=6389
# redis-server --port $REDIS_PORT --save "" --appendonly no --protected-mode no &> /dev/null &
# REDIS=$!
# echo "Redis server started"

# python -m bench.launch_latency $DEFAULT_ARGS \
#     --launcher aeris --parsl-config htex-aurora-cpu --redis-host $HEAD_NODE_IP --redis-port $REDIS_PORT

# kill $REDIS
# echo "Redis server stopped"

############
# RUN DASK #
############

mpiexec -n $NUM_NODES --ppn 1 ./scripts/setup_dask_aurora.sh cpu $NUM_RANKS
# --dask-shutdown flag should cause workers and scheduler to exit
python -m bench.launch_latency $DEFAULT_ARGS --launcher dask --dask-scheduler dask-local-directory/scheduler.json # --dask-shutdown

###########
# RUN RAY #
###########

# export RAY_CPU_PER_NODE=$NUM_RANKS
# export RAY_GPU_PER_NODE=0
# source scripts/setup_ray_aurora.sh
# start_ray_cluster
# python -m bench.launch_latency $DEFAULT_ARGS --launcher ray --ray-cluster $RAY_HEAD_IP:6379
# stop_ray
