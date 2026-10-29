"""The tools the agent can call, one file per group. Each file exports TOOLS: name -> (function, one-line usage for the prompt).
Each function takes the Run and its arguments and returns a JSON-able dict. The checks live inside the tools, so the agent cannot skip them."""
from plan2cost.tools import documents, drawings, estimate, records, standards, structural, submit

TOOLS: dict = {}
for group in (records, documents, drawings, structural, standards, estimate, submit):
    TOOLS.update(group.TOOLS)
