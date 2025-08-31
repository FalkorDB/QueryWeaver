"""
Graphiti integration for QueryWeaver memory component.
Saves summarized conversations with user and database nodes.
"""

import asyncio
import os
from typing import List, Dict, Any, Optional
from datetime import datetime

# Import Azure OpenAI components
from openai import AsyncAzureOpenAI

# Import Graphiti components
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core import Graphiti
from api.extensions import db
from api.config import Config
from graphiti_core.nodes import EpisodeType
from graphiti_core.llm_client import LLMConfig, OpenAIClient
from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder import OpenAIRerankerClient
from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF


from litellm import completion


class MemoryTool:
    """Memory management tool for handling user memories and interactions."""

    def __init__(self, user_id: str, graph_id: str):
        # Create FalkorDB driver with user-specific database
        user_memory_db = f"{user_id}-memory"
        falkor_driver = FalkorDriver(falkor_db=db, database=user_memory_db)

       
        # Create Graphiti client with Azure OpenAI configuration
        self.graphiti_client = create_graphiti_client(falkor_driver)

        self.user_id = user_id
        self.graph_id = graph_id
        self.config = Config()


    @classmethod
    async def create(cls, user_id: str, graph_id: str) -> "MemoryTool":
        """Async factory to construct and initialize the tool."""
        self = cls(user_id, graph_id)
        await self._ensure_database_node(graph_id, user_id)

        vector_size = Config.EMBEDDING_MODEL.get_vector_size()
        driver = self.graphiti_client.driver
        await driver.execute_query(f"CREATE VECTOR INDEX FOR (p:Query) ON (p.embeddings) OPTIONS {{dimension:{vector_size}, similarityFunction:'euclidean'}}")

        return self

    async def _ensure_user_node(self, user_id: str) -> Optional[str]:
        """Ensure user node exists in the memory graph."""
        user_node_name = f"User {user_id}"
        try:
            # First check if user node already exists
            node_search_config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
            node_search_config.limit = 1  # Limit to 1 results

            # Execute the node search
            node_search_results = await self.graphiti_client.search_(
                query=user_node_name,
                config=node_search_config,
            )
            
            # If user node already exists, return the user_id
            if node_search_results and len(node_search_results.nodes) > 0:
                # Check if any result exactly matches the expected node name
                for node in node_search_results.nodes:
                    if node.name == user_node_name:
                        print(f"User node for {user_id} already exists")
                        return user_id
            
            # Create new user node if it doesn't exist
            await self.graphiti_client.add_episode(
                name=user_node_name,
                episode_body=f'User {user_id} is using QueryWeaver',
                source=EpisodeType.text,
                reference_time=datetime.now(),
                source_description='User node creation'
            )
            print(f"Created new user node for {user_id}")
            return user_id
            
        except Exception as e:
            print(f"Error creating user node for {user_id}: {e}")
            return None

    async def _ensure_database_node(self, database_name: str, user_id: str) -> Optional[str]:
        """Ensure database node exists in the memory graph."""
        database_node_name = f"Database {database_name}"
        try:
            # First check if database node already exists
            node_search_config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
            node_search_config.limit = 1  # Limit to 1 results

            # Execute the node search
            node_search_results = await self.graphiti_client.search_(
                query=database_node_name,
                config=node_search_config,
            )
            
            # If database node already exists, return the database_name
            if node_search_results and len(node_search_results.nodes) > 0:
                # Check if any result exactly matches the expected node name
                for node in node_search_results.nodes:
                    if node.name == database_node_name:
                        print(f"Database node for {database_name} already exists")
                        return database_name
            
            # Create new database node if it doesn't exist
            await self.graphiti_client.add_episode(
                name=database_node_name,
                episode_body=f'User {user_id} has database {database_name} available for querying',
                source=EpisodeType.text,
                reference_time=datetime.now(),
                source_description='Database node creation'
            )
            print(f"Created new database node for {database_name}")
            return database_name
            
        except Exception as e:
            print(f"Error creating database node for {database_name}: {e}")
            return None

    async def add_new_memory(self, conversation: Dict[str, Any]) -> bool:
        # Use LLM to analyze and summarize the conversation with focus on graph-oriented database facts
        analysis = await self.summarize_conversation(conversation)
        user_id = self.user_id
        database_name = self.graph_id

        # Extract summaries
        database_summary = analysis.get("database_summary", "")
        
        try:
            if database_summary:
                await self.graphiti_client.add_episode(
                    name=f"Database_Facts_{user_id}_{database_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    episode_body=f"Database: {database_name}\n{database_summary}",
                    source=EpisodeType.message,
                    reference_time=datetime.now(),
                    source_description=f"Graph-oriented facts about Database: {database_name} from User: {user_id} interaction"
                )
            
            # Keep personal memory as it was originally (only question)
            await self.graphiti_client.add_episode(
                name=f"Personal_Memory_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                episode_body=f"User: {user_id}\n{conversation['question']}",
                source=EpisodeType.message,
                reference_time=datetime.now(),
                source_description=f"Personal memory for user {user_id}"
            )
                
        except Exception as e:
            print(f"Error adding new memory episodes: {e}")
            return False
        
        return True

    async def save_query_memory(self, query: str, sql_query: str, success: bool, error: Optional[str] = None) -> bool:
        """
        Save individual query memory directly to the database node.
        
        Args:
            query: The user's natural language query
            sql_query: The generated SQL query
            success: Whether the query execution was successful
            error: Error message if the query failed
            
        Returns:
            bool: True if memory was saved successfully, False otherwise
        """
        try:
            database_name = self.graph_id
            
            # Find the database node
            database_node_name = f"Database {database_name}"
            node_search_config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
            node_search_config.limit = 1
            
            database_node_results = await self.graphiti_client.search_(
                query=database_node_name,
                config=node_search_config,
            )
            
            # Check if database node exists
            database_node_exists = False
            for node in database_node_results.nodes:
                if node.name == database_node_name:
                    database_node_exists = True
                    database_node_uuid = node.uuid
                    break
            if not database_node_exists:
                return False

            # Check if Query node with same user_query and sql_query already exists
            relationship_type = "SUCCESS" if success else "FAILED"
            
            # Escape quotes in the query and SQL for Cypher
            escaped_query = query.replace("'", "\\'").replace('"', '\\"')
            escaped_sql = sql_query.replace("'", "\\'").replace('"', '\\"')
            escaped_error = error.replace("'", "\\'").replace('"', '\\"') if error else ""
            embeddings = Config.EMBEDDING_MODEL.embed(escaped_query)[0]

            # First check if a Query node with the same user_query and sql_query already exists
            check_query = f"""
            MATCH (db:Entity {{uuid: "{database_node_uuid}"}})
            MATCH (db)-[r]->(q:Query)
            WHERE q.user_query = "{escaped_query}" AND q.sql_query = "{escaped_sql}"
            RETURN q.uuid as existing_query_uuid
            LIMIT 1
            """
            
            graph_driver = self.graphiti_client.driver
            check_result = await graph_driver.execute_query(check_query)
            
            # If query already exists, don't create a duplicate
            if check_result[0]:  # If records exist
                print(f"Query with same user_query and sql_query already exists, skipping creation")
                return True

            # Create the Query node and relationship using Cypher only if it doesn't exist
            cypher_query = f"""
            MATCH (db:Entity {{uuid: "{database_node_uuid}"}})
            MERGE (q:Query {{
                user_query: "{escaped_query}",
                sql_query: "{escaped_sql}",
                success: {str(success).lower()},
                error: "{escaped_error}",
                timestamp: timestamp(),
                embeddings: vecf32($embedding)
            }})
            CREATE (db)-[:{relationship_type} {{timestamp: timestamp()}}]->(q)
            RETURN q.uuid as query_uuid
            """
            
            # Execute the Cypher query through Graphiti's graph driver
            try:
                result = await graph_driver.execute_query(cypher_query, embedding=embeddings)
                return True
            except Exception as cypher_error:
                print(f"Error executing Cypher query: {cypher_error}")
                return False
            
        except Exception as e:
            print(f"Error saving query memory: {e}")
            return False
        
    async def retrieve_similar_queries(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve similar queries from the memory database.

        Args:
            query: The original query to find similar queries for.
            limit: The maximum number of similar queries to retrieve.

        Returns:
            A list of similar query metadata.
        """
        try:
            database_name = self.graph_id
            
            # Find the database node
            database_node_name = f"Database {database_name}"
            node_search_config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
            node_search_config.limit = 1
            
            database_node_results = await self.graphiti_client.search_(
                query=database_node_name,
                config=node_search_config,
            )
            

            # Check if database node exists
            database_node_exists = False
            for node in database_node_results.nodes:
                if node.name == database_node_name:
                    database_node_exists = True
                    database_node_uuid = node.uuid
                    break
            if not database_node_exists:
                return []

            query_embedding = Config.EMBEDDING_MODEL.embed(query)[0]
            cypher_query = f"""
                    CALL db.idx.vector.queryNodes('Query', 'embeddings', 10, vecf32($embedding))
                        YIELD node, score
                        MATCH (db:Entity {{uuid: $database_node_uuid}})-[r]->(node)
                        RETURN node {{
                            .user_query,
                            .sql_query,
                            .success,
                            .error
                        }} AS query,
                        score
                        ORDER BY score ASC
                        LIMIT {limit}
            """
            # Execute the Cypher query through Graphiti's graph driver
            graph_driver = self.graphiti_client.driver
            try:
                records, header, _  = await graph_driver.execute_query(cypher_query, embedding=query_embedding, database_node_uuid=database_node_uuid)
                similar_queries = [record["query"] for record in records]
                return similar_queries

            except Exception as cypher_error:
                print(f"Error executing Cypher query: {cypher_error}")
                return []

        except Exception as e:
            print(f"Error retrieving similar queries: {e}")
            return []

    async def search_user_summary(self, limit: int = 5) -> str:
        """
        Search for user node summary extracts the user's personal information and general preferences.

        Args:
            query: Natural language query to search for
            limit: Maximum number of results to return
            
        Returns:
            List of user node summaries with metadata
        """
        try:
            # First, find the user node specifically
            user_node_search_config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
            user_node_search_config.limit = limit
            
            user_node_results = await self.graphiti_client.search_(
                query=f'User {self.user_id}',
                config=user_node_search_config,
            )
            
            for node in user_node_results.nodes:
                if node.name == f"User {self.user_id}":
                    user_summary = node.summary
                    return user_summary

            return ""
            
        except Exception as e:
            print(f"Error searching user node for {self.user_id}: {e}")
            return ""

    async def search_database_facts(self, query: str, limit: int = 10) -> str:
        """
        Search for database-specific facts and interaction history using database node as center.
        
        Args:
            query: Natural language query to search for database facts
            limit: Maximum number of results to return
            
        Returns:
            String containing all relevant database facts with time relevancy information
        """
        try:
            # First, find the database node to use as center for reranking
            database_node_search_config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
            database_node_search_config.limit = limit
            
            database_node_results = await self.graphiti_client.search_(
                query=f'Database {self.graph_id}',
                config=database_node_search_config,
            )

            center_node_uuid = None
            for node in database_node_results.nodes:
                if node.name == f"Database {self.graph_id}":
                    print(f'Found database node: {node.name} with UUID: {node.uuid}')
                    center_node_uuid = node.uuid
                    break

            if center_node_uuid is None:
                return ""


            reranked_results = await self.graphiti_client.search(
                query=query,
                center_node_uuid=center_node_uuid,
                num_results=limit
            )
            
            # Filter and format results for database-specific content into a single string
            database_facts_text = []
            if reranked_results and len(reranked_results) > 0:
                print(f'\nDatabase Facts Search Results for {self.graph_id}:')
                for i, result in enumerate(reranked_results, 1):
                    if result.source_node_uuid != center_node_uuid and result.target_node_uuid != center_node_uuid:
                        continue
                    
                    fact_entry = f"Fact {i}: {result.fact}"
                    
                    # Add time information if available
                    time_info = []
                    if hasattr(result, 'valid_at') and result.valid_at:
                        time_info.append(f"Valid from: {result.valid_at}")
                    if hasattr(result, 'invalid_at') and result.invalid_at:
                        time_info.append(f"Valid until: {result.invalid_at}")
                    
                    if time_info:
                        fact_entry += f" ({', '.join(time_info)})"
                    
                    database_facts_text.append(fact_entry)

            # Join all facts into a single string
            return "\n".join(database_facts_text) if database_facts_text else ""
            
        except Exception as e:
            print(f"Error searching database facts for {self.graph_id}: {e}")
            return ""

    async def search_memories(self, query: str, user_limit: int = 5, database_limit: int = 10) -> str:
        """
        Run both user summary and database facts searches concurrently for better performance.
        Also builds a comprehensive memory context string for the analysis agent.
        
        Args:
            query: Natural language query to search for database facts
            user_limit: Maximum number of results for user summary search
            database_limit: Maximum number of results for database facts search
            
        Returns:
            Dict containing user_summary, database_facts, similar_queries, and memory_context
        """
        try:
            # Run both searches concurrently using asyncio.gather
            user_summary_task = self.search_user_summary(limit=user_limit)
            database_facts_task = self.search_database_facts(query=query, limit=database_limit)
            queries_task = self.retrieve_similar_queries(query=query, limit=5)
            
            # Wait for both to complete
            user_summary, database_facts, similar_queries = await asyncio.gather(
                user_summary_task,
                database_facts_task,
                queries_task,
                return_exceptions=True
            )
            
            # Handle potential exceptions
            if isinstance(user_summary, Exception):
                user_summary = ""
            if isinstance(database_facts, Exception):
                database_facts = ""
            if isinstance(similar_queries, Exception):
                similar_queries = []
            
            # Build comprehensive memory context
            memory_context = ""
            
            if user_summary:
                memory_context += f"{self.user_id} CONTEXT (Personal preferences and information):\n{user_summary}\n\n"
            
            if database_facts:
                memory_context += f"{self.graph_id} INTERACTION HISTORY (Previous queries and learnings about this database):\n{database_facts}\n\n"

            # Add similar queries context
            if similar_queries:
                memory_context += "SIMILAR QUERIES HISTORY:\n"
                
                # Separate successful and failed queries
                successful_queries = [q for q in similar_queries if q.get('success', False)]
                failed_queries = [q for q in similar_queries if not q.get('success', False)]
                
                if successful_queries:
                    memory_context += "\nSUCCESSFUL QUERIES (Learn from these patterns):\n"
                    for i, query_data in enumerate(successful_queries, 1):
                        memory_context += f"{i}. Query: \"{query_data.get('user_query', '')}\"\n"
                        memory_context += f"   Successful SQL: {query_data.get('sql_query', '')}\n\n"
                
                if failed_queries:
                    memory_context += "FAILED QUERIES (Avoid these patterns):\n"
                    for i, query_data in enumerate(failed_queries, 1):
                        memory_context += f"{i}. Query: \"{query_data.get('user_query', '')}\"\n"
                        memory_context += f"   Failed SQL: {query_data.get('sql_query', '')}\n"
                        if query_data.get('error'):
                            memory_context += f"   Error: {query_data.get('error')}\n"
                        memory_context += f"   AVOID this approach.\n\n"
                
                memory_context += "\n"
            
            return memory_context
            
        except Exception as e:
            print(f"Error in concurrent memory search: {e}")
            return ""

    async def clean_memory(self, size: int = 10000) -> int:
        """
        Clean up the memory by removing old nodes.

        """
        driver = self.graphiti_client.driver
        query = """
                MATCH (n)
                WHERE NOT (n:Entity AND n.name = $pinned_user)
                WITH n ORDER BY coalesce(n.timestamp, 0) DESC
                SKIP $keep
                DETACH DELETE n
                """
        try:
            _, _, _stats = await driver.execute_query(
                query,
                pinned_user=f"User {self.user_id}",
                keep=int(size),
            )
            # Stats may not be available; return 0 on success path
            return 0
        except Exception as e:
            print(f"Error cleaning memory: {e}")
            return 0
    async def summarize_conversation(self, conversation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use LLM to summarize the conversation and extract database-oriented insights.
        
        Args:
            conversation: Dictionary containing conversation data
            
        Returns:
            Dict with 'database_summary' key containing direct text summary
        """
        # Format conversation for summarization
        conv_text = ""
        conv_text += f"User: {conversation.get('question', '')}\n"
        if conversation.get('generated_sql'):
            conv_text += f"SQL: {conversation['generated_sql']}\n"
        if conversation.get('error'):
            conv_text += f"Error: {conversation['error']}\n"
        if conversation.get('answer'):
            conv_text += f"Assistant: {conversation['answer']}\n"
        
        # Add success/failure status
        success_status = conversation.get('success', True)
        conv_text += f"Execution Status: {'Success' if success_status else 'Failed'}\n"
        conv_text += "\n"
        
        prompt = f"""
                Analyze this QueryWeaver question-answer interaction with database "{self.graph_id}".
                Focus exclusively on extracting graph-oriented facts about the database and its entities, relationships, and structure.

                Your task is to extract database-specific facts that imply connections between database "{self.graph_id}" and entities within the conversation:
                - Specific entities (tables, columns, data types) mentioned or discovered
                - Relationships between entities in database "{self.graph_id}"
                - Data patterns, constraints, or business rules learned about "{self.graph_id}"
                - Query patterns that work well with "{self.graph_id}" structure
                - Errors specific to "{self.graph_id}" schema or data
                - ALWAYS be explicit about database name "{self.graph_id}" in all facts

                **Critical: Be very explicit about the database name in all facts. For example: "Database {self.graph_id} contains a customers table with columns id, name, revenue" instead of "The database contains a customers table"**

                Question-Answer Interaction:
                {conv_text}

                Instructions:
                - ALWAYS be explicit about database name "{self.graph_id}" in all facts
                - Focus on graph relationships, entities, and structural facts about "{self.graph_id}"
                - Include specific table names, column names, and data relationships discovered
                - Document successful SQL patterns that work with "{self.graph_id}" structure
                - Note any schema constraints or business rules specific to "{self.graph_id}"
                - Emphasize connections between database "{self.graph_id}" and entities in the conversation
                - Use empty string if no relevant database facts are discovered
                """

        
        try:
            response = completion(
                model=self.config.COMPLETION_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            
            # Parse the direct text response (no JSON parsing needed)
            content = response.choices[0].message.content.strip()
            return {
                "database_summary": content
            }
            
        except Exception as e:
            print(f"Error in LLM summarization: {e}")
            return {
                "database_summary": ""
            }


class AzureOpenAIConfig:
    """Configuration for Azure OpenAI integration."""
    
    def __init__(self):
        # Set the model name as requested
        os.environ["MODEL_NAME"] = "gpt-4.1"
        
        self.api_key = os.getenv('AZURE_API_KEY')
        self.endpoint = os.getenv('AZURE_API_BASE') 
        self.api_version = os.getenv('AZURE_API_VERSION', '2024-02-01')
        self.model_choice = "gpt-4.1"  # Use the model name directly
        self.embedding_model = "text-embedding-ada-002"  # Use model name, not deployment
        self.small_model = os.getenv('AZURE_SMALL_MODEL', 'gpt-4o-mini')
        
        # Use model names directly instead of deployment names
        self.llm_deployment = self.model_choice
        self.small_model_deployment = self.small_model
        self.embedding_deployment = self.embedding_model
        
        # Embedding endpoint (can be same or different from main endpoint)
        self.embedding_endpoint = os.getenv('AZURE_EMBEDDING_ENDPOINT', self.endpoint)


def get_azure_openai_clients():
    """Configure and return Azure OpenAI clients for Graphiti."""
    config = AzureOpenAIConfig()
    
    # Validate required configuration
    if not config.endpoint:
        raise ValueError("AZURE_API_BASE environment variable is required")
    if not config.api_key:
        raise ValueError("AZURE_API_KEY environment variable is required")
    
    # Create separate Azure OpenAI clients for different services
    llm_client_azure = AsyncAzureOpenAI(
        api_key=config.api_key,
        api_version=config.api_version,
        azure_endpoint=config.endpoint,
    )

    embedding_client_azure = AsyncAzureOpenAI(
        api_key=config.api_key,
        api_version=config.api_version,
        azure_endpoint=config.embedding_endpoint,
    )

    return llm_client_azure, embedding_client_azure, config

def create_graphiti_client(falkor_driver: FalkorDriver) -> Graphiti:
    """Create a Graphiti client configured with Azure OpenAI."""
    # Get Azure OpenAI clients and config
    llm_client_azure, embedding_client_azure, config = get_azure_openai_clients()

    # Create LLM Config with Azure deployment names
    azure_llm_config = LLMConfig(
        small_model=config.small_model_deployment,
        model=config.llm_deployment,
    )

    # Initialize Graphiti with Azure OpenAI clients
    return Graphiti(
        graph_driver=falkor_driver,
        llm_client=OpenAIClient(config=azure_llm_config, client=llm_client_azure),
        embedder=OpenAIEmbedder(
            config=OpenAIEmbedderConfig(embedding_model=config.embedding_deployment),
            client=embedding_client_azure,
        ),
        cross_encoder=OpenAIRerankerClient(
            config=LLMConfig(
                model=azure_llm_config.small_model  # Use small model for reranking
            ),
            client=llm_client_azure,
        ),
    )

