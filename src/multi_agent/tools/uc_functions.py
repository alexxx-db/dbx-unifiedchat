"""
Unity Catalog Functions Registration for Multi-Agent System

This module registers UC functions that provide metadata querying capabilities
for the SQL Synthesis Agent.

Available UC functions:
1. get_space_summary - High-level space information
2. get_table_overview - Table-level metadata
3. get_column_detail - Column-level metadata
4. get_space_instructions - SQL examples, filters, and measures guidance (REQUIRED FINAL STEP)
5. get_space_details - Complete metadata (last resort)

Usage:
    from src.multi_agent.tools.uc_functions import register_uc_functions
    
    # Register all UC functions before creating agents
    register_uc_functions(catalog="my_catalog", schema="my_schema", table_name="enriched_genie_docs_chunks")
"""

from typing import Optional

try:
    from databricks.sdk.runtime import spark
except ImportError:
    spark = None


def register_uc_functions(
    catalog: str,
    schema: str,
    table_name: str,
    drop_if_exists: bool = False,
    verbose: bool = True
) -> dict:
    """
    Register all UC functions required by the SQL Synthesis Agent.
    
    This function creates 5 UC functions in Unity Catalog that provide
    metadata querying capabilities at different granularities.
    
    IMPORTANT: This must be called BEFORE creating SQLSynthesisTableAgent
    to ensure the functions exist when the agent initializes its toolkit.
    
    Args:
        catalog: Unity Catalog catalog name
        schema: Schema name where functions will be created
        table_name: Fully qualified name of enriched_genie_docs_chunks table
        drop_if_exists: If True, drop existing functions before creating
        verbose: If True, print registration progress
        
    Returns:
        Dictionary with registration status:
        {
            "success": bool,
            "registered_functions": list[str],
            "errors": list[str]
        }
    
    Example:
        >>> from src.multi_agent.tools.uc_functions import register_uc_functions
        >>> register_uc_functions(
        ...     catalog="my_catalog",
        ...     schema="my_schema", 
        ...     table_name="my_catalog.my_schema.enriched_genie_docs_chunks"
        ... )
        {"success": True, "registered_functions": [...], "errors": []}
    """
    if spark is None:
        return {
            "success": False,
            "registered_functions": [],
            "errors": ["Spark runtime not available. This function must be called in Databricks environment."]
        }
    
    registered = []
    errors = []
    
    if verbose:
        print("=" * 80)
        print("REGISTERING UNITY CATALOG FUNCTIONS")
        print("=" * 80)
        print(f"Target table: {table_name}")
        print(f"Functions will be created in: {catalog}.{schema}")
        print("=" * 80)
    
    # Optional: Drop existing functions
    if drop_if_exists:
        function_names = [
            "get_space_summary",
            "get_table_overview", 
            "get_column_detail",
            "get_space_details",
            "get_space_instructions"
        ]
        for func_name in function_names:
            try:
                spark.sql(f'DROP FUNCTION IF EXISTS {catalog}.{schema}.{func_name}')
                if verbose:
                    print(f"✓ Dropped existing function: {func_name}")
            except Exception as e:
                if verbose:
                    print(f"⚠ Warning dropping {func_name}: {str(e)}")
    
    # UC Function 1: get_space_summary
    try:
        spark.sql(f"""
CREATE OR REPLACE FUNCTION {catalog}.{schema}.get_space_summary(
    space_ids_json STRING DEFAULT 'null' COMMENT 'JSON array of space IDs to query, or "null" to retrieve all spaces. Example: ["space_1", "space_2"] or "null"'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Get high-level summary of Genie spaces. Returns JSON with space summaries including chunk_id, chunk_type, space_title, and content.'
RETURN
    SELECT COALESCE(
        to_json(
            map_from_entries(
                collect_list(
                    struct(
                        space_id,
                        named_struct(
                            'chunk_id', chunk_id,
                            'chunk_type', chunk_type,
                            'space_title', space_title,
                            'content', searchable_content
                        )
                    )
                )
            )
        ),
        '{{}}')
    ) as result
    FROM {table_name}
    WHERE chunk_type = 'space_summary'
    AND (
        space_ids_json IS NULL 
        OR TRIM(LOWER(space_ids_json)) IN ('null', 'none', '')
        OR array_contains(from_json(space_ids_json, 'array<string>'), space_id)
    )
""")
        registered.append("get_space_summary")
        if verbose:
            print("✓ Registered: get_space_summary")
    except Exception as e:
        errors.append(f"get_space_summary: {str(e)}")
        if verbose:
            print(f"✗ Failed to register get_space_summary: {str(e)}")
    
    # UC Function 2: get_table_overview
    try:
        spark.sql(f"""
CREATE OR REPLACE FUNCTION {catalog}.{schema}.get_table_overview(
    space_ids_json STRING DEFAULT 'null' COMMENT 'JSON array of space IDs to query (required, prefer single space). Example: ["space_1"]',
    table_names_json STRING DEFAULT 'null' COMMENT 'JSON array of table names to filter, or "null" for all tables in the specified spaces. Example: ["table1", "table2"] or "null"'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Get table-level metadata for specific Genie spaces. Returns JSON with table metadata including chunk_id, chunk_type, table_name, and content grouped by space.'
RETURN
    SELECT COALESCE(
        to_json(
            map_from_entries(
                collect_list(
                    struct(
                        space_id,
                        named_struct(
                            'space_title', space_title,
                            'tables', tables
                        )
                    )
                )
            )
        ),
        '{{}}')
    ) as result
    FROM (
        SELECT 
            space_id,
            first(space_title) as space_title,
            collect_list(
                named_struct(
                    'chunk_id', chunk_id,
                    'chunk_type', chunk_type,
                    'table_name', table_name,
                    'content', searchable_content
                )
            ) as tables
        FROM {table_name}
        WHERE chunk_type = 'table_overview'
        AND array_contains(from_json(space_ids_json, 'array<string>'), space_id)
        AND (
            table_names_json IS NULL 
            OR TRIM(LOWER(table_names_json)) IN ('null', 'none', '')
            OR array_contains(from_json(table_names_json, 'array<string>'), table_name)
        )
        GROUP BY space_id
    )
""")
        registered.append("get_table_overview")
        if verbose:
            print("✓ Registered: get_table_overview")
    except Exception as e:
        errors.append(f"get_table_overview: {str(e)}")
        if verbose:
            print(f"✗ Failed to register get_table_overview: {str(e)}")
    
    # UC Function 3: get_column_detail
    try:
        spark.sql(f"""
CREATE OR REPLACE FUNCTION {catalog}.{schema}.get_column_detail(
    space_ids_json STRING DEFAULT 'null' COMMENT 'JSON array of space IDs to query (required, prefer single space). Example: ["space_1"]',
    table_names_json STRING DEFAULT 'null' COMMENT 'JSON array of table names to filter (required, prefer single table). Example: ["table1"]',
    column_names_json STRING DEFAULT 'null' COMMENT 'JSON array of column names to filter, or "null" for all columns in the specified tables. Example: ["col1", "col2"] or "null"'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Get column-level metadata for specific Genie spaces. Returns JSON with column metadata including chunk_id, chunk_type, table_name, column_name, and content grouped by space.'
RETURN
    SELECT COALESCE(
        to_json(
            map_from_entries(
                collect_list(
                    struct(
                        space_id,
                        named_struct(
                            'space_title', space_title,
                            'columns', columns
                        )
                    )
                )
            )
        ),
        '{{}}')
    ) as result
    FROM (
        SELECT 
            space_id,
            first(space_title) as space_title,
            collect_list(
                named_struct(
                    'chunk_id', chunk_id,
                    'chunk_type', chunk_type,
                    'table_name', table_name,
                    'column_name', column_name,
                    'content', searchable_content
                )
            ) as columns
        FROM {table_name}
        WHERE chunk_type = 'column_detail'
        AND array_contains(from_json(space_ids_json, 'array<string>'), space_id)
        AND array_contains(from_json(table_names_json, 'array<string>'), table_name)
        AND (
            column_names_json IS NULL 
            OR TRIM(LOWER(column_names_json)) IN ('null', 'none', '')
            OR array_contains(from_json(column_names_json, 'array<string>'), column_name)
        )
        GROUP BY space_id
    )
""")
        registered.append("get_column_detail")
        if verbose:
            print("✓ Registered: get_column_detail")
    except Exception as e:
        errors.append(f"get_column_detail: {str(e)}")
        if verbose:
            print(f"✗ Failed to register get_column_detail: {str(e)}")
    
    # UC Function 4: get_space_details
    try:
        spark.sql(f"""
CREATE OR REPLACE FUNCTION {catalog}.{schema}.get_space_details(
    space_ids_json STRING DEFAULT 'null' COMMENT 'JSON array of space IDs to query (required). Example: ["space_1", "space_2"]. WARNING: Returns large metadata - use as LAST RESORT.'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Get complete metadata for specific Genie spaces - use as LAST RESORT (token intensive). Returns JSON with complete space metadata including chunk_id, chunk_type, space_title, and all available metadata content.'
RETURN
    SELECT COALESCE(
        to_json(
            map_from_entries(
                collect_list(
                    struct(
                        space_id,
                        named_struct(
                            'chunk_id', chunk_id,
                            'chunk_type', chunk_type,
                            'space_title', space_title,
                            'complete_metadata', searchable_content
                        )
                    )
                )
            )
        ),
        '{{}}')
    ) as result
    FROM {table_name}
    WHERE chunk_type = 'space_details'
    AND array_contains(from_json(space_ids_json, 'array<string>'), space_id)
""")
        registered.append("get_space_details")
        if verbose:
            print("✓ Registered: get_space_details")
    except Exception as e:
        errors.append(f"get_space_details: {str(e)}")
        if verbose:
            print(f"✗ Failed to register get_space_details: {str(e)}")
    
    # UC Function 5: get_space_instructions (REQUIRED FINAL STEP)
    try:
        spark.sql(f"""
CREATE OR REPLACE FUNCTION {catalog}.{schema}.get_space_instructions(
    space_ids_json STRING DEFAULT 'null' COMMENT 'JSON array of space IDs to query (required). Example: ["space_1", "space_2"]'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'Extract SQL instructions from Genie space metadata. Returns JSON with space-specific SQL guidance. The instructions field contains the raw JSON content from serialized_space.instructions, which may include example queries, filters, measures, and other space-specific guidance.'
RETURN
    SELECT COALESCE(
        to_json(
            map_from_entries(
                collect_list(
                    struct(
                        space_id,
                        named_struct(
                            'chunk_id', chunk_id,
                            'chunk_type', chunk_type,
                            'space_title', space_title,
                            'instructions', get_json_object(metadata_json, '$.serialized_space.instructions')
                        )
                    )
                )
            )
        ),
        '{{}}')
    ) as result
    FROM {table_name}
    WHERE chunk_type = 'space_details'
    AND array_contains(from_json(space_ids_json, 'array<string>'), space_id)
""")
        registered.append("get_space_instructions")
        if verbose:
            print("✓ Registered: get_space_instructions")
    except Exception as e:
        errors.append(f"get_space_instructions: {str(e)}")
        if verbose:
            print(f"✗ Failed to register get_space_instructions: {str(e)}")
    
    # Print summary
    if verbose:
        print("\n" + "=" * 80)
        if not errors:
            print(f"✅ ALL {len(registered)} UC FUNCTIONS REGISTERED SUCCESSFULLY!")
        else:
            print(f"⚠ PARTIAL SUCCESS: {len(registered)}/{len(registered) + len(errors)} functions registered")
        print("=" * 80)
        print("Functions available for SQL Synthesis Agent:")
        for i, func_name in enumerate(registered, 1):
            print(f"  {i}. {catalog}.{schema}.{func_name}")
        if errors:
            print("\nErrors:")
            for error in errors:
                print(f"  ✗ {error}")
        print("=" * 80)
    
    return {
        "success": len(errors) == 0,
        "registered_functions": registered,
        "errors": errors
    }


def check_uc_functions_exist(catalog: str, schema: str, verbose: bool = True) -> dict:
    """
    Check if all required UC functions exist in the specified catalog.schema.
    
    Args:
        catalog: Unity Catalog catalog name
        schema: Schema name
        verbose: If True, print check results
        
    Returns:
        Dictionary with:
        {
            "all_exist": bool,
            "existing_functions": list[str],
            "missing_functions": list[str]
        }
    """
    if spark is None:
        return {
            "all_exist": False,
            "existing_functions": [],
            "missing_functions": [],
            "error": "Spark runtime not available"
        }
    
    required_functions = [
        "get_space_summary",
        "get_table_overview",
        "get_column_detail",
        "get_space_instructions",
        "get_space_details"
    ]
    
    existing = []
    missing = []
    
    for func_name in required_functions:
        try:
            # Try to describe the function
            result = spark.sql(f"DESCRIBE FUNCTION {catalog}.{schema}.{func_name}").collect()
            if result:
                existing.append(func_name)
        except Exception:
            missing.append(func_name)
    
    if verbose:
        print("=" * 80)
        print("UC FUNCTIONS STATUS CHECK")
        print("=" * 80)
        print(f"Catalog: {catalog}")
        print(f"Schema: {schema}")
        print("=" * 80)
        
        if existing:
            print(f"✓ Existing functions ({len(existing)}):")
            for func in existing:
                print(f"  - {func}")
        
        if missing:
            print(f"\n✗ Missing functions ({len(missing)}):")
            for func in missing:
                print(f"  - {func}")
            print("\nTo register missing functions, call:")
            print(f"  register_uc_functions(catalog='{catalog}', schema='{schema}', table_name='...')")
        else:
            print("\n✅ All UC functions are registered!")
        
        print("=" * 80)
    
    return {
        "all_exist": len(missing) == 0,
        "existing_functions": existing,
        "missing_functions": missing
    }

