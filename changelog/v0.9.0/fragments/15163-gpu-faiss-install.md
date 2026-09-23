---
type: fix
scope: backend
issue: 15163
pr: 0000
---
GPU-accelerated vector search (`gpu_vector_search.py`, #387) is now reachable: a new `requirements-gpu-faiss.txt` installs `faiss-gpu` whenever the ansible backend role detects a GPU, replacing the dead conda-only install path.
