"""
AWCP — RLM Summarizer
========================
Recursive Language Model summarizer for compressing
large trace histories and documents.

Used during replay and recovery to fold verbose execution
histories into compact, actionable summaries that fit
within the context graph's token budget.

Provides:
  - summarize_trace()    — compress a trace sequence
  - fold_document()      — recursively summarize a long document
  - rank_relevance()     — score context artifacts by relevance
"""
