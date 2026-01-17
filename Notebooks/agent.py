"""
Multi-Agent System for Cross-Domain Genie Space Queries

This module implements a sophisticated multi-agent system using LangGraph and 
Databricks ResponseAgent integration for answering questions across multiple 
Genie spaces.

Architecture:
- SupervisorAgent: Routes queries to appropriate sub-agents
- ThinkingPlanningAgent: Analyzes queries and plans execution strategy
- GenieAgents: Query individual Genie spaces
- SQLSynthesisAgent: Combines SQL queries from multiple Genie agents
- SQLExecutionAgent: Executes synthesized SQL queries
"""

import json
import os
from typing import Generator, Literal, List, Dict, Any, Optional
from uuid import uuid4
import asyncio

import mlflow
from databricks_langchain import (
    ChatDatabricks,
    DatabricksFunctionClient,
    UCFunctionToolkit,
    set_uc_function_client,
)
from databricks_langchain.genie import GenieAgent
from langchain_core.runnables import Runnable
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain.agents import create_tool_calling_agent
from langgraph.graph import StateGraph, MessagesState
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
    output_to_responses_items_stream,
    to_chat_completions_input,
)
from pydantic import BaseModel

# Initialize UC Function Client
client = DatabricksFunctionClient()
set_uc_function_client(client)

########################################
# Configuration Models
########################################

GENIE = "genie"
THINKING_PLANNING = "thinking_planning"
SQL_SYNTHESIS = "sql_synthesis"
SQL_EXECUTION = "sql_execution"


class Genie(BaseModel):
    """Configuration for a Genie Space agent."""
    space_id: str
    name: str
    task: str = GENIE
    description: str


class ServedSubAgent(BaseModel):
    """Configuration for an externally served agent."""
    endpoint_name: str
    name: str
    task: Literal["agent/v1/responses", "agent/v1/chat", "agent/v2/chat"]
    description: str


class InCodeSubAgent(BaseModel):
    """Configuration for an in-code tool-calling agent."""
    tools: list[str]
    name: str
    description: str


class QueryPlan(BaseModel):
    """Structured output for query planning."""
    question_clear: bool
    clarification_needed: Optional[str] = None
    clarification_options: Optional[List[str]] = None
    sub_questions: Optional[List[str]] = None
    requires_multiple_spaces: bool = False
    relevant_space_ids: Optional[List[str]] = None
    requires_join: bool = False
    join_strategy: Optional[str] = None  # "table_route" or "genie_route"
    execution_plan: Optional[str] = None


########################################
# Thinking and Planning Agent
########################################

class ThinkingPlanningAgent:
    """
    Agent responsible for analyzing queries, breaking them down into sub-tasks,
    and determining the best execution strategy.
    """
    
    def __init__(self, llm: Runnable, vector_search_function_name: str):
        self.llm = llm
        self.vector_search_function = vector_search_function_name
        self.name = "ThinkingPlanning"
    
    def _search_relevant_spaces(self, query: str, num_results: int = 5) -> List[Dict]:
        """Search for relevant Genie spaces using vector search Python SDK."""
        from databricks.vector_search.client import VectorSearchClient
        from pyspark.sql import SparkSession
        
        # Initialize Vector Search client
        client = VectorSearchClient()
        
        # Extract index name from function name (format: catalog.schema.function_name)
        # The index name is typically: catalog.schema.enriched_genie_docs_chunks_vs_index
        parts = self.vector_search_function.split('.')
        catalog = parts[0]
        schema = parts[1]
        index_name = f"{catalog}.{schema}.enriched_genie_docs_chunks_vs_index"
        
        # Get the index
        vs_index = client.get_index(index_name=index_name)
        
        # Search with filters for space_summary chunks (dict syntax for standard endpoints)
        results = vs_index.similarity_search(
            query_text=query,
            columns=["space_id", "space_title", "score"],
            filters={"chunk_type": "space_summary"},
            num_results=num_results
        )
        
        # Extract result data
        result_data = results.get('result', {})
        manifest = result_data.get('manifest', {})
        data_array = result_data.get('data_array', [])
        
        # Get column names from manifest
        column_names = [col.get('name') if isinstance(col, dict) else str(col) 
                       for col in manifest.get('columns', [])]
        
        # Convert to list of dictionaries
        if len(data_array) > 0 and len(column_names) > 0:
            return [dict(zip(column_names, row)) for row in data_array]
        else:
            return []
    
    def analyze_query(self, query: str) -> QueryPlan:
        """
        Analyze a user query and create an execution plan.
        
        Returns:
            QueryPlan with analysis results and execution strategy
        """
        # First, check if question is clear
        clarity_prompt = f"""
        Analyze the following question for clarity and specificity:
        
        Question: {query}
        
        Determine if:
        1. The question is clear and answerable as-is
        2. The question needs clarification
        
        If clarification is needed, provide:
        - A brief explanation of what's unclear
        - 2-3 specific clarification options the user can choose from
        
        Return your analysis as JSON:
        {{
            "question_clear": true/false,
            "clarification_needed": "explanation if unclear",
            "clarification_options": ["option 1", "option 2", "option 3"]
        }}
        
        Only return valid JSON, no explanations.
        """
        
        clarity_response = self.llm.invoke(clarity_prompt)
        clarity_result = json.loads(clarity_response.content)
        
        if not clarity_result.get("question_clear", False):
            return QueryPlan(
                question_clear=False,
                clarification_needed=clarity_result.get("clarification_needed"),
                clarification_options=clarity_result.get("clarification_options", [])
            )
        
        # Question is clear, proceed with planning
        # Search for relevant Genie spaces
        relevant_spaces = self._search_relevant_spaces(query, num_results=5)
        
        # Analyze query structure and requirements
        planning_prompt = f"""
        You are a query planning expert. Analyze the following question and create an execution plan.
        
        Question: {query}
        
        Potentially relevant Genie spaces:
        {json.dumps(relevant_spaces, indent=2)}
        
        Break down the question and determine:
        1. What are the sub-questions or analytical components?
        2. How many Genie spaces are needed to answer completely? (List their space_ids)
        3. If multiple spaces are needed, do we need to JOIN data across them?
        4. If JOIN is needed, what's the best strategy:
           - "table_route": Directly synthesize SQL across multiple tables
           - "genie_route": Query each space separately, then combine results
        5. If no JOIN needed, can answers be verbally merged?
        
        Return your analysis as JSON:
        {{
            "question_clear": true,
            "sub_questions": ["sub-question 1", "sub-question 2", ...],
            "requires_multiple_spaces": true/false,
            "relevant_space_ids": ["space_id_1", "space_id_2", ...],
            "requires_join": true/false,
            "join_strategy": "table_route" or "genie_route" or null,
            "execution_plan": "Brief description of execution plan"
        }}
        
        Only return valid JSON, no explanations.
        """
        
        planning_response = self.llm.invoke(planning_prompt)
        plan_result = json.loads(planning_response.content)
        
        return QueryPlan(**plan_result)
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Process messages and return query plan."""
        messages = state.get("messages", [])
        last_message = messages[-1].content if messages else ""
        
        plan = self.analyze_query(last_message)
        
        # Add plan to state
        response_msg = AIMessage(
            content=json.dumps(plan.model_dump(), indent=2),
            name=self.name
        )
        
        return {"messages": [response_msg], "query_plan": plan.model_dump()}


########################################
# SQL Synthesis Agent
########################################

class SQLSynthesisAgent:
    """
    Agent responsible for synthesizing SQL queries, either from scratch
    or by combining SQL from multiple Genie agents.
    """
    
    def __init__(self, llm: Runnable):
        self.llm = llm
        self.name = "SQLSynthesis"
    
    def synthesize_sql_table_route(
        self, 
        query: str, 
        table_metadata: List[Dict]
    ) -> str:
        """
        Table Route: Directly synthesize SQL across multiple tables.
        
        Args:
            query: Original user question
            table_metadata: Metadata about relevant tables
            
        Returns:
            Synthesized SQL query
        """
        prompt = f"""
        You are an expert SQL developer. Generate a SQL query to answer the following question
        using the available tables.
        
        Question: {query}
        
        Available Tables and Metadata:
        {json.dumps(table_metadata, indent=2)}
        
        Generate a complete, executable SQL query. Include:
        - Proper JOINs where needed
        - WHERE clauses for filtering
        - Appropriate aggregations
        - Column aliases for clarity
        
        Return ONLY the SQL query, no explanations.
        """
        
        response = self.llm.invoke(prompt)
        return response.content.strip()
    
    def synthesize_sql_genie_route(
        self,
        query: str,
        sub_queries_with_sql: List[Dict[str, str]]
    ) -> str:
        """
        Genie Route: Combine SQL from multiple Genie agents into a unified query.
        
        Args:
            query: Original user question
            sub_queries_with_sql: List of {"sub_question": str, "sql": str}
            
        Returns:
            Combined SQL query
        """
        prompt = f"""
        You are an expert SQL developer. Combine the following SQL queries into a single query
        that answers the original question.
        
        Original Question: {query}
        
        Sub-queries and their SQL:
        {json.dumps(sub_queries_with_sql, indent=2)}
        
        Generate a unified SQL query that:
        - Combines results from sub-queries using JOINs, CTEs, or subqueries
        - Ensures proper correlation between results
        - Maintains data integrity
        - Returns the final answer to the original question
        
        Return ONLY the SQL query, no explanations.
        """
        
        response = self.llm.invoke(prompt)
        return response.content.strip()
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Process state and synthesize SQL."""
        query_plan = state.get("query_plan", {})
        messages = state.get("messages", [])
        
        # Determine which route to take
        if query_plan.get("join_strategy") == "table_route":
            # Use metadata to synthesize SQL directly
            table_metadata = state.get("table_metadata", [])
            sql = self.synthesize_sql_table_route(
                messages[0].content,
                table_metadata
            )
        else:
            # Combine SQL from Genie agents
            sub_results = state.get("genie_results", [])
            sql = self.synthesize_sql_genie_route(
                messages[0].content,
                sub_results
            )
        
        response_msg = AIMessage(
            content=f"Synthesized SQL:\n```sql\n{sql}\n```",
            name=self.name
        )
        
        return {"messages": [response_msg], "synthesized_sql": sql}


########################################
# SQL Execution Agent
########################################

class SQLExecutionAgent:
    """
    Agent responsible for executing SQL queries and returning results.
    """
    
    def __init__(self):
        self.name = "SQLExecution"
    
    def execute_sql(self, sql: str) -> Dict[str, Any]:
        """
        Execute SQL query and return results.
        
        Args:
            sql: SQL query to execute
            
        Returns:
            Dictionary with results and metadata
        """
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        
        try:
            result_df = spark.sql(sql)
            
            # Convert to markdown table for display
            pandas_df = result_df.toPandas()
            markdown_table = pandas_df.to_markdown(index=False)
            
            return {
                "success": True,
                "result": markdown_table,
                "row_count": len(pandas_df),
                "columns": list(pandas_df.columns)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "sql": sql
            }
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute synthesized SQL."""
        sql = state.get("synthesized_sql", "")
        
        if not sql:
            result = {
                "success": False,
                "error": "No SQL query to execute"
            }
        else:
            result = self.execute_sql(sql)
        
        if result["success"]:
            content = f"Query executed successfully!\n\n{result['result']}"
        else:
            content = f"Error executing query:\n{result['error']}"
        
        response_msg = AIMessage(content=content, name=self.name)
        
        return {"messages": [response_msg], "execution_result": result}


########################################
# Create LangGraph Supervisor
########################################

TOOLS = []


def stringify_content(state):
    """Helper to stringify message content if it's a list."""
    msgs = state["messages"]
    if isinstance(msgs[-1].content, list):
        msgs[-1].content = json.dumps(msgs[-1].content, indent=4)
    return {"messages": msgs}


def create_langgraph_supervisor(
    llm: Runnable,
    genie_spaces: List[Genie] = [],
    in_code_agents: List[InCodeSubAgent] = [],
    vector_search_function: str = None,
):
    """
    Create a LangGraph supervisor for the multi-agent system using modern LangGraph patterns.
    
    Args:
        llm: Language model for agents
        genie_spaces: List of Genie space configurations
        in_code_agents: List of in-code agent configurations
        vector_search_function: UC function name for vector search
    """
    # Build agent registry
    agents = {}
    agent_descriptions = ""
    
    # Add Thinking and Planning Agent
    thinking_agent = ThinkingPlanningAgent(llm, vector_search_function)
    agents["thinking_planning"] = thinking_agent
    agent_descriptions += (
        f"- ThinkingPlanning: Analyzes queries, breaks them into sub-tasks, "
        "and determines execution strategy\n"
    )
    
    # Add Genie Space Agents
    for genie in genie_spaces:
        agent_descriptions += f"- {genie.name}: {genie.description}\n"
        genie_agent = GenieAgent(
            genie_space_id=genie.space_id,
            genie_agent_name=genie.name,
            description=genie.description,
            include_context=True  # Include reasoning and SQL
        )
        genie_agent.name = genie.name
        agents[genie.name.lower().replace(" ", "_")] = genie_agent
    
    # Add SQL Synthesis Agent
    sql_synthesis_agent = SQLSynthesisAgent(llm)
    agents["sql_synthesis"] = sql_synthesis_agent
    agent_descriptions += (
        f"- SQLSynthesis: Synthesizes SQL queries across multiple "
        "tables or combines results from Genie agents\n"
    )
    
    # Add SQL Execution Agent
    sql_exec_agent = SQLExecutionAgent()
    agents["sql_execution"] = sql_exec_agent
    agent_descriptions += (
        f"- SQLExecution: Executes SQL queries and returns results\n"
    )
    
    # Add in-code tool-calling agents
    for agent_config in in_code_agents:
        agent_descriptions += f"- {agent_config.name}: {agent_config.description}\n"
        uc_toolkit = UCFunctionToolkit(function_names=agent_config.tools)
        TOOLS.extend(uc_toolkit.tools)
        tool_agent = create_tool_calling_agent(llm, tools=uc_toolkit.tools)
        agents[agent_config.name.lower().replace(" ", "_")] = tool_agent
    
    # Create supervisor with modern LangGraph StateGraph
    workflow = StateGraph(MessagesState)
    
    # Supervisor routing logic
    def supervisor_node(state: MessagesState):
        """Supervisor decides which agent to call next."""
        messages = state.get("messages", [])
        
        # Simple routing logic - this could be enhanced with LLM-based routing
        # For now, always start with thinking_planning
        if len(messages) == 1:  # First message
            return {"next": "thinking_planning"}
        
        # Route based on last message
        last_msg = messages[-1]
        if hasattr(last_msg, 'name'):
            if last_msg.name == "ThinkingPlanning":
                # Analyze plan and route accordingly
                try:
                    plan = json.loads(last_msg.content)
                    if not plan.get("question_clear", True):
                        return {"next": "END"}
                    if plan.get("requires_join"):
                        return {"next": "sql_synthesis"}
                    elif plan.get("requires_multiple_spaces"):
                        # Route to first relevant space
                        spaces = plan.get("relevant_space_ids", [])
                        if spaces:
                            return {"next": "genie"}
                        return {"next": "END"}
                    else:
                        return {"next": "genie"}
                except:
                    return {"next": "END"}
            elif last_msg.name == "SQLSynthesis":
                return {"next": "sql_execution"}
            else:
                return {"next": "END"}
        
        return {"next": "END"}
    
    # Add nodes for each agent
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("thinking_planning", lambda state: thinking_agent(state))
    workflow.add_node("sql_synthesis", lambda state: sql_synthesis_agent(state))
    workflow.add_node("sql_execution", lambda state: sql_exec_agent(state))
    
    # Add Genie agent nodes
    for genie in genie_spaces:
        agent_key = genie.name.lower().replace(" ", "_")
        workflow.add_node(agent_key, lambda state, a=agents[agent_key]: a(state))
    
    # Set entry point
    workflow.set_entry_point("thinking_planning")
    
    # Add edges
    workflow.add_edge("thinking_planning", "supervisor")
    
    # Conditional routing from supervisor
    def route_supervisor(state):
        next_agent = state.get("next", "END")
        return next_agent
    
    workflow.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "thinking_planning": "thinking_planning",
            "sql_synthesis": "sql_synthesis",
            "sql_execution": "sql_execution",
            "genie": list(agents.keys())[1] if len(agents) > 1 else "END",  # Route to first Genie
            "END": "__end__"
        }
    )
    
    workflow.add_edge("sql_synthesis", "sql_execution")
    workflow.add_edge("sql_execution", "__end__")
    
    # Add memory checkpointer
    memory = MemorySaver()
    
    return workflow.compile(checkpointer=memory)


########################################
# ResponsesAgent Wrapper for MLflow 3.7.0
########################################

class LangGraphResponsesAgent(ResponsesAgent):
    """
    MLflow 3.7.0 ResponsesAgent wrapper for LangGraph multi-agent system.
    
    This wrapper implements the ResponsesAgent interface following the official
    MLflow 3.7.0 patterns for serving LangGraph agents.
    
    Based on: https://mlflow.org/docs/latest/genai/flavors/responses-agent-intro.html
    """
    
    def __init__(self, agent: StateGraph):
        """
        Initialize with a compiled LangGraph agent.
        
        Args:
            agent: Compiled StateGraph (CompiledStateGraph) from LangGraph
        """
        self.agent = agent

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        """
        Synchronous prediction method.
        
        Collects all streaming events and returns a complete ResponsesAgentResponse.
        
        Args:
            request: ResponsesAgentRequest with input messages and custom inputs
            
        Returns:
            ResponsesAgentResponse with output items and custom outputs
        """
        outputs = [
            event.item
            for event in self.predict_stream(request)
            if event.type == "response.output_item.done"
        ]
        return ResponsesAgentResponse(
            output=outputs, 
            custom_outputs=request.custom_inputs
        )

    def predict_stream(
        self,
        request: ResponsesAgentRequest,
    ) -> Generator[ResponsesAgentStreamEvent, None, None]:
        """
        Streaming prediction method.
        
        Streams ResponsesAgentStreamEvents as the agent processes the request.
        
        Args:
            request: ResponsesAgentRequest with input messages
            
        Yields:
            ResponsesAgentStreamEvent objects as the agent processes
        """
        # Convert request input to chat completions format
        cc_msgs = to_chat_completions_input([i.model_dump() for i in request.input])

        # Stream agent execution
        for _, events in self.agent.stream(
            {"messages": cc_msgs}, 
            stream_mode=["updates"]
        ):
            # Process each node's output
            for node_data in events.values():
                if "messages" in node_data:
                    # Convert messages to response items stream
                    yield from output_to_responses_items_stream(node_data["messages"])


class MultiAgentSystem:
    """
    Simplified wrapper for testing and local development.
    For production deployment, use LangGraphChatModel with MLflow.
    """
    
    def __init__(self, graph):
        self.graph = graph
        self.config = {"configurable": {"thread_id": "default"}}

    def predict(self, input_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synchronous prediction for testing.
        
        Args:
            input_dict: Dictionary with "input" key containing message list
            
        Returns:
            Dictionary with agent response
        """
        messages = []
        for msg in input_dict.get("input", []):
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
            elif msg["role"] == "system":
                messages.append(SystemMessage(content=msg["content"]))
        
        result = self.graph.invoke(
            {"messages": messages},
            config=self.config
        )
        
        return {
            "messages": [
                {
                    "role": "assistant",
                    "content": msg.content if hasattr(msg, 'content') else str(msg)
                }
                for msg in result.get("messages", [])
            ]
        }

    def predict_stream(self, input_dict: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
        """
        Streaming prediction for testing.
        
        Args:
            input_dict: Dictionary with "input" key containing message list
            
        Yields:
            Dictionaries with agent responses
        """
        messages = []
        for msg in input_dict.get("input", []):
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        
        for event in self.graph.stream(
            {"messages": messages},
            config=self.config,
            stream_mode="updates"
        ):
            for node, output in event.items():
                if "messages" in output:
                    for msg in output["messages"]:
                        yield {
                            "node": node,
                            "content": msg.content if hasattr(msg, 'content') else str(msg)
                        }


########################################
# Configuration
########################################

# LLM Endpoint
LLM_ENDPOINT_NAME = os.getenv("LLM_ENDPOINT", "databricks-claude-sonnet-4-5")
llm = ChatDatabricks(endpoint=LLM_ENDPOINT_NAME)

# Vector Search Function
VECTOR_SEARCH_FUNCTION = os.getenv(
    "VECTOR_SEARCH_FUNCTION",
    "yyang.multi_agent_genie.search_genie_spaces"
)

# Genie Spaces Configuration
# Only include the 3 core Genie agents for Provider Enrollment, Claims, and Diagnosis/Procedures
GENIE_SPACES = [
    Genie(
        space_id="01f0956a54af123e9cd23907e8167df9",
        name="Provider Enrollment",
        description=(
            "This agent can answer questions about provider and patient enrollment. "
            "This dataset contains two tables: provider and enrollment. The provider table includes "
            "information about healthcare claims, such as claim ID, patient ID, provider NPI, provider role, "
            "and taxonomy code. "
            "The enrollment table contains patient demographic and enrollment details, including gender, year of birth, ZIP code, state, enrollment dates, benefit type, and pay type."
        ),
    ),
    Genie(
        space_id="01f0956a387714969edde65458dcc22a",
        name="Claims",
        description=(
            "This agent can answer questions about Medical and pharmacy claims. There are two "
            "tables: medical_claim and pharmacy_claim, both in the hv_claims_sample schema. Each "
            "table contains claims data with columns for claim_id, patient_id, date_service, and "
            "pay_type, among others. They can be connected by the patient_id column, which "
            "identifies the patient associated with each claim."
        ),
    ), 
    Genie(
        space_id="01f0956a4b0512e2a8aa325ffbac821b",
        name="Diagnosiss and Procedures",
        description=(
            "This agent can answer questions about diagnosiss and procedures. There are two tables: procedure and diagnosis, "
            "both in the hv_claims_sample schema. They are connected by the columns claim_id and patient_id, which appear in "
            "both tables and can be used to join procedure and diagnosis information for the same claim and patient."
        ),
    ),
]

# In-code tool agents
IN_CODE_AGENTS = [
    InCodeSubAgent(
        tools=["system.ai.*"],
        name="CodeExecutionAgent",
        description=(
            "Specializes in solving programming challenges, generating code snippets, "
            "debugging issues, and explaining complex coding concepts."
        ),
    )
]

########################################
# Create and Configure Agent
########################################

def get_agent_graph():
    """Factory function to create the agent graph."""
    return create_langgraph_supervisor(
        llm=llm,
        genie_spaces=GENIE_SPACES,
        in_code_agents=IN_CODE_AGENTS,
        vector_search_function=VECTOR_SEARCH_FUNCTION,
    )

# Create agent instance
supervisor_graph = get_agent_graph()

# Create wrapper for local testing (notebook use)
AGENT = MultiAgentSystem(supervisor_graph)

# Create MLflow 3.7.0 ResponsesAgent wrapper for deployment
MLFLOW_AGENT = LangGraphResponsesAgent(agent=supervisor_graph)

# Enable MLflow autologging for tracing
mlflow.langchain.autolog()

# Set the MLflow model for deployment
mlflow.models.set_model(MLFLOW_AGENT)

