"""Conversation persistence + context management (chat history).

A deliberate late addition: the retrieval core is single-shot on purpose (see
docs/RETRIEVAL_REDESIGN.md) to avoid the O(T²) cost of resending a whole conversation each turn.
Multi-turn is bought WITHOUT reintroducing that cost: history touches only a cheap `contextualize`
rewrite that turns a follow-up into a standalone query; the cascade then runs on it as before.
"""
