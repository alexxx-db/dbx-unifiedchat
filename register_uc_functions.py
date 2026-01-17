"""
Unity Catalog Function Registration Script

This script registers the custom agent functions as Unity Catalog functions.
Run this in a Databricks notebook or job to register the functions.

Prerequisites:
1. Ensure you have CREATE FUNCTION permissions on the target catalog/schema
2. Upload agent_uc_functions.py to a volume or DBFS location
3. Update CATALOG and SCHEMA constants below
"""

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import (
    FunctionInfo,
    FunctionParameterInfo,
    FunctionParameterInfos,
    ColumnTypeName,
)

# Configuration
CATALOG = "yyang"
SCHEMA = "multi_agent_genie"
PYTHON_FILE_PATH = "/Workspace/Users/yang.yang@databricks.com/agent_uc_functions.py"

# Initialize Workspace Client
w = WorkspaceClient()

########################################
# Function Registration Definitions
########################################

FUNCTIONS_TO_REGISTER = [
    {
        "name": "analyze_query_plan",
        "comment": "Analyze a user query and create an execution plan using vector search and LLM reasoning.",
        "parameters": [
            FunctionParameterInfo(
                name="query",
                type_text="STRING",
                type_name=ColumnTypeName.STRING,
                comment="The user's question to analyze",
                position=0
            ),
            FunctionParameterInfo(
                name="vector_search_index",
                type_text="STRING",
                type_name=ColumnTypeName.STRING,
                comment="Full name of the vector search index",
                position=1,
                parameter_default=f'"{CATALOG}.{SCHEMA}.enriched_genie_docs_chunks_vs_index"'
            ),
            FunctionParameterInfo(
                name="num_results",
                type_text="INT",
                type_name=ColumnTypeName.INT,
                comment="Number of relevant spaces to retrieve",
                position=2,
                parameter_default="5"
            ),
        ],
        "return_type": "STRING",
        "return_comment": "JSON string with QueryPlan structure",
        "routine_body": "EXTERNAL",
        "routine_definition": f"""
from agent_uc_functions import analyze_query_plan
return analyze_query_plan(query, vector_search_index, num_results)
""",
    },
    {
        "name": "synthesize_sql_table_route",
        "comment": "Synthesize SQL query directly across multiple tables (table route).",
        "parameters": [
            FunctionParameterInfo(
                name="query",
                type_text="STRING",
                type_name=ColumnTypeName.STRING,
                comment="The user's question",
                position=0
            ),
            FunctionParameterInfo(
                name="table_metadata_json",
                type_text="STRING",
                type_name=ColumnTypeName.STRING,
                comment="JSON string with table metadata",
                position=1
            ),
        ],
        "return_type": "STRING",
        "return_comment": "SQL query string",
        "routine_body": "EXTERNAL",
        "routine_definition": f"""
from agent_uc_functions import synthesize_sql_table_route
return synthesize_sql_table_route(query, table_metadata_json)
""",
    },
    {
        "name": "synthesize_sql_genie_route",
        "comment": "Combine SQL from multiple Genie agents into a unified query (genie route).",
        "parameters": [
            FunctionParameterInfo(
                name="query",
                type_text="STRING",
                type_name=ColumnTypeName.STRING,
                comment="The original user question",
                position=0
            ),
            FunctionParameterInfo(
                name="sub_queries_json",
                type_text="STRING",
                type_name=ColumnTypeName.STRING,
                comment="JSON string with list of sub-queries and their SQL",
                position=1
            ),
        ],
        "return_type": "STRING",
        "return_comment": "Combined SQL query string",
        "routine_body": "EXTERNAL",
        "routine_definition": f"""
from agent_uc_functions import synthesize_sql_genie_route
return synthesize_sql_genie_route(query, sub_queries_json)
""",
    },
    {
        "name": "execute_sql_query",
        "comment": "Execute a SQL query and return results as a formatted string.",
        "parameters": [
            FunctionParameterInfo(
                name="sql",
                type_text="STRING",
                type_name=ColumnTypeName.STRING,
                comment="SQL query to execute",
                position=0
            ),
        ],
        "return_type": "STRING",
        "return_comment": "JSON string with execution results",
        "routine_body": "EXTERNAL",
        "routine_definition": f"""
from agent_uc_functions import execute_sql_query
return execute_sql_query(sql)
""",
    },
    {
        "name": "get_table_metadata",
        "comment": "Retrieve table metadata for given Genie space IDs.",
        "parameters": [
            FunctionParameterInfo(
                name="space_ids_json",
                type_text="STRING",
                type_name=ColumnTypeName.STRING,
                comment="JSON string with list of space_ids",
                position=0
            ),
        ],
        "return_type": "STRING",
        "return_comment": "JSON string with table metadata",
        "routine_body": "EXTERNAL",
        "routine_definition": f"""
from agent_uc_functions import get_table_metadata
return get_table_metadata(space_ids_json)
""",
    },
    {
        "name": "verbal_merge_results",
        "comment": "Verbally merge results from multiple Genie agents using LLM.",
        "parameters": [
            FunctionParameterInfo(
                name="query",
                type_text="STRING",
                type_name=ColumnTypeName.STRING,
                comment="Original user question",
                position=0
            ),
            FunctionParameterInfo(
                name="results_json",
                type_text="STRING",
                type_name=ColumnTypeName.STRING,
                comment="JSON string with list of results from different agents",
                position=1
            ),
        ],
        "return_type": "STRING",
        "return_comment": "Merged response text",
        "routine_body": "EXTERNAL",
        "routine_definition": f"""
from agent_uc_functions import verbal_merge_results
return verbal_merge_results(query, results_json)
""",
    },
]


########################################
# Registration Functions
########################################

def register_function(func_config: dict):
    """Register a single UC function."""
    full_name = f"{CATALOG}.{SCHEMA}.{func_config['name']}"
    
    try:
        # Check if function exists
        try:
            existing = w.functions.get(full_name)
            print(f"Function {full_name} already exists. Deleting...")
            w.functions.delete(full_name, force=True)
        except Exception:
            pass  # Function doesn't exist, which is fine
        
        # Create function
        print(f"Creating function {full_name}...")
        
        function_info = FunctionInfo(
            catalog_name=CATALOG,
            schema_name=SCHEMA,
            name=func_config["name"],
            comment=func_config["comment"],
            parameters=FunctionParameterInfos(
                parameters=func_config["parameters"]
            ),
            return_params=FunctionParameterInfos(
                parameters=[
                    FunctionParameterInfo(
                        name="result",
                        type_text=func_config["return_type"],
                        type_name=getattr(ColumnTypeName, func_config["return_type"]),
                        comment=func_config["return_comment"],
                        position=0
                    )
                ]
            ),
            routine_body=func_config["routine_body"],
            routine_definition=func_config["routine_definition"],
            external_language="PYTHON",
            is_deterministic=False,
            security_type="DEFINER",
            specific_name=func_config["name"],
        )
        
        w.functions.create(function_info=function_info)
        print(f"✅ Successfully created {full_name}")
        
    except Exception as e:
        print(f"❌ Error creating {full_name}: {str(e)}")
        raise


def register_all_functions():
    """Register all UC functions."""
    print(f"\n{'='*60}")
    print(f"Registering UC Functions in {CATALOG}.{SCHEMA}")
    print(f"{'='*60}\n")
    
    success_count = 0
    error_count = 0
    
    for func_config in FUNCTIONS_TO_REGISTER:
        try:
            register_function(func_config)
            success_count += 1
        except Exception as e:
            print(f"Error details: {e}")
            error_count += 1
    
    print(f"\n{'='*60}")
    print(f"Registration Complete: {success_count} succeeded, {error_count} failed")
    print(f"{'='*60}\n")
    
    if success_count > 0:
        print("✅ Functions registered successfully. You can now use them with:")
        print(f"   UCFunctionToolkit(function_names=['{CATALOG}.{SCHEMA}.*'])")


########################################
# Alternative: SQL-based Registration
########################################

def generate_sql_statements():
    """
    Generate SQL statements for manual function registration.
    Use this if the SDK-based registration doesn't work.
    """
    print("\n" + "="*60)
    print("SQL Statements for Manual Registration")
    print("="*60 + "\n")
    
    for func_config in FUNCTIONS_TO_REGISTER:
        full_name = f"{CATALOG}.{SCHEMA}.{func_config['name']}"
        
        # Build parameter list
        params = []
        for p in func_config["parameters"]:
            param_str = f"{p.name} {p.type_text}"
            if hasattr(p, 'parameter_default') and p.parameter_default:
                param_str += f" DEFAULT {p.parameter_default}"
            param_str += f" COMMENT '{p.comment}'"
            params.append(param_str)
        
        param_list = ",\n  ".join(params)
        
        sql = f"""
-- Drop existing function if it exists
DROP FUNCTION IF EXISTS {full_name};

-- Create function
CREATE FUNCTION {full_name}(
  {param_list}
)
RETURNS {func_config['return_type']}
LANGUAGE PYTHON
COMMENT '{func_config['comment']}'
AS $$
{func_config['routine_definition'].strip()}
$$;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION {full_name} TO `account users`;
"""
        print(sql)
        print("\n" + "-"*60 + "\n")


########################################
# Main Execution
########################################

if __name__ == "__main__":
    import sys
    
    print("\n" + "="*60)
    print("UC Function Registration Tool")
    print("="*60 + "\n")
    
    print(f"Target: {CATALOG}.{SCHEMA}")
    print(f"Python file: {PYTHON_FILE_PATH}\n")
    
    choice = input("Choose registration method:\n1. SDK-based (recommended)\n2. Generate SQL statements\nEnter choice (1 or 2): ")
    
    if choice == "1":
        confirm = input(f"\nThis will register {len(FUNCTIONS_TO_REGISTER)} functions. Continue? (y/n): ")
        if confirm.lower() == 'y':
            register_all_functions()
        else:
            print("Registration cancelled.")
    elif choice == "2":
        generate_sql_statements()
    else:
        print("Invalid choice. Exiting.")
        sys.exit(1)

