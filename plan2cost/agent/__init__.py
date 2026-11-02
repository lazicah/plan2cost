"""The Plan2Cost agent: reads a drawing set, settles a checklist with verified facts, asks the user for what is missing,
and files a BoQ. Loop shape follows the Meta agent workshop pattern (one tool per turn, facts with quotes, checks the agent
cannot skip, escalation and resume); the code is our own."""
