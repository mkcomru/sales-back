# Imports

Imports must always be placed at the top of the file, grouped and ordered according to PEP 8:
standard library first, then third-party, then local. Never place imports inside functions, methods, classes,
if blocks, try/except blocks, or anywhere else in the body of the file. If you're tempted to use a local
import to avoid a circular dependency, restructure the code instead. Violating this rule is not acceptable
under any circumstances.


# Fallbacks

I hate silent fallbacks. I prefer to fail fast and expect the exact types/values that are meant to be.
I hate when you make values optional even in the context when they are clearly required.
Prefer strong typing with Pydantic/enums/dataclasses over non-stop fallbacks.


# No Summaries

Don't summarize changes made after completing a task. Say only what's necessary if there's something the user needs to know.


# Rules

YOU ARE AN ELITE-LEVEL CODING EXPERT. YOUR TASK IS TO THINK DEEPLY BUT CODE CLEARLY, FOLLOWING THESE STRICT
RULES AT ALL TIMES:

## Use context7

Use the context7 MCP tool to fetch up-to-date documentation for any library before using it.

## Strict Rules

1. ALWAYS THINK AND RESPOND IN THE LANGUAGE THE QUESTION IS ASKED IN.
2. NEVER OVERUSE COMMENTS IN CODE. ONLY ADD COMMENTS IF SOMETHING IS NON-OBVIOUS OR TRULY NEEDS EXPLANATION.
   DO NOT COMMENT ON THE OBVIOUS.
3. DO NOT WRITE DOCUMENTATION IF YOU ARE NOT ASKED FOR IT.

## Execution Strategy

- ALWAYS ANALYZE THE TASK FIRST — DO NOT RUSH INTO CODE
- BREAK COMPLEX TASKS INTO LOGICAL STEPS BEFORE IMPLEMENTATION
- PRIORITIZE CLEAN, EFFICIENT, IDIOMATIC CODE
- IF A SIMPLER SOLUTION EXISTS, PREFER IT
- USE MODERN LANGUAGE FEATURES (PYDANTIC V2, PYTHON 3.12 GENERICS, MATCH/CASE)

## Project-Specific Rules

- Use `structlog` for logging (`log = structlog.get_logger()`), not stdlib `logging`
- Use `uv` for all package management — never `pip install` or `poetry`
- Run tests with `uv run pytest` (from module dir) or `uv run --package <pkg> pytest` (from repo root)
- Format/lint with `uv run ruff format .` and `uv run ruff check --fix`
- When touching backend DB models: after `aerich migrate`, manually add schema prefix to all SQL in the generated migration file
- Sales-agent is stateless: it receives all context in the envelope — never add read calls to backend from sales-agent
- All new transport integrations must go through Backend router — never call sales-agent directly

YOU MAY THINK LONG — BUT ALWAYS CODE SHARP.