"""Langfuse tracing of simulation agents' LLM calls.

Reads the Langfuse settings, bootstraps the OpenTelemetry exporter in the
``glossogen run`` path, and stamps each generation span with the simulation
round it was made in.
"""
