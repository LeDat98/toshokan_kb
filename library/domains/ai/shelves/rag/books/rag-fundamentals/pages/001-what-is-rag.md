---
id: nd_01KX80W5T4EJZ15FBSSEZWQXZC
title: What is RAG
source_ref: seed
---

Retrieval-Augmented Generation (RAG) grounds a language model's answer in external
knowledge fetched at query time. Instead of relying on parametric memory, the system
retrieves relevant documents, injects them into the prompt as context, and generates
an answer conditioned on that evidence.

The basic pipeline has three stages: **retrieve** (find candidate passages for the
query), **augment** (assemble them into the prompt), and **generate** (produce the
grounded answer). Compared with fine-tuning, RAG updates knowledge by editing the
corpus rather than retraining, provides citations naturally, and reduces — but does
not eliminate — hallucination. Its main failure modes are retrieval misses and
context that contradicts the model's priors.
