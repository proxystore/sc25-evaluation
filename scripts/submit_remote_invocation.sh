DEFAULT_ARGS=" --repeat 10 --num-nodes 1 --workers-per-node 1 "
DEFAULT_ARGS+=" --run-dir /home/alokvk2/research/agents/sc25-evaluation/runs-test "
DEFAULT_ARGS+=" --state-sizes 1kb 10kb 100kb 1mb 10mb 100mb "

ENDPOINT_ID="73e00b24-25b5-44e5-adc5-8ad17705e5da"

# conda activate py310 # Activate python 3.10 environment
# cd /home/alokvk2/research/agents/sc25-evaluation
# . ./venv/bin/activate
# echo $PWD

#############
# RUN ACADEMY #
#############

python -m bench.remote_invocation $DEFAULT_ARGS \
    --launcher academy --exchange cloud --executor process-pool


############
# RUN Globus Compute #
############

# python -m bench.remote_invocation $DEFAULT_ARGS \
#     --launcher academy --exchange cloud --executor globus-compute \
#     --gc-endpoint $ENDPOINT_ID
