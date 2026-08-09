# Local AI Runtime Certification

Approved runtime: official llama.cpp Windows x64 CPU release `b10329`, build
`10329 (18f7ad7fc)`. Runtime archive SHA-256:
`fc33edf0b209e89f477f5542657271f93dc5c56a03c9c5d9af8cc9f330c318c5`.

Approved model: `ggml-org/Qwen3-1.7B-GGUF`, file
`Qwen3-1.7B-Q4_K_M.gguf`, Apache-2.0, 1,282,439,264 bytes, SHA-256
`d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5`.
Only this one model was downloaded. Runtime and model directories are ignored by Git.

Certified launch profile:

```text
llama-server -m <ignored-model-path> --host 127.0.0.1 --port 8080
  --ctx-size 4096 --threads 4 --threads-http 2 --parallel 1
  --gpu-layers 0 --jinja --api-key-file <ignored-secret-file>
  --cors-origins localhost --no-cors-credentials --no-webui
```

The listener was verified as `127.0.0.1:8080` only. The UI is disabled and an
unauthenticated chat completion returns 401. Configure the application with
`LOCAL_AI_MODEL`, the loopback `LOCAL_AI_ENDPOINT`, and preferably
`LOCAL_AI_API_KEY_FILE`; do not copy the key into source control.

Load time was 6.300 seconds in the hardened run and observed working-set RAM was
approximately 2.32 GB. The six-case synthetic benchmark produced schema-valid
output in 6/6 cases. Generation ranged from 2.459 to 4.033 tokens/second. Correct
safe actions were produced for bank table, marketplace table, and correction
instruction (3/6). Simple invoice, mixed-GST, and unknown-format anchoring were
classified `NEEDS_CLOUD`. This is a narrow local assistant, not autonomous authority.
