---
id: nd_01KX82V9P9JKWJERB3VDNXAY4F
title: Faithfulness & Relevance Metrics
source_ref: seed
---

RAG evaluation separates the pipeline into measurable parts. **Faithfulness**: is
every claim in the answer supported by the retrieved context? **Answer relevance**:
does the answer address the question? **Context precision/recall**: did retrieval
return the right passages, and how much of it was useful?

These are usually scored by an LLM judge given the question, context and answer.
LLM-as-judge is convenient but biased: it favors fluent answers, position and
verbosity. Mitigate with rubric-anchored prompts, score justification, and periodic
human calibration on a sample. Track metrics per corpus segment — averages hide
regressions in small but important slices.
