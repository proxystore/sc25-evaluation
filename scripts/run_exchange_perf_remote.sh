DEFAULT_ARGS=" --repeat 50 "
DEFAULT_ARGS+=" --run-dir /home/alokvk2/research/agents/sc25-evaluation/runs-prod "\

ENDPOINT_ID="73e00b24-25b5-44e5-adc5-8ad17705e5da"
LOCAL_PS_ENDPOINT="0d603b36-4d6e-4de2-8730-fc8ad1edad70"
REMOTE_PS_ENPOINT="348cd67c-fa7c-4e4e-9325-095204f05fee"

#############
# RUN w/o Proxystore #
#############

python -m bench.exchange_perf $DEFAULT_ARGS \
    --data-sizes 1kb 10kb 100kb \
    --exchange cloud --executor globus-compute --gc-endpoint $ENDPOINT_ID

############
# RUN w/ Proxystore #
############

python -m bench.exchange_perf $DEFAULT_ARGS \
    --data-sizes 1kb 10kb 100kb 1mb 10mb 100mb \
    --exchange cloud --executor globus-compute --gc-endpoint $ENDPOINT_ID \
    --ps-endpoints $LOCAL_PS_ENDPOINT $REMOTE_PS_ENPOINT