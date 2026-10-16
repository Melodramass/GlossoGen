"""Deriving a new run from a finished one at a round boundary.

The replace-agent, cross-run replace-agent and fork-at-round flows: preparing the
truncated copy, the manifests that record where each derived run came from, and
launching its resumed subprocess.
"""
