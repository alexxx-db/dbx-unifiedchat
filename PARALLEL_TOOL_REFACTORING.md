# Parallel Execution Tool Refactoring

## Summary
Refactored `_create_parallel_execution_tool()` method to follow LangChain best practices using `RunnableParallel` + `StructuredTool` pattern.

## Bug Fix (v2)
Fixed error: `_genie_tool_call() got an unexpected keyword argument 'question'`

**Root Cause:** When calling `RunnableLambda.invoke(GenieToolInput(...))`, the Pydantic object was being unpacked as kwargs instead of passed as a single argument.

**Solution:** 
1. Instead of calling the executor's `.invoke()` method, call the StructuredTool's underlying `.func` directly
2. Removed `parallel_executors` entirely since we now use StructuredTools directly
3. Fixed both `_create_parallel_execution_tool()` and `invoke_genie_agents_parallel()` methods

```python
# Before (broken):
self.parallel_executors[sid].invoke(GenieToolInput(...))

# After (fixed):
tool.func(GenieToolInput(...))
```

This ensures the `GenieToolInput` object is passed correctly as a single argument to `_genie_tool_call(args: GenieToolInput)`.

### Complete Fix Applied To:
1. ✅ `_create_parallel_execution_tool()` - Used by SQL Synthesis Agent for parallel execution
2. ✅ `invoke_genie_agents_parallel()` - Direct parallel invocation method
3. ✅ Removed `parallel_executors` dictionary - No longer needed, use StructuredTools directly

## Changes Made

### 1. Input Schema with Pydantic
**Before:** String-based JSON input
```python
def invoke_parallel_genie_agents(genie_route_plan: str) -> str:
    route_plan = json.loads(genie_route_plan)
```

**After:** Type-safe Pydantic schema
```python
class ParallelGenieInput(BaseModel):
    genie_route_plan: Dict[str, str] = Field(
        ..., 
        description="Dictionary mapping space_id to question"
    )

def invoke_parallel_genie_agents(args: ParallelGenieInput) -> Dict[str, Any]:
    route_plan = args.genie_route_plan
```

### 2. RunnableParallel Pattern
**Before:** Manual parallel execution with try/catch
```python
parallel_tasks = {}
for space_id in route_plan.keys():
    parallel_tasks[space_id] = RunnableLambda(...)
parallel_runner = RunnableParallel(**parallel_tasks)
results = parallel_runner.invoke(route_plan)
```

**After:** Composed chain with merge function
```python
# Build parallel tasks
parallel_tasks = {
    space_id: RunnableLambda(
        lambda inp, sid=space_id: self.parallel_executors[sid].invoke(
            GenieToolInput(question=inp[sid], conversation_id=None)
        )
    )
    for space_id, question in route_plan.items()
}

# Compose with merge function
parallel = RunnableParallel(**parallel_tasks)
composed = parallel | RunnableLambda(merge_genie_outputs)
results = composed.invoke(route_plan)
```

### 3. Merge Function
**Before:** Inline extraction logic
```python
extracted_results = {}
for space_id, result in results.items():
    extracted = {...}
    # ... extraction logic ...
    extracted_results[space_id] = extracted
```

**After:** Dedicated merge function
```python
def merge_genie_outputs(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge outputs from multiple Genie agents into a unified result.
    """
    merged_results = {}
    for space_id, result in outputs.items():
        extracted = {...}
        # Handle direct dict output from StructuredTool
        if isinstance(result, dict):
            extracted["answer"] = result.get("answer", "")
            extracted["sql"] = result.get("sql", "")
            # ...
        # Handle message-based output (fallback)
        elif isinstance(result, dict) and "messages" in result:
            # ... extract from messages ...
        merged_results[space_id] = extracted
    return merged_results
```

### 4. StructuredTool Instead of @tool Decorator
**Before:** Simple function decorator
```python
from langchain_core.tools import tool as langchain_tool

parallel_tool = langchain_tool(invoke_parallel_genie_agents)
parallel_tool.name = "invoke_parallel_genie_agents"
parallel_tool.description = """..."""
```

**After:** Explicit StructuredTool with schema
```python
from langchain.tools import StructuredTool

parallel_tool = StructuredTool(
    name="invoke_parallel_genie_agents",
    description="...",
    args_schema=ParallelGenieInput,
    func=invoke_parallel_genie_agents,
)
```

### 5. Return Type
**Before:** JSON string
```python
return json.dumps(extracted_results, indent=2)
```

**After:** Dictionary
```python
return results  # Dict[str, Any]
```

## Benefits

1. **Type Safety**: Pydantic schema provides compile-time and runtime type checking
2. **Better Tool Documentation**: LLM can understand the exact structure of inputs/outputs
3. **Cleaner Composition**: `parallel | RunnableLambda(merge)` pattern is more idiomatic
4. **Easier Testing**: Dict return values are easier to test than JSON strings
5. **Better Error Messages**: Pydantic validation provides clear error messages
6. **Follows LangChain Best Practices**: Aligns with official LangChain patterns

## Key Pattern Elements

### 1. RunnableParallel
```python
parallel = RunnableParallel(
    task1=lambda x: agent1.invoke(x["input1"]),
    task2=lambda x: agent2.invoke(x["input2"]),
)
```

### 2. Merge Function
```python
def merge_outputs(outputs: Dict[str, Any]) -> Dict[str, Any]:
    # Combine outputs from parallel tasks
    return combined_result
```

### 3. Composition
```python
composed = parallel | RunnableLambda(merge_outputs)
```

### 4. StructuredTool
```python
class InputSchema(BaseModel):
    field: str = Field(..., description="...")

tool = StructuredTool(
    name="tool_name",
    description="...",
    args_schema=InputSchema,
    func=lambda args: composed.invoke(args.field),
)
```

## Cleanup: Removed parallel_executors

**Before:** Created separate `RunnableLambda` wrappers stored in `self.parallel_executors`:
```python
# OLD CODE - REMOVED
parallel_executors = {}
for space in self.relevant_spaces:
    agent_runnable = RunnableLambda(make_genie_tool_call(genie_agent))
    agent_runnable.name = genie_agent_name
    agent_runnable.description = description
    parallel_executors[space_id] = agent_runnable
self.parallel_executors = parallel_executors
```

**After:** Use StructuredTools directly:
```python
# NEW CODE - CLEANER
genie_tool = StructuredTool(
    name=genie_agent_name,
    description=description,
    args_schema=GenieToolInput,
    func=make_genie_tool_call(genie_agent),
)
self.genie_agent_tools.append(genie_tool)
# No parallel_executors needed!
```

**Benefits:**
- Eliminates code duplication
- Single source of truth (StructuredTools)
- Cleaner architecture
- No confusion about which to use

## Implementation Details

### Space ID to Tool Mapping
To enable parallel execution, the code builds a mapping from `space_id` to `StructuredTool`:

```python
space_id_to_tool = {}
for space in self.relevant_spaces:
    space_id = space.get("space_id")
    if space_id:
        for tool in self.genie_agent_tools:
            space_title = space.get("space_title", space_id)
            if f"Genie_{space_title}" == tool.name:
                space_id_to_tool[space_id] = tool
                break
```

### Parallel Task Construction
Each parallel task directly invokes the tool's underlying function:

```python
parallel_tasks = {}
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

**Key Points:**
- Use default arguments (`sid=space_id, t=tool`) to capture loop variables in closure
- Call `tool.func()` directly instead of `tool.invoke()` to avoid Pydantic unpacking issues
- Pass `GenieToolInput` as a single object, not unpacked kwargs

## Testing Recommendations

Test the refactored tool with:
1. Single space query
2. Multiple space queries (2-3 spaces)
3. Invalid space_id (error handling)
4. Empty route_plan (error handling)
5. Mixed success/failure results

Example test:
```python
tool_input = ParallelGenieInput(
    genie_route_plan={
        "space_id_1": "Get member demographics",
        "space_id_2": "Get benefit costs"
    }
)
result = parallel_tool.invoke(tool_input)
assert "space_id_1" in result
assert result["space_id_1"]["sql"]
```
