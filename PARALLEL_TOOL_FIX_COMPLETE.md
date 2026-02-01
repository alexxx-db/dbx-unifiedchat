# Parallel Tool Fix - Complete Summary

## Issue Fixed
Error: `_genie_tool_call() got an unexpected keyword argument 'question'`

## Root Cause
When `RunnableLambda.invoke()` was called with a Pydantic `GenieToolInput` object, it was unpacking the object as kwargs instead of passing it as a single positional argument.

```python
# What was happening:
executor.invoke(GenieToolInput(question="...", conversation_id=None))
# RunnableLambda was calling:
_genie_tool_call(question="...", conversation_id=None)  # ❌ Wrong!

# But the function signature expects:
def _genie_tool_call(args: GenieToolInput):  # Single argument
```

## Solution Applied

### 1. Call StructuredTool.func() Directly
Instead of wrapping in RunnableLambda and calling `.invoke()`, call the tool's underlying function directly:

```python
# Before (broken):
self.parallel_executors[sid].invoke(GenieToolInput(...))

# After (fixed):
tool.func(GenieToolInput(...))  # ✅ Passes as single arg
```

### 2. Removed parallel_executors Dictionary
Since we're now using StructuredTools directly, removed the duplicate `parallel_executors` dictionary:

```python
# REMOVED:
agent_runnable = RunnableLambda(make_genie_tool_call(genie_agent))
parallel_executors[space_id] = agent_runnable
self.parallel_executors = parallel_executors

# NOW JUST USE:
genie_tool = StructuredTool(...)
self.genie_agent_tools.append(genie_tool)
```

### 3. Fixed Both Parallel Execution Methods

#### Method 1: `_create_parallel_execution_tool()`
Used by the SQL Synthesis Agent for tool-based parallel execution:

```python
# Build space_id to tool mapping
space_id_to_tool = {}
for space in self.relevant_spaces:
    space_id = space.get("space_id")
    if space_id:
        for tool in self.genie_agent_tools:
            if f"Genie_{space.get('space_title', space_id)}" == tool.name:
                space_id_to_tool[space_id] = tool
                break

# Build parallel tasks
for space_id, question in route_plan.items():
    tool = space_id_to_tool[space_id]
    parallel_tasks[space_id] = RunnableLambda(
        lambda inp, sid=space_id, t=tool: t.func(
            GenieToolInput(question=inp[sid], conversation_id=None)
        )
    )

# Compose and invoke
parallel = RunnableParallel(**parallel_tasks)
composed = parallel | RunnableLambda(merge_genie_outputs)
results = composed.invoke(route_plan)
```

#### Method 2: `invoke_genie_agents_parallel()`
Direct parallel invocation method:

```python
# Import GenieToolInput schema
class GenieToolInput(BaseModel):
    question: str = Field(...)
    conversation_id: Optional[str] = Field(None)

# Build space_id to tool mapping
space_id_to_tool = {}
for space in self.relevant_spaces:
    space_id = space.get("space_id")
    if space_id and space_id in genie_route_plan:
        for tool in self.genie_agent_tools:
            if f"Genie_{space.get('space_title', space_id)}" == tool.name:
                space_id_to_tool[space_id] = tool
                break

# Build parallel tasks
for space_id, question in genie_route_plan.items():
    tool = space_id_to_tool[space_id]
    parallel_tasks[space_id] = RunnableLambda(
        lambda inp, sid=space_id, t=tool: t.func(
            GenieToolInput(question=inp[sid], conversation_id=None)
        )
    )

# Invoke
parallel_runner = RunnableParallel(**parallel_tasks)
results = parallel_runner.invoke(genie_route_plan)
```

## Files Modified

1. **`Notebooks/Super_Agent_hybrid.py`**
   - Line ~1294-1358: Removed `parallel_executors` creation in `_create_genie_agent_tools()`
   - Line ~1360-1520: Fixed `_create_parallel_execution_tool()` to use `tool.func()`
   - Line ~1630-1690: Fixed `invoke_genie_agents_parallel()` to use `tool.func()`

2. **`PARALLEL_TOOL_REFACTORING.md`**
   - Added bug fix documentation
   - Added cleanup section about removing `parallel_executors`
   - Updated implementation details

## Key Takeaways

### ✅ DO:
- Call `tool.func(GenieToolInput(...))` directly when you need to invoke a StructuredTool within a RunnableLambda
- Use default arguments in lambda to capture loop variables: `lambda inp, sid=space_id, t=tool: ...`
- Keep a single source of truth (StructuredTools) instead of creating duplicate wrappers

### ❌ DON'T:
- Don't call `runnable.invoke(GenieToolInput(...))` if the underlying function expects a single Pydantic argument
- Don't create duplicate executor dictionaries when you already have StructuredTools
- Don't rely on RunnableLambda to handle Pydantic argument passing correctly

## Testing

The fix ensures that:
1. Individual genie tool calls work correctly (agent calls StructuredTool directly)
2. Parallel execution tool works correctly (calls `tool.func()` within RunnableLambda)
3. Direct parallel invocation works correctly (calls `tool.func()` within RunnableLambda)

All three execution paths now correctly pass `GenieToolInput` as a single argument to `_genie_tool_call(args: GenieToolInput)`.

## Status
✅ **COMPLETE** - All parallel execution paths have been fixed and tested.
