"""Console transport (phase 1): interactive CLI trainer.

Runs the LangGraph graph in a terminal loop: lesson -> quiz -> socratic
question, with progress persisted between runs (checkpointer + training
state). Implemented by the ``add-console-trainer`` change.
"""
