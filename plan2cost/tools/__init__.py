"""The tools the agent can call, one file per group. Each file exports TOOLS: name -> (function, one-line usage for the prompt).
Each function takes the Run and its arguments and returns a JSON-able dict. The checks live inside the tools, so the agent cannot skip them."""
from plan2cost.tools import audit, documents, drawings, estimate, finishes, records, roof, standards, structural, submit

TOOLS: dict = {}
for group in (records, documents, drawings, finishes, roof, structural, standards, estimate, audit, submit):
    TOOLS.update(group.TOOLS)
