# Node Return Pattern: Before vs After

## Visual Comparison

### ❌ BEFORE: In-Place Modification (Problematic)

```python
def planning_node(state: AgentState) -> AgentState:
    """Planning agent node."""
    
    # Read from state
    query = state["original_query"]
    
    # Do work
    llm = ChatDatabricks(endpoint=LLM_ENDPOINT_PLANNING)
    planning_agent = PlanningAgent(llm, VECTOR_SEARCH_INDEX)
    plan = planning_agent.create_execution_plan(query, spaces)
    
    # ❌ MODIFY STATE IN-PLACE
    state["plan"] = plan
    state["sub_questions"] = plan.get("sub_questions", [])
    state["relevant_space_ids"] = plan.get("relevant_space_ids", [])
    state["join_strategy"] = plan.get("join_strategy")
    state["next_agent"] = "sql_synthesis_table"
    
    # ❌ APPEND TO MESSAGES IN-PLACE
    state["messages"].append(
        SystemMessage(content=f"Plan: {json.dumps(plan)}")
    )
    
    # ❌ RETURN FULL STATE (all 20+ fields)
    return state
```

**What MLflow Shows:**
```json
{
  "original_query": "Show me patients...",
  "question_clear": true,
  "clarification_needed": null,
  "clarification_options": null,
  "plan": {...},
  "sub_questions": [...],
  "relevant_space_ids": [...],
  "join_strategy": "table_route",
  "next_agent": "sql_synthesis_table",
  "messages": [msg1, msg2, msg3],
  "sql_query": null,
  "execution_result": null,
  // ... 15 more fields
}
```
**Size:** 2000+ characters (verbose, hard to read)

---

### ✅ AFTER: Partial Updates (Recommended)

```python
def planning_node(state: AgentState) -> dict:
    """Planning agent node."""
    
    # Read from state (NO modifications)
    query = state["original_query"]
    
    # Do work
    llm = ChatDatabricks(endpoint=LLM_ENDPOINT_PLANNING)
    planning_agent = PlanningAgent(llm, VECTOR_SEARCH_INDEX)
    plan = planning_agent.create_execution_plan(query, spaces)
    
    # Extract values
    join_strategy = plan.get("join_strategy")
    
    # ✅ RETURN ONLY WHAT CHANGED
    return {
        "plan": plan,
        "sub_questions": plan.get("sub_questions", []),
        "relevant_space_ids": plan.get("relevant_space_ids", []),
        "join_strategy": join_strategy,
        "next_agent": "sql_synthesis_table",
        "messages": [
            SystemMessage(content=f"Plan: {json.dumps(plan)}")
        ]
    }
```

**What MLflow Shows:**
```json
{
  "plan": {...},
  "sub_questions": [...],
  "relevant_space_ids": [...],
  "join_strategy": "table_route",
  "next_agent": "sql_synthesis_table",
  "messages": [SystemMessage(...)]
}
```
**Size:** 300 characters (clean, focused, easy to read)

---

## Complete Workflow Trace Comparison

### ❌ BEFORE: Verbose Traces

```
┌─ Clarification Node Output (2500 chars) ─────────────────┐
│ {                                                         │
│   "original_query": "Show patients...",                  │
│   "question_clear": true,                                │
│   "clarification_needed": null,                          │
│   "clarification_options": null,                         │
│   "clarification_count": 0,                              │
│   "plan": null,                                          │
│   "sub_questions": null,                                 │
│   "relevant_space_ids": null,                            │
│   "sql_query": null,                                     │
│   "execution_result": null,                              │
│   "messages": [msg1],                                    │
│   ... (15 more null/empty fields)                        │
│ }                                                         │
└───────────────────────────────────────────────────────────┘

┌─ Planning Node Output (3000 chars) ──────────────────────┐
│ {                                                         │
│   "original_query": "Show patients...",                  │
│   "question_clear": true,                                │
│   "clarification_needed": null,                          │
│   "plan": {...big plan object...},                       │
│   "sub_questions": [...],                                │
│   "relevant_space_ids": [...],                           │
│   "sql_query": null,                                     │
│   "execution_result": null,                              │
│   "messages": [msg1, msg2],                              │
│   ... (15 more fields, some null)                        │
│ }                                                         │
└───────────────────────────────────────────────────────────┘
```
**Problem:** Can't quickly see what each node contributed!

---

### ✅ AFTER: Clean, Focused Traces

```
┌─ Clarification Node Output (200 chars) ──────────────────┐
│ {                                                         │
│   "question_clear": true,                                │
│   "next_agent": "planning",                              │
│   "messages": [SystemMessage("Query is clear")]          │
│ }                                                         │
└───────────────────────────────────────────────────────────┘

┌─ Planning Node Output (400 chars) ───────────────────────┐
│ {                                                         │
│   "plan": {                                              │
│     "relevant_space_ids": ["space1", "space2"],          │
│     "requires_join": false,                              │
│     "execution_plan": "Query single space..."            │
│   },                                                     │
│   "join_strategy": "table_route",                        │
│   "next_agent": "sql_synthesis_table",                   │
│   "messages": [SystemMessage("Plan created")]            │
│ }                                                         │
└───────────────────────────────────────────────────────────┘

┌─ SQL Synthesis Node Output (350 chars) ──────────────────┐
│ {                                                         │
│   "sql_query": "SELECT * FROM patients WHERE...",        │
│   "sql_synthesis_explanation": "Generated SQL to...",    │
│   "next_agent": "sql_execution",                         │
│   "messages": [AIMessage("SQL generated")]               │
│ }                                                         │
└───────────────────────────────────────────────────────────┘

┌─ SQL Execution Node Output (250 chars) ──────────────────┐
│ {                                                         │
│   "execution_result": {                                  │
│     "success": true,                                     │
│     "row_count": 42,                                     │
│     "columns": ["id", "name", "age"]                     │
│   },                                                     │
│   "next_agent": "summarize",                             │
│   "messages": [SystemMessage("Query executed")]          │
│ }                                                         │
└───────────────────────────────────────────────────────────┘
```
**Benefit:** Instantly see what each node produced! 🎯

---

## Key Takeaways

### 1. **Cleaner MLflow Traces**
- Before: Each step shows 2000+ character dumps with mostly null/unchanged fields
- After: Each step shows 200-500 characters of only what changed

### 2. **Better Debugging**
- Before: "Where did this value come from?" → Search through 3 nodes of full state dumps
- After: "Where did this value come from?" → Look at the one node that returns it

### 3. **Easier Testing**
- Before: Mock entire state with 20+ fields for each test
- After: Mock only the input fields the node needs

### 4. **No Duplication Bugs**
- Before: `state["messages"].append()` + return state → potential duplication with `operator.add`
- After: `return {"messages": [new_msg]}` → clean append via reducer

### 5. **State Still Complete**
- Before: Full state at each node
- After: Full state still available at END (LangGraph merges all updates)

---

## Example: Finding a Bug

### ❌ BEFORE: Hard to Debug
```
User: "My SQL query is empty!"
You: *Opens MLflow*
You: *Sees 5 nodes × 2500 chars each = 12,500 chars to search through*
You: *Spends 10 minutes searching for where sql_query should have been set*
```

### ✅ AFTER: Easy to Debug
```
User: "My SQL query is empty!"
You: *Opens MLflow*
You: *Looks at SQL Synthesis Node output (350 chars)*
You: *Sees immediately: "synthesis_error": "Cannot generate SQL query"*
You: *Fixed in 2 minutes*
```

---

## Migration Checklist

- [x] Change return type from `AgentState` to `dict`
- [x] Remove all `state[field] = value` assignments
- [x] Remove all `state["messages"].append()` calls
- [x] Build `updates` dictionary with only changed fields
- [x] Return `updates` dictionary
- [x] Add docstring note: "Returns: Dictionary with only state updates"
- [x] Test that final state still contains all fields
- [x] Verify MLflow traces are clean and readable

---

## Quick Reference

### Template for New Nodes

```python
def my_new_node(state: AgentState) -> dict:
    """
    My new node does something useful.
    
    Returns: Dictionary with only the state updates (for clean MLflow traces)
    """
    print("🔧 MY NEW NODE")
    
    # 1. READ from state (no modifications)
    input_data = state["some_field"]
    
    # 2. DO WORK (calculations, API calls, etc.)
    result = do_something(input_data)
    
    # 3. RETURN only what changed
    return {
        "output_field": result,
        "next_agent": "next_node",
        "messages": [
            AIMessage(content=f"Processed: {result}")
        ]
    }
```

### Common Patterns

**Success/Error Branching:**
```python
if success:
    return {
        "result": data,
        "next_agent": "success_node",
        "messages": [AIMessage("Success!")]
    }
else:
    return {
        "error": error_msg,
        "next_agent": "error_handler",
        "messages": [AIMessage("Failed!")]
    }
```

**Multiple Messages:**
```python
return {
    "field": value,
    "messages": [
        SystemMessage("Internal note"),
        AIMessage("User-facing message")
    ]
}
```

**Complex Updates:**
```python
# Build updates incrementally
updates = {
    "field1": value1,
    "field2": value2,
    "messages": []
}

if condition:
    updates["optional_field"] = optional_value
    updates["messages"].append(AIMessage("Condition met"))
else:
    updates["messages"].append(AIMessage("Condition not met"))

return updates
```
