DEFAULT_ARGS=" --repeat 30 --num-nodes 1 --workers-per-node 1 "
DEFAULT_ARGS+=" --run-dir /home/alokvk2/research/agents/sc25-evaluation/runs-prod "
DEFAULT_ARGS+=" --state-sizes 1gb 2gb 4gb 8gb 16gb "

ENDPOINT_ID="73e00b24-25b5-44e5-adc5-8ad17705e5da"

# conda activate py310 # Activate python 3.10 environment
# cd /home/alokvk2/research/agents/sc25-evaluation
# . ./venv/bin/activate
# echo $PWD

#############
# RUN ACADEMY #
#############

python -m bench.remote_invocation $DEFAULT_ARGS \
    --launcher academy --exchange cloud --executor globus-compute \
    --gc-endpoint $ENDPOINT_ID

############
# RUN Globus Compute #
############

STATE_STORE="/flare/workflow_scaling/alokvk2/agents/sc25-evaluation/data/state.bytes"
python -m bench.remote_invocation $DEFAULT_ARGS \
    --launcher gc --endpoint-id $ENDPOINT_ID --state-path $STATE_STORE
