"""Known-answer research quality evaluation for the autonomous scientist.

Each task is a research question over a synthetic dataset whose answer is known by
construction (an effect that exists, or one that does not). A nightly run sends every task
through the real pipeline (real models, literature, sandbox, verification and review) and
scores what it verified against the truth. See :mod:`evals.scientist.run`.
"""
