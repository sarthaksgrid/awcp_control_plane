"""
AWCP — Context Hashing & Staleness Detection
===============================================
Generates and compares content-addressable hashes of
context snapshots to detect stale state.

Used by the Context Graph Manager and the Degradation
Engine to trigger autonomy reduction when context
diverges from the last checkpoint.
"""
