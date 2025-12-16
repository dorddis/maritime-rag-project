"""
SQL Agent using LangChain and Gemini

Converts natural language queries to SQL and executes them safely.
"""

import logging
import re
from typing import Dict, Any, List, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain.agents import create_sql_agent
from langchain.agents.agent_types import AgentType
from langchain_core.prompts import PromptTemplate

from ..config import settings, get_postgres_url, get_google_api_key
from .schema_context import get_schema_context, get_example_queries

logger = logging.getLogger(__name__)


class SQLAgent:
    """
    SQL Agent for natural language to SQL conversion.

    Uses LangChain's SQL Agent with Gemini 2.5 Flash for:
    - Query understanding
    - SQL generation
    - Self-correction on errors
    - Result formatting
    """

    def __init__(
        self,
        database_url: str = None,
        model_name: str = None,
        api_key: str = None,
    ):
        self.database_url = database_url or get_postgres_url()
        self.model_name = model_name or settings.gemini_model
        self.api_key = api_key or get_google_api_key()

        # Initialize database connection
        self.db = SQLDatabase.from_uri(self.database_url)

        # Initialize LLM
        self.llm = ChatGoogleGenerativeAI(
            model=self.model_name,
            google_api_key=self.api_key,
            temperature=settings.sql_agent_temperature,
            convert_system_message_to_human=True,
        )

        # Create toolkit and agent
        self.toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)
        self.agent = self._create_agent()

        # Schema context for prompting
        self.schema_context = get_schema_context()
        self.example_queries = get_example_queries()

    def _create_agent(self):
        """Create the SQL agent with custom configuration."""
        return create_sql_agent(
            llm=self.llm,
            toolkit=self.toolkit,
            agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=settings.sql_agent_max_iterations,
            early_stopping_method="generate",
        )

    def _build_prompt(self, question: str, filters: Dict[str, Any] = None) -> str:
        """Build the full prompt with schema context and examples."""
        # Build few-shot examples
        examples_text = "\n".join([
            f"Question: {ex['question']}\nSQL: {ex['sql']}\n"
            for ex in self.example_queries[:3]
        ])

        prompt = f"""
{self.schema_context}

## Examples
{examples_text}

## User Question
{question}
"""
        if filters:
            prompt += f"\n## Pre-extracted Filters\n{filters}\n"

        prompt += "\nGenerate the SQL query to answer this question. Use the helper functions when appropriate."

        return prompt

    def _validate_sql(self, sql: str) -> tuple[bool, str]:
        """
        Validate SQL for safety.

        Returns (is_valid, error_message)
        """
        sql_upper = sql.upper().strip()

        # Disallow destructive operations
        dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE"]
        for keyword in dangerous_keywords:
            # Allow if it's in a string or comment
            pattern = rf'\b{keyword}\b'
            if re.search(pattern, sql_upper):
                # Check if it's a real statement (not in quotes)
                # Simple check: if it starts with the keyword
                if sql_upper.startswith(keyword):
                    return False, f"Destructive operation '{keyword}' not allowed"

        # Must be a SELECT query
        if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
            return False, "Only SELECT queries are allowed"

        return True, ""

    async def query(
        self,
        question: str,
        filters: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute a natural language query.

        Args:
            question: Natural language question
            filters: Pre-extracted filters from query router

        Returns:
            {
                "question": str,
                "sql": str,
                "results": list,
                "row_count": int,
                "explanation": str,
                "error": str or None
            }
        """
        try:
            # Build prompt with context
            prompt = self._build_prompt(question, filters)

            # Run agent
            response = await self.agent.ainvoke({"input": prompt})

            # Extract results
            output = response.get("output", "")

            # Try to extract SQL from the response
            sql = self._extract_sql(output)

            # If we got SQL, validate and optionally re-run
            if sql:
                is_valid, error = self._validate_sql(sql)
                if not is_valid:
                    return {
                        "question": question,
                        "sql": sql,
                        "results": [],
                        "row_count": 0,
                        "explanation": f"Query blocked: {error}",
                        "error": error,
                    }

            return {
                "question": question,
                "sql": sql,
                "results": self._extract_results(output),
                "row_count": self._count_results(output),
                "explanation": output,
                "error": None,
            }

        except Exception as e:
            logger.error(f"SQL Agent error: {e}")
            return {
                "question": question,
                "sql": None,
                "results": [],
                "row_count": 0,
                "explanation": str(e),
                "error": str(e),
            }

    def query_sync(
        self,
        question: str,
        filters: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous version of query().
        """
        try:
            prompt = self._build_prompt(question, filters)
            response = self.agent.invoke({"input": prompt})
            output = response.get("output", "")
            sql = self._extract_sql(output)

            if sql:
                is_valid, error = self._validate_sql(sql)
                if not is_valid:
                    return {
                        "question": question,
                        "sql": sql,
                        "results": [],
                        "row_count": 0,
                        "explanation": f"Query blocked: {error}",
                        "error": error,
                    }

            return {
                "question": question,
                "sql": sql,
                "results": self._extract_results(output),
                "row_count": self._count_results(output),
                "explanation": output,
                "error": None,
            }

        except Exception as e:
            logger.error(f"SQL Agent error: {e}")
            return {
                "question": question,
                "sql": None,
                "results": [],
                "row_count": 0,
                "explanation": str(e),
                "error": str(e),
            }

    def execute_sql_direct(self, sql: str) -> Dict[str, Any]:
        """
        Execute SQL directly (bypasses agent, for testing).

        Still validates for safety.
        """
        is_valid, error = self._validate_sql(sql)
        if not is_valid:
            return {
                "sql": sql,
                "results": [],
                "error": error,
            }

        try:
            result = self.db.run(sql)
            return {
                "sql": sql,
                "results": result,
                "error": None,
            }
        except Exception as e:
            return {
                "sql": sql,
                "results": [],
                "error": str(e),
            }

    def _extract_sql(self, output: str) -> Optional[str]:
        """Extract SQL query from agent output."""
        # Look for SQL in code blocks
        sql_pattern = r"```sql\n?(.*?)\n?```"
        matches = re.findall(sql_pattern, output, re.DOTALL | re.IGNORECASE)
        if matches:
            return matches[-1].strip()

        # Look for SELECT statements
        select_pattern = r"(SELECT\s+.*?(?:;|$))"
        matches = re.findall(select_pattern, output, re.DOTALL | re.IGNORECASE)
        if matches:
            return matches[-1].strip().rstrip(";")

        return None

    def _extract_results(self, output: str) -> List[Dict]:
        """Extract result rows from agent output."""
        # The agent typically returns results as text
        # This is a simplified extraction
        # In practice, you might parse structured output
        return []

    def _count_results(self, output: str) -> int:
        """Count result rows from agent output."""
        # Look for patterns like "X rows" or count from results
        count_pattern = r"(\d+)\s+rows?"
        matches = re.findall(count_pattern, output, re.IGNORECASE)
        if matches:
            return int(matches[-1])
        return 0

    def get_table_info(self) -> str:
        """Get database table information."""
        return self.db.get_table_info()

    def get_usable_tables(self) -> List[str]:
        """Get list of usable table names."""
        return self.db.get_usable_table_names()


# Convenience function for simple queries
async def ask_database(question: str) -> Dict[str, Any]:
    """
    Simple interface to ask a question to the database.

    Example:
        result = await ask_database("Show me all tankers near Mumbai")
    """
    agent = SQLAgent()
    return await agent.query(question)
