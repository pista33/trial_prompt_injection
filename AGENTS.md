# Editing rules

- Use the repository-root `.venv` as the single shared Python environment for every provider. Never create or use provider-specific or nested virtual environments.
- Run commands from the repository root with `.venv/bin/python` and `.venv/bin/agent-risk-lab`; do not depend on shell activation or machine-specific absolute paths.
- Before Python work, verify `sys.executable` and `sys.prefix` with `.venv/bin/python`. If the shared environment is unavailable, stop and report the cause instead of using `uv run`, a system Python, another environment, or automatically creating a new environment.
- Do not add or update dependencies, contact external APIs, commit, or push without explicit user permission.

- Keep Python compatibility at 3.12 or newer and keep Gemini SDK code inside `src/agent_risk_lab/providers/gemini/client.py`.
- Use only the Interactions API through `client.interactions.create`; do not add Generate Content, chat, streaming, background execution, or `previous_interaction_id`.
- Every Interactions API request must explicitly set `store=False` and each trial may make at most one request.
- Tool definitions must remain JSON Function Declarations. The only executable tool currently permitted is `file_copy`, dispatched once inside a unique temporary shadow copied from a registered experiment fixture. It must reject absolute paths, traversal, symlinks, special files, destinations outside the shadow, and overwrites. Never modify the registered fixture, execute any other tool, send Function Results, start agent loops, or add Gmail, Drive, SMTP, shell, subprocess, `os.system`, `eval`, or `exec`.
- Keep dry-run as the default. Tests must deny network access and use mocked Interaction responses.
- Read experiment documents only through the sandbox document store. Reject absolute paths, traversal, symlinks, special files, non-UTF-8 data, and oversized input.
- Never print, log, test with, or commit an API key or real secret. Use generated synthetic Canary values and fictional data only.
- Raw logs belong under `artifacts/logs/` and must stay ignored. Shared summaries must be aggregate-only and must not include Canary values, response text, Function Call arguments, Interaction IDs, or run IDs.
- Do not delete, move, or overwrite user files. Generated artifacts must use exclusive, unique filenames.
- Before completing changes, run offline pytest, doctor, representative dry-runs, `git diff`, and a security review.
- Experiment PDF input must be sent inline as a document part. Never use the Files API or `client.files.upload`; never log input text, PDF bytes, or base64 data.
