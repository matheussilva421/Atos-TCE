"""Promoted analysis engine (M6 Task 1).

These modules are behaviour-preserving copies of the proven pipeline, moved next
to the Mesa so no supported runtime path depends on the legacy portable tree.
The presentation artifacts of that tree (extension dataset and HTML/markdown
interface payload) are intentionally not carried: the Mesa reads its analysis
results from SQLite.
"""
