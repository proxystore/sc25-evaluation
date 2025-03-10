#!/bin/bash -l
#PBS -A proxystore
#PBS -N agents-launch-latency
#PBS -l walltime=00:30:00
#PBS -l filesystems=flare,eagle
#PBS -k doe
#PBS -l place=scatter

NUM_NODES=`wc -l < $PBS_NODEFILE`
NUM_RANKS=6
NUM_WORKERS=$(( NUM_NODES * NUM_RANKS ))

DEFAULT_ARGS=" --repeat 6 --num-nodes $NUM_NODES --workers-per-node $NUM_RANKS "
# TODO: run dir
DEFAULT_ARGS+=" --run-dir ... "
 
ulimit -c unlimited

#############
# RUN AERIS #
#############

REDIS_PORT=6389
redis-server --port $REDIS_PORT --save "" --appendonly no --protected-mode no &> /dev/null &
REDIS=$!
echo "Redis server started"

python -m bench.launch_latency $DEFAULT_ARGS \
    --launcher aeris --parsl-config htex-aurora --redis-host localhost --redis-port $REDIS_PORT

kill $REDIS
echo "Redis server stopped"

############
# RUN DASK #
############

mpiexec -n $NUM_WORKERS --ppn $NUM_RANKS ./scripts/setup_dask_aurora.sh cpu $NUM_RANKS
# --dask-shutdown flag should cause workers and scheduler to exit
python -m bench.launch_latency $DEFAULT_ARGS --launcher dask --dask-scheduler $LOCAL_DIRECTORY --dask-shutdown

###########
# RUN RAY #
###########

source scripts/setup_ray_cluster.sh

export HSN_IP_ADDRESS=$(getent hosts "$(hostname).hsn.cm.aurora.alcf.anl.gov" | awk '{ print $1 }' | sort | head -n 1)

create_ray_cluster
python -m bench.launch_latency $DEFAULT_ARGS --launcher ray --ray-cluster $RAY_HEAD_IP:6379
stop_ray
