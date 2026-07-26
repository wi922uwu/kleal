#!/bin/bash
# Self-host Llama-3.3-70B-Instruct (AWQ int4) on the pod's A100-80GB via vLLM :8002.
# Frees the GPU first (kills any running vLLM, incl. prod-mistral — they don't co-fit on 80GB).
pkill -9 -f vllm 2>/dev/null
pkill -9 -f spawn_main 2>/dev/null
pkill -9 -f 'multiprocessing.spawn' 2>/dev/null
sleep 8
# AWQ weights live on the LOCAL disk /root (the /workspace network volume breaks on big files).
# NO --quantization flag: vLLM auto-detects AWQ and picks the faster awq_marlin kernel on Ampere.
# (--quantization awq would FORCE the slower plain-AWQ kernel — do not set it.)
# nohup+setsid+`-u` — else the process dies on SSH close with an EMPTY log (proven, not a crash).
nohup setsid python3 -u -m vllm.entrypoints.openai.api_server \
  --model /root/llama-3.3-70b-awq \
  --served-model-name llama-3.3-70b \
  --host 0.0.0.0 --port 8002 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90 \
  --max-num-seqs 16 \
  --dtype float16 \
  > /root/llama_vllm.log 2>&1 < /dev/null &
echo "Llama-3.3-70B launching -> tail -f /root/llama_vllm.log (ready ~3-4 min: load+KV+CUDA graphs)"
# Re-download if missing:
#   HF_HUB_DISABLE_XET=1 python3 -c "from huggingface_hub import snapshot_download; \
#     snapshot_download('casperhansen/llama-3.3-70b-instruct-awq', local_dir='/root/llama-3.3-70b-awq')"
