# SONiC Python LLM Consistency Checker

Step-by-step SONiC learning and consistency-checking project.

Reads SONiC's internal Redis DB configuration dynamically, explores Redis state, builds cross-DB views of ports and routes, detects inconsistencies, and uses an LLM-ready explanation layer to support debugging workflows.

## Steps

| Step | Description | README |
|---|---|---|
| 1 | Dynamic DB Config Discovery | [STEP_01.md](docs/readme/STEP_01.md) |
| 2 | Redis DB Explorer | *(coming)* |
| 3 | Port View | *(coming)* |
| 4 | Consistency Checks | *(coming)* |
| 5 | SWSS SDK Explorer | *(coming)* |
| 6 | UI Demo | *(coming)* |
| 7 | LLM Explanation Layer | *(coming)* |

## Quick Start

```bash
pip install -e .
sonic-checker db-config
```

See [docs/readme/STEP_01.md](docs/readme/STEP_01.md) for connection mode setup.
