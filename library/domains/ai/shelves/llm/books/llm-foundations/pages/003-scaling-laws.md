---
id: nd_01KX82V9S43F90QZDJ2HAJ4WA3
title: Scaling Laws
source_ref: seed
---

Scaling laws describe how loss falls predictably as parameters, data and compute
grow — power-law curves smooth enough to extrapolate. The **Chinchilla** result
showed many earlier models were undertrained: for a fixed compute budget, loss is
minimized by scaling parameters and training tokens together (roughly 20 tokens per
parameter), not by parameters alone.

Practical consequences: smaller models trained on much more data can match larger
undertrained ones, and inference cost — not just training loss — should drive model
sizing. Downstream capabilities sometimes appear 'emergent', though part of that is
an artifact of discontinuous metrics.
