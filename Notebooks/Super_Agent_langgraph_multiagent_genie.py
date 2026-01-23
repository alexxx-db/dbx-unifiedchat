# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # Multi-Agent System for Genie Space Querying with LangGraph Supervisor
# MAGIC 
# MAGIC This notebook implements a sophisticated multi-agent system using Mosaic AI Agent Framework and LangGraph's `create_supervisor` pattern.
# MAGIC 
# MAGIC ## 🎯 System Architecture
# MAGIC 
# MAGIC The system uses a **supervisor-based multi-agent architecture** with 6 specialized agents:
# MAGIC 
# MAGIC 1. **Clarification Agent**: 
# MAGIC    - Validates query clarity with lenient approach
# MAGIC    - Dynamically loads space context from Delta table
# MAGIC    - Requests clarification only when truly needed (max 1 time)
# MAGIC    - Preserves original query through clarification flow
# MAGIC 
# MAGIC 2. **Planning Agent**: 
# MAGIC    - Analyzes queries and searches vector index for relevant spaces
# MAGIC    - Creates detailed execution plans with genie_route_plan
# MAGIC    - Determines optimal strategy: table_route or genie_route
# MAGIC    - Identifies join requirements and sub-questions
# MAGIC 
# MAGIC 3. **SQL Synthesis Agent (Table Route)**: 
# MAGIC    - Generates SQL using UC metadata functions intelligently
# MAGIC    - Queries metadata on-demand with minimal sufficiency
# MAGIC    - Best for complex joins across multiple tables
# MAGIC    - Returns SQL with detailed explanation
# MAGIC 
# MAGIC 4. **SQL Synthesis Agent (Genie Route)**: 
# MAGIC    - Routes queries to individual Genie Space Agents
# MAGIC    - **OPTIMIZED**: Only creates Genie agents for relevant spaces (not all spaces)
# MAGIC    - Combines SQL fragments from multiple Genie agents
# MAGIC    - Includes retry logic and disaster recovery
# MAGIC    - Best for decomposable queries across independent spaces
# MAGIC 
# MAGIC 5. **SQL Execution Agent**: 
# MAGIC    - Executes generated SQL queries on delta tables
# MAGIC    - Returns structured results with success status
# MAGIC    - Comprehensive error handling and formatting
# MAGIC    - Supports multiple output formats (dict, json, markdown)
# MAGIC 
# MAGIC 6. **Result Summarize Agent** (NEW!): 
# MAGIC    - Generates comprehensive natural language summary
# MAGIC    - Includes: original query, plan, SQL, results, errors
# MAGIC    - Formats results in user-friendly way
# MAGIC    - **MANDATORY**: Every workflow ends with this agent
# MAGIC 
# MAGIC ## 🚀 Key Features
# MAGIC 
# MAGIC - ✅ **Supervisor Pattern**: Uses LangGraph's `create_supervisor` for intelligent agent routing
# MAGIC - ✅ **Comprehensive State**: Full observability with AgentState TypedDict
# MAGIC - ✅ **Dynamic Context Loading**: Clarification agent loads fresh space context (no redeployment needed)
# MAGIC - ✅ **Optimized Genie Route**: Only creates Genie agents for relevant spaces
# MAGIC - ✅ **Clarification Flow**: Preserves context and combines original query with clarification
# MAGIC - ✅ **Result Summarization**: Every workflow ends with comprehensive user-friendly summary
# MAGIC - ✅ **Streaming Support**: Full streaming via ResponsesAgent wrapper
# MAGIC - ✅ **Error Handling**: Graceful handling with explanations at every step
# MAGIC 
# MAGIC ## 📋 Prerequisites
# MAGIC 
# MAGIC Before running this notebook, ensure:
# MAGIC 1. **Unity Catalog Functions** registered:
# MAGIC    - `get_space_summary` - High-level space information
# MAGIC    - `get_table_overview` - Table-level metadata
# MAGIC    - `get_column_detail` - Column-level metadata
# MAGIC    - `get_space_details` - Complete metadata (last resort)
# MAGIC 2. **Genie Spaces** created and configured
# MAGIC 3. **Vector Search Index** created for space summaries
# MAGIC 4. **Delta Table** with enriched genie docs chunks

# COMMAND ----------

# MAGIC %pip install -U -qqq langgraph-supervisor==0.0.30 mlflow[databricks] databricks-langchain databricks-vectorsearch databricks-agents uv 
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Define the Multi-Agent System

# COMMAND ----------

%%writefile agent.py
import json
import re
from typing import Dict, List, Optional, Any, Generator, Annotated
from typing_extensions import TypedDict
from uuid import uuid4
import operator

import mlflow
from databricks_langchain import (
    ChatDatabricks,
    DatabricksFunctionClient,
    UCFunctionToolkit,
    VectorSearchRetrieverTool,
    set_uc_function_client,
)
from databricks_langchain.genie import GenieAgent
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph
from langgraph_supervisor import create_supervisor
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
    output_to_responses_items_stream,
    to_chat_completions_input,
)
from pydantic import BaseModel
from functools import partial

client = DatabricksFunctionClient()
set_uc_function_client(client)

########################################
# Configuration
########################################

# TODO: Update these configuration values
CATALOG = "yyang"
SCHEMA = "multi_agent_genie"
TABLE_NAME = f"{CATALOG}.{SCHEMA}.enriched_genie_docs_chunks"
VECTOR_SEARCH_INDEX = f"{CATALOG}.{SCHEMA}.enriched_genie_docs_chunks_vs_index"
LLM_ENDPOINT_NAME = "databricks-claude-sonnet-4-5"
LLM_ENDPOINT_PLANNING = "databricks-claude-haiku-4-5"  # Planning can use lighter model
LLM_ENDPOINT_CLARIFICATION = "databricks-claude-haiku-4-5"  # Fast model for clarity checks
LLM_ENDPOINT_SQL_SYNTHESIS = "databricks-claude-sonnet-4-5"  # Powerful model for SQL
LLM_ENDPOINT_SUMMARIZE = "databricks-claude-haiku-4-5"  # Fast model for summarization

########################################
# Unity Catalog Functions (Prerequisites)
########################################

# IMPORTANT: Before running this agent, ensure UC functions are registered:
# The following UC functions must exist in your catalog:
# 1. {CATALOG}.{SCHEMA}.get_space_summary - High-level space information
# 2. {CATALOG}.{SCHEMA}.get_table_overview - Table-level metadata
# 3. {CATALOG}.{SCHEMA}.get_column_detail - Column-level metadata
# 4. {CATALOG}.{SCHEMA}.get_space_details - Complete metadata (last resort)
#
# To register these functions, see the Super_Agent_hybrid.py notebook
# or the register_uc_functions.py script for the complete SQL CREATE FUNCTION statements.
#
# These functions query the enriched_genie_docs_chunks table at different granularities
# and are used by the SQL Synthesis Table Route Agent to gather metadata intelligently.

########################################
# Agent State Definition
########################################

class AgentState(TypedDict):
    """
    Explicit state that flows through the multi-agent system.
    This provides full observability and makes debugging easier.
    """
    # Input
    original_query: str
    
    # Clarification
    question_clear: bool
    clarification_needed: Optional[str]
    clarification_options: Optional[List[str]]
    clarification_count: Optional[int]  # Track clarification attempts (max 1)
    user_clarification_response: Optional[str]  # User's response to clarification
    clarification_message: Optional[str]  # The clarification question asked by agent
    combined_query_context: Optional[str]  # Combined context: original + clarification + response
    
    # Planning
    plan: Optional[Dict[str, Any]]
    sub_questions: Optional[List[str]]
    requires_multiple_spaces: Optional[bool]
    relevant_space_ids: Optional[List[str]]
    relevant_spaces: Optional[List[Dict[str, Any]]]
    vector_search_relevant_spaces_info: Optional[List[Dict[str, str]]]
    requires_join: Optional[bool]
    join_strategy: Optional[str]  # "table_route" or "genie_route"
    execution_plan: Optional[str]
    genie_route_plan: Optional[Dict[str, str]]
    
    # SQL Synthesis
    sql_query: Optional[str]
    sql_synthesis_explanation: Optional[str]  # Agent's explanation/reasoning
    synthesis_error: Optional[str]
    has_sql: Optional[bool]
    
    # Execution
    execution_result: Optional[Dict[str, Any]]
    execution_error: Optional[str]
    
    # Summary
    final_summary: Optional[str]  # Natural language summary of the workflow execution
    
    # Control flow
    next_agent: Optional[str]
    messages: Annotated[List, operator.add]

########################################
# Agent Type Definitions
########################################

class InCodeSubAgent(BaseModel):
    tools: list[str]
    name: str
    description: str
    system_prompt: Optional[str] = None


class GenieSubAgent(BaseModel):
    space_id: str
    name: str
    description: str


TOOLS = []

########################################
# Helper Functions
########################################

def stringify_content(state):
    """Converts list content to JSON string for better parsing."""
    msgs = state["messages"]
    if isinstance(msgs[-1].content, list):
        msgs[-1].content = json.dumps(msgs[-1].content, indent=4)
    return {"messages": msgs}


def enforce_limit(messages, n=10):
    """Appends an instruction to the last user message to limit the result size."""
    last = messages[-1] if messages else {"content": ""}
    content = last.get("content", "") if isinstance(last, dict) else last.content
    return f"{content}\n\nPlease limit the result to at most {n} rows."


def extract_genie_sql(resp: dict) -> tuple:
    """Extracts thinking, SQL, and answer from Genie agent response."""
    thinking = None
    sql = None
    answer = None

    for msg in resp["messages"]:
        if isinstance(msg, AIMessage):
            if msg.name == "query_reasoning":
                thinking = msg.content
            elif msg.name == "query_sql":
                sql = msg.content
            elif msg.name == "query_result":
                answer = msg.content
    return thinking, sql, answer


def query_delta_table(table_name: str, filter_field: str, filter_value: str, select_fields: List[str] = None):
    """Query a delta table with a filter condition."""
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    
    if select_fields:
        fields_str = ", ".join(select_fields)
    else:
        fields_str = "*"
    
    df = spark.sql(f"""
        SELECT {fields_str}
        FROM {table_name}
        WHERE {filter_field} = '{filter_value}'
    """)
    
    return df


def load_space_context(table_name: str) -> Dict[str, str]:
    """
    Load space context from Delta table.
    Called fresh on each request - no caching for dynamic refresh.
    
    Args:
        table_name: Full table name (catalog.schema.table)
        
    Returns:
        Dictionary mapping space_id to searchable_content
    """
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    
    df = spark.sql(f"""
        SELECT space_id, searchable_content
        FROM {table_name}
        WHERE chunk_type = 'space_summary'
    """)
    
    context = {row["space_id"]: row["searchable_content"] 
               for row in df.collect()}
    
    print(f"✓ Loaded {len(context)} Genie spaces for context")
    return context


########################################
# Create Genie Agents
########################################

def create_genie_agents_from_relevant_spaces(relevant_spaces: List[Dict[str, Any]]) -> List:
    """
    Create Genie agents as tools only for relevant spaces (not all spaces).
    Uses RunnableLambda wrapper pattern to avoid closure issues.
    
    Args:
        relevant_spaces: List of relevant spaces from PlanningAgent's Vector Search.
                        Each dict should have: space_id, space_title, searchable_content
    
    Returns:
        List of Genie agent tools
    """
    genie_agent_tools = []
    
    print(f"  Creating Genie agent tools for {len(relevant_spaces)} relevant spaces...")
    
    for space in relevant_spaces:
        space_id = space.get("space_id")
        space_title = space.get("space_title", space_id)
        searchable_content = space.get("searchable_content", "")
        
        if not space_id:
            print(f"  ⚠ Warning: Space missing space_id, skipping: {space}")
            continue
        
        genie_agent_name = f"Genie_{space_title}"
        description = searchable_content
        
        # Create Genie agent
        genie_agent = GenieAgent(
            genie_space_id=space_id,
            genie_agent_name=genie_agent_name,
            description=description,
            include_context=True,
            message_processor=lambda msgs: enforce_limit(msgs, n=5)
        )
        
        # Wrap the agent call in a function that only takes a string argument
        # This function also returns a function to avoid closure issues
        def make_agent_invoker(agent):
            return lambda question: agent.invoke(
                {"messages": [{"role": "user", "content": question}]}
            )
        
        runnable = RunnableLambda(make_agent_invoker(genie_agent))
        runnable.name = genie_agent_name
        runnable.description = description
        
        genie_agent_tools.append(
            runnable.as_tool(
                name=genie_agent_name,
                description=description,
                arg_types={"question": str}
            )
        )
        
        print(f"  ✓ Created Genie agent tool: {genie_agent_name} ({space_id})")
    
    return genie_agent_tools


def create_genie_agents(table_name: str) -> tuple:
    """Create Genie agents from space summary data."""
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    
    # Query space summary data
    space_summary_df = query_delta_table(
        table_name=table_name,
        filter_field="chunk_type",
        filter_value="space_summary",
        select_fields=["space_id", "space_title", "searchable_content"]
    )
    
    genie_agents = []
    genie_agent_tools = []
    genie_subagent_configs = []
    
    for row in space_summary_df.collect():
        space_id = row["space_id"]
        space_title = row["space_title"]
        searchable_content = row["searchable_content"]
        genie_agent_name = f"Genie_{space_title}"
        description = searchable_content
        
        # Create Genie agent
        genie_agent = GenieAgent(
            genie_space_id=space_id,
            genie_agent_name=genie_agent_name,
            description=description,
            include_context=True,
            message_processor=lambda msgs: enforce_limit(msgs, n=10)
        )
        
        genie_agents.append(genie_agent)
        
        # Wrap agent for tool use
        def make_agent_invoker(agent):
            return lambda question: agent.invoke(
                {"messages": [{"role": "user", "content": question}]}
            )
        
        runnable = RunnableLambda(make_agent_invoker(genie_agent))
        runnable.name = genie_agent_name
        runnable.description = description
        
        genie_agent_tools.append(
            runnable.as_tool(
                name=genie_agent_name,
                description=description,
                arg_types={"question": str}
            )
        )
        
        # Store config for supervisor
        genie_subagent_configs.append(
            GenieSubAgent(
                space_id=space_id,
                name=genie_agent_name,
                description=description
            )
        )
    
    return genie_agents, genie_agent_tools, genie_subagent_configs, space_summary_df


########################################
# Create LangGraph Supervisor Agent
########################################

def create_langgraph_supervisor(
    llm: Runnable,
    in_code_agents: list[InCodeSubAgent] = [],
    additional_agents: list[Runnable] = [],
):
    """Create a LangGraph supervisor with specialized agents."""
    agents = []
    agent_descriptions = ""

    # Process inline code agents
    for agent in in_code_agents:
        agent_descriptions += f"- {agent.name}: {agent.description}\n"
        
        # Handle agents with tools
        if agent.tools:
            uc_toolkit = UCFunctionToolkit(function_names=agent.tools)
            TOOLS.extend(uc_toolkit.tools)
            agent_tools = uc_toolkit.tools
        else:
            agent_tools = []
        
        # Create agent with custom system prompt if provided
        if agent.system_prompt:
            created_agent = create_agent(
                llm, 
                tools=agent_tools, 
                name=agent.name,
                system_prompt=agent.system_prompt
            )
        else:
            created_agent = create_agent(llm, tools=agent_tools, name=agent.name)
        
        agents.append(created_agent)

    # Add additional pre-built agents
    for agent in additional_agents:
        agents.append(agent)
        # Extract description from agent if available
        agent_name = getattr(agent, 'name', 'unknown_agent')
        agent_desc = getattr(agent, 'description', 'Additional agent')
        agent_descriptions += f"- {agent_name}: {agent_desc}\n"

    # Supervisor prompt
    prompt = f"""
You are a supervisor in a multi-agent system for analyzing and querying Genie spaces.

Your role is to:
1. Understand the user's query
2. Route to appropriate agents in the correct sequence
3. Coordinate handoffs between agents
4. Ensure comprehensive results are generated

Available Agents:
{agent_descriptions}

REQUIRED Workflow (ALL paths must complete ALL steps):
1. **Clarification Agent**: Validates query clarity first
   - If unclear → Ask for clarification and wait for user response
   - If clear → Proceed to Planning Agent

2. **Planning Agent**: Analyzes query and creates execution plan
   - Searches vector index for relevant spaces
   - Determines strategy: table_route or genie_route
   - Creates detailed execution plan

3. **SQL Synthesis Agent** (choose ONE based on plan):
   - **Table Route**: Uses UC metadata functions for direct SQL generation
   - **Genie Route**: Routes to multiple Genie agents and combines SQL
   - If synthesis fails → Skip to Result Summarize Agent

4. **SQL Execution Agent**: Executes the generated SQL
   - Runs SQL on delta tables
   - Returns structured results with success status
   - If execution fails → Still proceed to Result Summarize Agent

5. **Result Summarize Agent** (REQUIRED - ALWAYS call this agent last):
   - Generates comprehensive natural language summary
   - Includes: original query, plan, SQL, results, errors
   - Formats results in user-friendly way
   - This is MANDATORY - every workflow must end here

CRITICAL RULES:
- ALWAYS route to Result Summarize Agent as the final step
- Result Summarize Agent must receive complete state information
- Never skip the summarization step
- Maintain full context throughout the workflow

Your coordination ensures users receive:
- Clear execution plan
- Generated SQL query (if successful)
- Query results (if executed)
- Comprehensive summary of the entire workflow
- Proper error handling and explanations
    """

    return create_supervisor(
        agents=agents,
        model=llm,
        prompt=prompt,
        add_handoff_messages=False,
        output_mode="full_history",
    ).compile()


##########################################
# Wrap LangGraph Supervisor as a ResponsesAgent
##########################################

class LangGraphResponsesAgent(ResponsesAgent):
    """
    Wrapper class to make the Supervisor Agent compatible with Databricks Model Serving.
    
    This class implements the ResponsesAgent interface required for deployment
    to Databricks Model Serving endpoints with proper streaming support.
    
    Supports three scenarios:
    1. New query: Fresh start with new original_query
    2. Clarification response: User answering agent's clarification question
    3. Follow-up query: New query with access to previous conversation context
    """
    
    def __init__(self, agent: CompiledStateGraph):
        """
        Initialize the ResponsesAgent wrapper.
        
        Args:
            agent: The compiled LangGraph workflow (supervisor)
        """
        self.agent = agent

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        """
        Make a prediction (non-streaming).
        
        Args:
            request: The request containing input messages
            
        Returns:
            ResponsesAgentResponse with output items
        """
        outputs = [
            event.item
            for event in self.predict_stream(request)
            if event.type == "response.output_item.done"
        ]
        return ResponsesAgentResponse(output=outputs, custom_outputs=request.custom_inputs)

    def predict_stream(
        self,
        request: ResponsesAgentRequest,
    ) -> Generator[ResponsesAgentStreamEvent, None, None]:
        """
        Make a streaming prediction.
        
        Handles three scenarios:
        1. New query: Fresh start with new original_query
        2. Clarification response: User answering agent's clarification question
        3. Follow-up query: New query with access to previous conversation context
        
        Args:
            request: The request containing:
                - input: List of messages (user query is the last message)
                - custom_inputs: Dict with optional keys:
                    - thread_id (str): Thread identifier for conversation continuity (default: "default")
                    - is_clarification_response (bool): Set to True when user is answering clarification
                    - clarification_count (int): Preserved from previous state
                    - original_query (str): Preserved from previous state for clarification responses
                    - clarification_message (str): Preserved from previous state for clarification responses
            
        Yields:
            ResponsesAgentStreamEvent for each step in the workflow
        """
        # Convert request input to chat completions format
        cc_msgs = to_chat_completions_input([i.model_dump() for i in request.input])
        
        # Get the latest user message
        latest_query = cc_msgs[-1]["content"] if cc_msgs else ""
        
        # Check if this is a clarification response
        is_clarification_response = request.custom_inputs.get("is_clarification_response", False) if request.custom_inputs else False
        
        # Initialize state based on scenario
        if is_clarification_response:
            # Scenario 2: Clarification Response
            # User is answering the agent's clarification question
            # We need to preserve state from previous call and add user's response
            
            # Get preserved state from custom_inputs (caller must pass these)
            original_query = request.custom_inputs.get("original_query", latest_query)
            clarification_message = request.custom_inputs.get("clarification_message", "")
            clarification_count = request.custom_inputs.get("clarification_count", 1)
            
            initial_state = {
                # Preserve from previous state
                "original_query": original_query,  # Keep original unchanged
                "clarification_message": clarification_message,  # Keep clarification question
                "clarification_count": clarification_count,  # Keep count
                
                # Add user's clarification response
                "user_clarification_response": latest_query,
                "question_clear": False,  # Will be set to True by clarification agent
                
                # Messages
                "messages": [HumanMessage(content=f"Clarification response: {latest_query}")],
            }
            
        else:
            # Scenario 1 & 3: New Query or Follow-Up Query
            initial_state = {
                "original_query": latest_query,
                "question_clear": False,
                "messages": [
                    SystemMessage(content="""You are a multi-agent Q&A analysis system.
Your role is to help users query and analyze cross-domain data.

Guidelines:
- Always explain your reasoning and execution plan
- Validate SQL queries before execution
- Provide clear, comprehensive summaries
- If information is missing, ask for clarification (max once)
- Use UC functions and Genie agents to generate accurate SQL
- Return results with proper context and explanations"""),
                    HumanMessage(content=latest_query)
                ],
            }
        
        first_message = True
        seen_ids = set()

        # Stream the workflow execution
        for _, events in self.agent.stream(initial_state, stream_mode=["updates"]):
            new_msgs = [
                msg
                for v in events.values()
                for msg in v.get("messages", [])
                if hasattr(msg, 'id') and msg.id not in seen_ids
            ]
            if first_message:
                seen_ids.update(msg.id for msg in new_msgs[: len(cc_msgs)])
                new_msgs = new_msgs[len(cc_msgs) :]
                first_message = False
            else:
                seen_ids.update(msg.id for msg in new_msgs)
                # Get node name
                if events:
                    node_name = tuple(events.keys())[0]
                    yield ResponsesAgentStreamEvent(
                        type="response.output_item.done",
                        item=self.create_text_output_item(
                            text=f"<name>{node_name}</name>", id=str(uuid4())
                        ),
                    )
            if len(new_msgs) > 0:
                yield from output_to_responses_items_stream(new_msgs)


#######################################################
# Configure the Multi-Agent System
#######################################################

# Initialize LLM
llm = ChatDatabricks(endpoint=LLM_ENDPOINT_NAME)
llm_planning = ChatDatabricks(endpoint=LLM_ENDPOINT_PLANNING)

# Create Genie agents (for genie route)
genie_agents, genie_agent_tools, genie_subagent_configs, space_summary_df = create_genie_agents(TABLE_NAME)

# Build space context for clarification and planning
space_summary_list = space_summary_df.collect()
context = {}
for row in space_summary_list:
    space_id = row["space_id"]
    context[space_id] = row["searchable_content"]

# Define UC function names
UC_FUNCTION_NAMES = [
    f"{CATALOG}.{SCHEMA}.get_space_summary",
    f"{CATALOG}.{SCHEMA}.get_table_overview",
    f"{CATALOG}.{SCHEMA}.get_column_detail",
    f"{CATALOG}.{SCHEMA}.get_space_details",
]

########################################
# SQL Execution Tool
########################################

def execute_sql_on_delta_tables(
    sql_query: str,
    max_rows: int = 100,
    return_format: str = "dict"
) -> Dict[str, Any]:
    """
    Execute SQL query on delta tables and return formatted results.
    
    Args:
        sql_query: Support two types:
            1) The result from invoke the SQL synthesis agent (dict with messages)
            2) The SQL query string (can be raw SQL or contain markdown code blocks)
        max_rows: Maximum number of rows to return (default: 100)
        return_format: Format of the result - "dict", "json", or "markdown"
    
    Returns:
        Dictionary containing:
        - success: bool - Whether execution was successful
        - sql: str - The executed SQL query
        - result: Any - Query results in requested format
        - row_count: int - Number of rows returned
        - columns: List[str] - Column names
        - error: str - Error message if failed (optional)
    """
    from pyspark.sql import SparkSession
    import pandas as pd
    
    spark = SparkSession.builder.getOrCreate()
    
    # Step 1: Extract SQL from agent result or markdown code blocks if present
    if sql_query and isinstance(sql_query, dict) and "messages" in sql_query:
        sql_query = sql_query["messages"][-1].content
    
    extracted_sql = sql_query.strip()
    
    # Try to extract SQL from markdown code blocks
    if "```sql" in extracted_sql.lower():
        sql_match = re.search(r'```sql\s*(.*?)\s*```', extracted_sql, re.IGNORECASE | re.DOTALL)
        if sql_match:
            extracted_sql = sql_match.group(1).strip()
    elif "```" in extracted_sql:
        # Extract any code block
        sql_match = re.search(r'```\s*(.*?)\s*```', extracted_sql, re.DOTALL)
        if sql_match:
            extracted_sql = sql_match.group(1).strip()
    
    # Step 2: Add LIMIT clause if not present (for safety)
    if "limit" not in extracted_sql.lower():
        extracted_sql = f"{extracted_sql.rstrip(';')} LIMIT {max_rows}"
    
    try:
        # Step 3: Execute the SQL query
        print(f"\n{'='*80}")
        print("🔍 EXECUTING SQL QUERY")
        print(f"{'='*80}")
        print(f"SQL:\n{extracted_sql}")
        print(f"{'='*80}\n")
        
        df = spark.sql(extracted_sql)
        
        # Step 4: Collect results
        results_list = df.collect()
        row_count = len(results_list)
        columns = df.columns
        
        print(f"✅ Query executed successfully!")
        print(f"📊 Rows returned: {row_count}")
        print(f"📋 Columns: {', '.join(columns)}\n")
        
        # Step 5: Format results based on return_format
        if return_format == "dataframe":
            result_data = df.toPandas()
        elif return_format == "json":
            result_data = df.toJSON().collect()
        elif return_format == "markdown":
            pandas_df = df.toPandas()
            result_data = pandas_df.to_markdown(index=False)
        else:  # dict (default)
            result_data = [row.asDict() for row in results_list]
        
        # Step 6: Display preview
        print(f"{'='*80}")
        print("📄 RESULTS PREVIEW (first 10 rows)")
        print(f"{'='*80}")
        df.show(n=min(10, row_count), truncate=False)
        print(f"{'='*80}\n")
        
        return {
            "success": True,
            "sql": extracted_sql,
            "result": result_data,
            "row_count": row_count,
            "columns": columns,
        }
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n{'='*80}")
        print("❌ SQL EXECUTION FAILED")
        print(f"{'='*80}")
        print(f"Error: {error_msg}")
        print(f"{'='*80}\n")
        
        return {
            "success": False,
            "sql": extracted_sql,
            "result": None,
            "row_count": 0,
            "columns": [],
            "error": error_msg
        }


# Create SQL execution tool
from langchain_core.tools import tool

@tool("execute_sql_tool")
def execute_sql_tool(sql_query: str, max_rows: int = 100) -> str:
    """
    Execute SQL query on delta tables and return results.
    
    Args:
        sql_query: The SQL query to execute
        max_rows: Maximum number of rows to return (default: 100)
    
    Returns:
        JSON string with execution results
    """
    result = execute_sql_on_delta_tables(sql_query, max_rows, return_format="dict")
    return json.dumps(result, indent=2, default=str)


########################################
# Create Genie Route Agent with Genie Tools
########################################

def create_genie_route_agent(llm: Runnable, genie_agent_tools: list) -> Runnable:
    """Create SQL synthesis agent for genie route using Genie agent tools."""
    
    system_prompt = """You are a SQL synthesis agent, which can take analysis plan, and route queries to the corresponding Genie Agent.
The Plan given to you is a JSON:
{
'original_query': 'The User's Question',
'vector_search_relevant_spaces_info': [{'space_id': 'space_id_1',
   'space_title': 'space_title_1'},
  {'space_id': 'space_id_2',
   'space_title': 'space_title_2'},
  {'space_id': 'space_id_3',
   'space_title': 'space_title_3'}],
"question_clear": true,
"sub_questions": ["sub-question 1", "sub-question 2", ...],
"requires_multiple_spaces": true/false,
"relevant_space_ids": ["space_id_1", "space_id_2", ...],
"requires_join": true/false,
"join_strategy": "table_route" or "genie_route" or null,
"execution_plan": "Brief description of execution plan",
"genie_route_plan": {'space_id_1':'partial_question_1', 'space_id_2':'partial_question_2', 'space_id_3':'partial_question_3', ...} or null,}

## Tool Calling Plan:
1. Under the key of 'genie_route_plan' in the JSON, extracting 'partial_question_1' and feed to the right Genie Agent tool of 'space_id_1' with the input as a string.
2. Asynchronously send all other partial_questions to the corresponding Genie Agent tools accordingly.
3. You have access to all Genie Agents as tools given to you; locate the proper Genie Agent Tool by searching the 'space_id_1' in the tool's description. After each Genie agent returns result, only extract the SQL string from the Genie tool output JSON {"thinking": thinking, "sql": sql, "answer": answer}.
4. If you find you are still missing necessary analytical components (metrics, filters, dimensions, etc.) to assemble the final SQL, which might be due to some genie agent tool may not have the necessary information being assigned, try to leverage other most likely Genie agents to find the missing pieces.

## Disaster Recovery (DR) Plan:
1. If one Genie agent tool fail to generate a SQL query, allow retry AS IS only one time;
2. If fail again, try to reframe the partial question 'partial_question_1' according to the error msg returned by the genie tool, e.g., genie tool may say "I dont have information for cost related information", you can remove those components in the 'partial_question_1' which doesn't exist in the genie tool. For example, if the genie tool "Genie_MemberBenefits" doesn't contain benefit cost related information, you can reframe the question by removing the cost-related components in the 'partial_question_1', generate 'partial_question_1_v2' and try again. Only try once;
3. If fail again, return response as is.


## Overall SQL Synthesis Plan:
Then, you can combine all the SQL pieces into a single SQL query, and return the final SQL query.
OUTPUT REQUIREMENTS:
- Generate complete, executable SQL with:
  * Proper JOINs based on execution plan strategy
  * WHERE clauses for filtering
  * Appropriate aggregations
  * Clear column aliases
  * Always use real column name existed in the data, never make up one
- Return your response with:
1. Your explanation combining both the individual Genie thinking and your own reasoning
2. The final SQL query in a ```sql code block
    """
    
    return create_agent(
        model=llm,
        tools=genie_agent_tools,
        name="sql_synthesis_genie_route",
        system_prompt=system_prompt
    )


########################################
# Create All Sub-Agents with Individual LLMs
########################################

# Keep IN_CODE_AGENTS empty - all agents now created individually with their own LLMs
IN_CODE_AGENTS = []

# Create LLMs for different agents (can be customized per agent)
llm_clarification = ChatDatabricks(endpoint=LLM_ENDPOINT_PLANNING, temperature=0.1)  # Fast model for simple task
llm_planning = ChatDatabricks(endpoint=LLM_ENDPOINT_PLANNING, temperature=0.1)
llm_table_route = ChatDatabricks(endpoint=LLM_ENDPOINT_NAME, temperature=0.1)  # Powerful model for SQL synthesis
llm_genie_route = ChatDatabricks(endpoint=LLM_ENDPOINT_PLANNING, temperature=0.1)
llm_execution = ChatDatabricks(endpoint=LLM_ENDPOINT_PLANNING, temperature=0.1)

# 1. Clarification Agent
def create_clarification_agent_with_context(llm: Runnable, table_name: str) -> Runnable:
    """
    Create clarification agent with dynamically loaded context.
    Loads fresh context from table on each call.
    """
    context = load_space_context(table_name)
    
    return create_agent(
        model=llm,
        tools=[],
        name="clarification_agent",
        system_prompt=f"""
You are a clarification agent. Your job is to analyze user queries and determine if they are clear enough to execute.

IMPORTANT: Only mark as unclear if the question is TRULY VAGUE or IMPOSSIBLE to answer.
Be lenient - if the question can reasonably be answered with the available data, mark it as clear.

Available Genie Spaces:
{json.dumps(context, indent=2)}

Determine if:
1. The question is clear and answerable as-is (BE LENIENT - default to TRUE)
2. The question is TRULY VAGUE and needs critical clarification (ONLY if essential information is missing)
3. If the question mentions any metrics/dimensions/filters that can be mapped to available data with certain confidence, mark it as CLEAR; otherwise, mark it as UNCLEAR and ask for clarification.

If clarification is truly needed, provide:
- A brief explanation of what's critically unclear
- 2-3 specific clarification options the user can choose from

Return your analysis as JSON:
{{
    "question_clear": true/false,
    "clarification_needed": "explanation if unclear (null if clear)",
    "clarification_options": ["option 1", "option 2", "option 3"] or null
}}

Only return valid JSON, no explanations.
        """
    )

clarification_agent = create_clarification_agent_with_context(llm_clarification, TABLE_NAME)
clarification_agent.name = "clarification_agent"
clarification_agent.description = "Validates query clarity and requests clarification if the user query is ambiguous or missing information."

# 2. Planning Agent
planning_agent = create_agent(
    model=llm_planning,
    tools=[],
    name="planning_agent",
    system_prompt="""
You are a query planning expert. Analyze the following question and create an execution plan.

You will receive:
1. The user's query (or combined query context with clarification)
2. Potentially relevant Genie spaces from vector search

Break down the question and determine:
1. What are the sub-questions or analytical components?
2. How many Genie spaces are needed to answer completely? (List their space_ids)
3. If multiple spaces are needed, do we need to JOIN data across them? Reasoning whether the sub-questions are totally independent without joining need.
    - JOIN needed: E.g., "How many active plan members over 50 are on Lexapro?" requires joining member data with pharmacy claims.
    - No need for JOIN: E.g., "How many active plan members over 50? How much total cost for all Lexapro claims?" - Two independent questions.
4. If JOIN is needed, what's the best strategy:
    - "table_route": Directly synthesize SQL across multiple tables
    - "genie_route": Query each Genie Space Agent separately, then combine SQL queries
    - If user explicitly asks for "genie_route", use it; otherwise, use "table_route"
    - always populate the join_strategy field in the JSON output.
5. Execution plan: A brief description of how to execute the plan.
    - For genie_route: Return "genie_route_plan": {'space_id_1':'partial_question_1', 'space_id_2':'partial_question_2'}
    - For table_route: Return "genie_route_plan": null
    - Each partial_question should be similar to original but scoped to that space
    - Add "Please limit to top 10 rows" to each partial question

Return your analysis as JSON:
{
    "original_query": "user query",
    "vector_search_relevant_spaces_info": [{"space_id": "space_id_1", "space_title": "title_1"}, ...],
    "question_clear": true,
    "sub_questions": ["sub-question 1", "sub-question 2", ...],
    "requires_multiple_spaces": true/false,
    "relevant_space_ids": ["space_id_1", "space_id_2", ...],
    "requires_join": true/false,
    "join_strategy": "table_route" or "genie_route",
    "execution_plan": "Brief description of execution plan",
    "genie_route_plan": {'space_id_1':'partial_question_1', 'space_id_2':'partial_question_2'} or null
}

Only return valid JSON, no explanations.
    """
)
planning_agent.name = "planning_agent"
planning_agent.description = "Analyzes queries, searches for relevant Genie spaces, identifies join requirements, and creates execution plans (table_route or genie_route)."

# 3. SQL Synthesis Table Route Agent
uc_toolkit_table_route = UCFunctionToolkit(function_names=UC_FUNCTION_NAMES)
TOOLS.extend(uc_toolkit_table_route.tools)

sql_synthesis_table_route = create_agent(
    model=llm_table_route,
    tools=uc_toolkit_table_route.tools,
    name="sql_synthesis_table_route",
    system_prompt="""
You are a specialized SQL synthesis agent in a multi-agent system.

ROLE: You receive execution plans from the planning agent and generate SQL queries.

## WORKFLOW:
1. Review the execution plan and provided metadata
2. If metadata is sufficient → Generate SQL immediately
3. If insufficient, call UC function tools in this order:
   a) get_space_summary for space information
   b) get_table_overview for table schemas
   c) get_column_detail for specific columns
   d) get_space_details ONLY as last resort (token intensive)
4. At last, if you still cannot find enough metadata in relevant spaces provided, dont stuck there. Expand the searching scope to all spaces mentioned in the execution plan's 'vector_search_relevant_spaces_info' field. Extract the space_id from 'vector_search_relevant_spaces_info'.
5. Generate complete, executable SQL

## UC FUNCTION USAGE:
- Pass arguments as JSON array strings: '["space_id_1", "space_id_2"]' or 'null'
- Only query spaces from execution plan's relevant_space_ids
- Use minimal sufficiency: only query what you need

## OUTPUT REQUIREMENTS:
- Generate complete, executable SQL with:
  * Proper JOINs based on execution plan
  * WHERE clauses for filtering
  * Appropriate aggregations
  * Clear column aliases
  * Always use real column names, never make up ones
- Return your response with:
1. Your explanations; If SQL cannot be generated, explain what metadata is missing
2. The final SQL query in a ```sql code block
    """
)
sql_synthesis_table_route.name = "sql_synthesis_table_route"
sql_synthesis_table_route.description = "Generates SQL queries using UC metadata functions (table route). Best for queries requiring joins across multiple tables."

# 4. SQL Synthesis Genie Route Agent (with Genie tools)
genie_route_agent = create_genie_route_agent(llm_genie_route, genie_agent_tools)
genie_route_agent.name = "sql_synthesis_genie_route"
genie_route_agent.description = "Generates SQL by routing queries to individual Genie agents and combining their SQL outputs. Use when join_strategy is 'genie_route'."

# 5. SQL Execution Agent
TOOLS.append(execute_sql_tool)
sql_execution_agent = create_agent(
    model=llm_execution,
    tools=[execute_sql_tool],
    name="sql_execution_agent",
    system_prompt="""
    You are a SQL execution agent. Your job is to:
    1. Take SQL queries from the SQL synthesis agents
    2. Execute them on delta tables using the execute_sql_tool
    3. Return formatted results with execution status
    
    IMPORTANT: Always use the execute_sql_tool to run SQL queries.
    
    When you receive a SQL query:
    - Extract the SQL if it's in markdown formatting or JSON
    - Call execute_sql_tool with the SQL query
    - Parse and present the results clearly
    
    The tool returns a JSON with:
      * success: boolean indicating if execution succeeded
      * sql: the executed query
      * result: query results (list of dictionaries)
      * row_count: number of rows returned
      * columns: list of column names
      * error: error message if failed
    
    Present the results in a user-friendly format including:
    - Success status
    - SQL that was executed
    - Results summary (row count, columns)
    - Sample of the data (if successful)
    - Error details (if failed)
    """
)
sql_execution_agent.name = "sql_execution_agent"
sql_execution_agent.description = "Executes SQL queries on delta tables and returns structured results with success status, data, and metadata."

# 6. Result Summarize Agent
llm_summarize = ChatDatabricks(endpoint=LLM_ENDPOINT_SUMMARIZE, temperature=0.1, max_tokens=2000)
result_summarize_agent = create_agent(
    model=llm_summarize,
    tools=[],
    name="result_summarize_agent",
    system_prompt="""
You are a result summarization agent. Generate a concise, natural language summary of what this multi-agent workflow accomplished.

You will receive workflow execution details including:
- Original user query
- Clarification status and details
- Execution plan and strategy
- SQL generation details and explanation
- Execution results or errors

Your task is to generate a detailed summary in natural language that:
1. Describes what the user asked for
2. Explains what the system did (planning, SQL generation, execution)
3. States the outcome (success with X rows, error, needs clarification, etc.)
4. Print out SQL synthesis explanation if any SQL was generated
5. Print out SQL if any SQL was generated; make it a code block
6. Print out the result itself (like a table)

Keep it concise and user-friendly.

Return your summary in this format:

**Summary**: [Brief overview of what happened]

**Original Query**: [User's original question]

**Planning**: [What the planning agent determined]
**Strategy**: [table_route or genie_route]

**SQL Generation**: [Success or failure, with explanation]
**SQL Query**: 
```sql
[The SQL query if generated]
```

**Execution**: [Success or failure]
**Rows**: [Number of rows]
**Columns**: [Column names]

**Result**: [Query results formatted as table or error message]
    """
)
result_summarize_agent.name = "result_summarize_agent"
result_summarize_agent.description = "Generates comprehensive natural language summary of the entire workflow execution including plans, SQL, results, and any errors."

# Collect all agents for supervisor
ALL_AGENTS = [
    clarification_agent,
    planning_agent,
    sql_synthesis_table_route,
    genie_route_agent,
    sql_execution_agent,
    result_summarize_agent
]

#################################################
# Create supervisor and set up MLflow for tracing
#################################################

# Create supervisor with all agents
supervisor = create_langgraph_supervisor(
    llm, 
    IN_CODE_AGENTS,  # Empty list now
    additional_agents=ALL_AGENTS  # All agents with their own LLMs
)

mlflow.langchain.autolog()
AGENT = LangGraphResponsesAgent(supervisor)
mlflow.models.set_model(AGENT)

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Integrated Multi-Agent System
# MAGIC 
# MAGIC The complete multi-agent system is now fully integrated with all agents working together:
# MAGIC 
# MAGIC ### Integrated Agents (ALL_AGENTS):
# MAGIC 
# MAGIC **All agents now have their own dedicated LLMs** for maximum flexibility and performance optimization.
# MAGIC 
# MAGIC 1. **Clarification Agent** (ALL_AGENTS[0])
# MAGIC    - LLM: `llm_clarification` (Haiku - fast for simple tasks)
# MAGIC    - Validates query clarity with lenient approach
# MAGIC    - Requests clarification only when truly needed (max 1 time)
# MAGIC    - Dynamically loads space context from Delta table
# MAGIC 
# MAGIC 2. **Planning Agent** (ALL_AGENTS[1])
# MAGIC    - LLM: `llm_planning` (Haiku - efficient for planning)
# MAGIC    - Analyzes queries and searches vector index
# MAGIC    - Creates detailed execution plans with genie_route_plan
# MAGIC    - Determines table_route or genie_route strategy
# MAGIC    - Identifies relevant spaces and join requirements
# MAGIC 
# MAGIC 3. **SQL Synthesis Table Route** (ALL_AGENTS[2])
# MAGIC    - LLM: `llm_table_route` (Sonnet - powerful for SQL generation)
# MAGIC    - Uses UC metadata functions intelligently
# MAGIC    - Best for complex joins across tables
# MAGIC    - Provides SQL with explanation
# MAGIC 
# MAGIC 4. **SQL Synthesis Genie Route** (ALL_AGENTS[3])
# MAGIC    - LLM: `llm_genie_route` (Sonnet - coordinates Genie agents)
# MAGIC    - Routes to individual Genie agents dynamically
# MAGIC    - Only creates Genie agents for relevant spaces (optimized)
# MAGIC    - Combines SQL from multiple sources with retry logic
# MAGIC    - Used when join_strategy is "genie_route"
# MAGIC 
# MAGIC 5. **SQL Execution Agent** (ALL_AGENTS[4])
# MAGIC    - LLM: `llm_execution` (Haiku - executes with tool)
# MAGIC    - Executes generated SQL queries on delta tables
# MAGIC    - Returns structured results with success status
# MAGIC    - Includes data, row counts, and comprehensive error handling
# MAGIC 
# MAGIC 6. **Result Summarize Agent** (ALL_AGENTS[5]) - NEW!
# MAGIC    - LLM: `llm_summarize` (Haiku - fast summarization)
# MAGIC    - Generates comprehensive natural language summary
# MAGIC    - Includes all workflow details: plan, SQL, results, errors
# MAGIC    - Formats results in user-friendly way
# MAGIC    - MANDATORY final step for all workflows
# MAGIC
# MAGIC ### LLM Configuration Benefits:
# MAGIC - **Cost Optimization**: Use cheaper models (Haiku) for simpler tasks
# MAGIC - **Performance**: Use powerful models (Sonnet) where needed
# MAGIC - **Flexibility**: Easy to adjust per agent based on requirements
# MAGIC - **Scalability**: Each agent can scale independently
# MAGIC 
# MAGIC ### Complete Workflow:
# MAGIC ```
# MAGIC User Query → Clarification → Planning → SQL Synthesis (Table/Genie Route) → 
# MAGIC SQL Execution → Result Summarize → Comprehensive Response
# MAGIC ```
# MAGIC 
# MAGIC ### Enhanced Features:
# MAGIC - **Dynamic Context Loading**: Clarification agent loads fresh space context from Delta table
# MAGIC - **Clarification Flow**: Preserves original query and combines with clarification response
# MAGIC - **Optimized Genie Route**: Only creates Genie agents for relevant spaces (not all spaces)
# MAGIC - **Comprehensive State**: Full observability with AgentState TypedDict
# MAGIC - **Result Summarization**: Every workflow ends with user-friendly summary
# MAGIC - **Error Handling**: Graceful handling with explanations at every step
# MAGIC 
# MAGIC ### Final Output Format:
# MAGIC The supervisor returns comprehensive results including:
# MAGIC - **Summary**: Natural language overview of entire workflow
# MAGIC - **Original Query**: User's question (preserved through clarifications)
# MAGIC - **Execution Plan**: Strategy and approach from planning agent
# MAGIC - **SQL Query**: Generated SQL with explanation
# MAGIC - **Results**: Query execution results formatted as table
# MAGIC - **Errors**: Clear error messages if any step fails

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test the Agent

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

from agent import AGENT

# Test with a sample query
input_example = {
    "input": [
        {"role": "user", "content": "What is the average cost of medical claims in 2024?"}
    ]
}

response = AGENT.predict(input_example)
print(response)

# COMMAND ----------

# Test streaming
for event in AGENT.predict_stream(input_example):
    print(event.model_dump(exclude_none=True))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Log the Agent as an MLflow Model

# COMMAND ----------

import mlflow
from agent import LLM_ENDPOINT_NAME, CATALOG, SCHEMA, UC_FUNCTION_NAMES, VECTOR_SEARCH_INDEX, TABLE_NAME
from mlflow.models.resources import (
    DatabricksFunction,
    DatabricksServingEndpoint,
    DatabricksSQLWarehouse,
    DatabricksTable,
    DatabricksVectorSearchIndex,
)
from pkg_resources import get_distribution

# Determine Databricks resources for automatic auth passthrough
resources = [DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT_NAME)]

# Add UC Functions
for func_name in UC_FUNCTION_NAMES:
    resources.append(DatabricksFunction(function_name=func_name))

# Add Vector Search Index
resources.append(DatabricksVectorSearchIndex(index_name=VECTOR_SEARCH_INDEX))

# Add Delta Table
resources.append(DatabricksTable(table_name=TABLE_NAME))

# TODO: Add SQL Warehouse ID
# resources.append(DatabricksSQLWarehouse(warehouse_id="<your_warehouse_id>"))

with mlflow.start_run():
    logged_agent_info = mlflow.pyfunc.log_model(
        name="agent",
        python_model="agent.py",
        resources=resources,
        pip_requirements=[
            f"databricks-connect=={get_distribution('databricks-connect').version}",
            f"mlflow=={get_distribution('mlflow').version}",
            f"databricks-langchain=={get_distribution('databricks-langchain').version}",
            f"langgraph=={get_distribution('langgraph').version}",
            f"langgraph-supervisor=={get_distribution('langgraph-supervisor').version}",
            f"databricks-vectorsearch=={get_distribution('databricks-vectorsearch').version}",
        ],
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Pre-deployment Validation

# COMMAND ----------

import mlflow
mlflow.models.predict(
    model_uri=f"runs:/{logged_agent_info.run_id}/agent",
    input_data=input_example,
    env_manager="uv",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Register to Unity Catalog

# COMMAND ----------

mlflow.set_registry_uri("databricks-uc")

# TODO: define the catalog, schema, and model name for your UC model
catalog = "yyang"
schema = "multi_agent_genie"
model_name = "super_agent_langgraph"
UC_MODEL_NAME = f"{catalog}.{schema}.{model_name}"

# register the model to UC
uc_registered_model_info = mlflow.register_model(
    model_uri=logged_agent_info.model_uri, name=UC_MODEL_NAME
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Deploy the Agent

# COMMAND ----------

from databricks import agents

agents.deploy(
    UC_MODEL_NAME, 
    uc_registered_model_info.version, 
    tags={"endpointSource": "multi_agent_genie", "version": "v1"}, 
    deploy_feedback_model=False
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Additional Testing Examples

# COMMAND ----------

# Test clarification flow
test_queries = [
    {
        "query": "How many patients are?",
        "description": "Vague query - should trigger clarification"
    },
    {
        "query": "What is the average cost of medical claims in 2024?",
        "description": "Clear query - should proceed directly"
    },
    {
        "query": "What is the average cost of medical claims for patients diagnosed with diabetes, broken down by insurance payer type and patient age group?",
        "description": "Complex multi-space query requiring join"
    },
    {
        "query": "Show me the top 10 most expensive medications and patient counts by age group",
        "description": "Multi-space query - tests genie_route or table_route decision"
    }
]

for test_case in test_queries:
    query = test_case["query"]
    description = test_case["description"]
    
    print(f"\n{'='*80}")
    print(f"Test Case: {description}")
    print(f"Query: {query}")
    print(f"{'='*80}\n")
    
    input_data = {"input": [{"role": "user", "content": query}]}
    
    try:
        response = AGENT.predict(input_data)
        print("\n📊 AGENT RESPONSE:")
        print(response)
        
        # Check if clarification was requested
        # (This would be in the response output)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    print(f"\n{'='*80}")
    print("Test case complete")
    print(f"{'='*80}\n")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test Clarification Response Flow
# MAGIC 
# MAGIC This test demonstrates how to handle clarification requests and responses

# COMMAND ----------

# Test clarification response workflow
print("="*80)
print("TESTING CLARIFICATION RESPONSE FLOW")
print("="*80)

# Step 1: Send a vague query that should trigger clarification
vague_query = "Show me the data"

print(f"\n📤 Sending vague query: {vague_query}")
input_data_1 = {"input": [{"role": "user", "content": vague_query}]}

response_1 = AGENT.predict(input_data_1)
print("\n📥 Response 1 (should contain clarification request):")
print(response_1)

# In a real scenario, you would:
# 1. Parse the response to check if clarification was requested
# 2. Extract clarification_message, original_query, clarification_count from state
# 3. Get user's clarification response
# 4. Send follow-up request with is_clarification_response=True

# Example of how to send clarification response:
# (This is pseudocode - actual implementation depends on how you access state)
"""
# Step 2: User provides clarification
user_clarification = "Show me patient count by age group from the enrollment data"

print(f"\n📤 User provides clarification: {user_clarification}")

# Send clarification response with preserved state
input_data_2 = {
    "input": [{"role": "user", "content": user_clarification}],
    "custom_inputs": {
        "is_clarification_response": True,
        "original_query": vague_query,  # Preserved from step 1
        "clarification_message": "...",  # Extracted from response_1
        "clarification_count": 1  # Preserved from step 1
    }
}

response_2 = AGENT.predict(input_data_2)
print("\n📥 Response 2 (should contain query results):")
print(response_2)
"""

print("\n" + "="*80)
print("Note: Clarification response handling requires access to previous state")
print("See ResponsesAgent.predict_stream() for full implementation details")
print("="*80)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test Genie Route Agent

# COMMAND ----------

from agent import genie_route_agent, execute_sql_on_delta_tables

# Example plan result (typically comes from planning agent)
example_plan = {
    "original_query": "What is the average cost of medical claims for patients diagnosed with diabetes?",
    "question_clear": True,
    "requires_multiple_spaces": True,
    "relevant_space_ids": ["space_id_1", "space_id_2"],
    "requires_join": True,
    "join_strategy": "genie_route",
    "genie_route_plan": {
        "space_id_1": "What are the medical claims for patients?",
        "space_id_2": "What are the diagnosis codes for diabetes?"
    }
}

# Test genie route agent with plan
agent_message = {
    "messages": [
        {
            "role": "user",
            "content": f"""
Generate a SQL query according to the following Query Plan:
{json.dumps(example_plan, indent=2)}
"""
        }
    ]
}

# Invoke genie route agent
genie_route_result = genie_route_agent.invoke(agent_message)
print("Genie Route Agent Result:")
print(genie_route_result)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test SQL Execution Tool

# COMMAND ----------

# Example SQL query to execute
test_sql = """
SELECT 
    COUNT(*) as total_count,
    AVG(allowed_amount) as avg_amount
FROM yyang.multi_agent_genie.medical_claim
LIMIT 100
"""

# Execute SQL
execution_result = execute_sql_on_delta_tables(test_sql, max_rows=100, return_format="dict")
print("\nExecution Result:")
print(json.dumps(execution_result, indent=2, default=str))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test End-to-End Workflow with SQL Execution

# COMMAND ----------

# Example: Get SQL from table route agent, then execute it
query = "How many patients are in the dataset?"

# Step 1: Create input for the agent
input_data = {"input": [{"role": "user", "content": query}]}

# Step 2: Get response from supervisor (which routes to appropriate agent)
response = AGENT.predict(input_data)

# Step 3: Extract SQL from response (if any)
# Note: You would parse the response to extract the SQL query
# For demonstration, using a sample SQL
sample_sql = """
SELECT COUNT(DISTINCT patient_id) as total_patients
FROM yyang.multi_agent_genie.enrollment
"""

# Step 4: Execute the SQL
execution_result = execute_sql_on_delta_tables(sample_sql, max_rows=10, return_format="dict")

print("Query:", query)
print("\nSQL Generated:", sample_sql)
print("\nExecution Result:")
print(json.dumps(execution_result, indent=2, default=str))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test Result Summarization
# MAGIC 
# MAGIC The Result Summarize Agent provides comprehensive summaries of workflow execution

# COMMAND ----------

# Test result summarization with a clear query
test_query_for_summary = "What is the total count of medical claims in 2024?"

print("="*80)
print("TESTING RESULT SUMMARIZATION")
print("="*80)
print(f"\nQuery: {test_query_for_summary}\n")

input_data = {"input": [{"role": "user", "content": test_query_for_summary}]}

# The response should include:
# 1. Summary of what happened
# 2. Original query
# 3. Execution plan
# 4. SQL query (if generated)
# 5. Execution results (if successful)
# 6. Any errors encountered
response = AGENT.predict(input_data)

print("\n📊 COMPREHENSIVE RESPONSE WITH SUMMARY:")
print("="*80)
print(response)
print("="*80)

print("\n✅ The response includes:")
print("  - Natural language summary of the workflow")
print("  - Complete execution plan from planning agent")
print("  - Generated SQL query with explanation")
print("  - Query execution results formatted as table")
print("  - Error details if any step failed")
print("\nThis comprehensive output is generated by the Result Summarize Agent (ALL_AGENTS[5])")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Inspect State After Execution
# MAGIC 
# MAGIC You can also directly invoke the supervisor to get full state

# COMMAND ----------

# Direct invocation gives access to full state
from agent import supervisor

test_query = "What is the average cost per claim?"
initial_state = {
    "original_query": test_query,
    "question_clear": False,
    "messages": [
        {"role": "system", "content": "Multi-agent Q&A system"},
        {"role": "user", "content": test_query}
    ]
}

print("="*80)
print("DIRECT SUPERVISOR INVOCATION FOR STATE INSPECTION")
print("="*80)

# Invoke supervisor directly
final_state = supervisor.invoke(initial_state)

print("\n📊 FINAL STATE KEYS:")
print(list(final_state.keys()))

print("\n🔍 KEY STATE FIELDS:")
print(f"  - original_query: {final_state.get('original_query', 'N/A')}")
print(f"  - question_clear: {final_state.get('question_clear', 'N/A')}")
print(f"  - execution_plan: {final_state.get('execution_plan', 'N/A')[:100]}...")
print(f"  - join_strategy: {final_state.get('join_strategy', 'N/A')}")
print(f"  - has_sql: {final_state.get('has_sql', 'N/A')}")

if final_state.get('sql_query'):
    print(f"\n💻 SQL QUERY:")
    print(final_state['sql_query'])

if final_state.get('execution_result'):
    exec_result = final_state['execution_result']
    print(f"\n📊 EXECUTION RESULT:")
    print(f"  - Success: {exec_result.get('success', False)}")
    print(f"  - Row count: {exec_result.get('row_count', 0)}")
    print(f"  - Columns: {exec_result.get('columns', [])}")

if final_state.get('final_summary'):
    print(f"\n📝 FINAL SUMMARY:")
    print(final_state['final_summary'])

print("\n" + "="*80)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Compare Table Route vs Genie Route

# COMMAND ----------

# Test both routes with the same query
test_query = "What is the average cost of medical claims in 2024?"

print("="*80)
print("COMPARING TABLE ROUTE VS GENIE ROUTE")
print("="*80)
print(f"\nQuery: {test_query}\n")

print("📝 ROUTE COMPARISON NOTES:")
print("-"*80)
print("1. **Table Route** (SQL Synthesis Table Route Agent):")
print("   - Uses UC metadata functions (get_space_summary, get_table_overview, etc.)")
print("   - Queries metadata on-demand with intelligent progression")
print("   - Best for complex joins across multiple tables")
print("   - Faster for queries requiring detailed schema information")
print("")
print("2. **Genie Route** (SQL Synthesis Genie Route Agent):")
print("   - Routes queries to individual Genie Space Agents")
print("   - Each Genie agent generates SQL for its space")
print("   - Combines SQL fragments into final query")
print("   - OPTIMIZED: Only creates Genie agents for relevant spaces (not all spaces)")
print("   - Best for queries that can be decomposed into independent sub-queries")
print("")
print("The Planning Agent automatically determines the best strategy based on:")
print("  - Query complexity")
print("  - Number of spaces needed")
print("  - Join requirements")
print("  - User preference (if explicitly requested)")
print("-"*80)

# Table Route Test
print("\n🚀 TABLE ROUTE TEST:")
print("-"*80)
table_route_input = {
    "input": [
        {"role": "user", "content": f"{test_query}\nPlease use table_route for SQL synthesis."}
    ]
}

print("Sending request with table_route preference...")
try:
    table_route_response = AGENT.predict(table_route_input)
    print("\n✅ Table Route Response:")
    print(table_route_response)
except Exception as e:
    print(f"\n❌ Table Route Error: {e}")

print("\n" + "="*80 + "\n")

# Genie Route Test
print("🚀 GENIE ROUTE TEST:")
print("-"*80)
genie_route_input = {
    "input": [
        {"role": "user", "content": f"{test_query}\nPlease use genie_route for SQL synthesis."}
    ]
}

print("Sending request with genie_route preference...")
print("Note: The Genie Route agent will:")
print("  1. Receive genie_route_plan from Planning Agent")
print("  2. Create Genie agents ONLY for relevant spaces")
print("  3. Route partial queries to each Genie agent")
print("  4. Extract SQL from each Genie agent response")
print("  5. Combine SQL fragments into final query")
print("")

try:
    genie_route_response = AGENT.predict(genie_route_input)
    print("\n✅ Genie Route Response:")
    print(genie_route_response)
except Exception as e:
    print(f"\n❌ Genie Route Error: {e}")

print("\n" + "="*80)
print("COMPARISON COMPLETE")
print("="*80)
print("\n💡 TIP: Review MLflow traces to see:")
print("  - Token usage differences")
print("  - Latency differences")
print("  - SQL quality differences")
print("  - Agent routing decisions")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next Steps
# MAGIC 
# MAGIC 1. **Test the multi-agent system** with various queries
# MAGIC    - Test clarification flow with ambiguous queries
# MAGIC    - Test both table_route and genie_route strategies
# MAGIC    - Test error handling and recovery
# MAGIC 2. **Monitor MLflow traces** to understand agent routing and execution
# MAGIC    - View supervisor routing decisions
# MAGIC    - Track agent performance and token usage
# MAGIC 3. **Fine-tune agent prompts** based on test results
# MAGIC    - Adjust clarification thresholds
# MAGIC    - Refine SQL synthesis instructions
# MAGIC 4. **Compare Table Route vs Genie Route** performance and accuracy
# MAGIC    - Measure latency differences
# MAGIC    - Compare SQL quality and accuracy
# MAGIC 5. **Review summarization quality**
# MAGIC    - Ensure summaries are comprehensive and user-friendly
# MAGIC    - Validate result formatting
# MAGIC 6. **Deploy to production** after validation
# MAGIC    - Register model to Unity Catalog
# MAGIC    - Deploy to Model Serving endpoint
# MAGIC    - Set up monitoring and alerts
# MAGIC 
# MAGIC ## Key Components Now Available
# MAGIC 
# MAGIC - ✅ **Clarification Agent**: Validates query clarity with dynamic context loading
# MAGIC - ✅ **Planning Agent**: Creates execution plans with vector search
# MAGIC - ✅ **SQL Synthesis Table Route**: Uses UC metadata functions intelligently
# MAGIC - ✅ **SQL Synthesis Genie Route**: Uses Genie agent tools (optimized for relevant spaces)
# MAGIC - ✅ **SQL Execution Agent**: Executes SQL on delta tables with comprehensive error handling
# MAGIC - ✅ **Result Summarize Agent**: Generates comprehensive natural language summaries (NEW!)
# MAGIC - ✅ **Genie Agent Tools**: Individual Genie space agents created on-demand
# MAGIC - ✅ **Enhanced State Management**: Full observability with AgentState
# MAGIC - ✅ **Clarification Flow**: Preserves context through clarification requests
# MAGIC - ✅ **Streaming Support**: Full streaming with ResponsesAgent wrapper
