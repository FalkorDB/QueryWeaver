"""
Graphiti integration for QueryWeaver memory component.
Saves summarized conversations with user and database nodes.
"""
# pylint: disable=all
import asyncio
import logging
import os
import uuid
from typing import List, Dict, Any, Optional, Tuple
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


def extract_embedding_model_name(full_model_name: str) -> str:
    """
    Extract just the model name without provider prefix for Graphiti.
    
    Args:
        full_model_name: Model name that may include provider prefix (e.g., "azure/text-embedding-ada-002")
        
    Returns:
        Model name without prefix (e.g., "text-embedding-ada-002")
    """
    if "/" in full_model_name:
        return full_model_name.split("/", 1)[1]  # Remove provider prefix
    else:
        return full_model_name


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


    @classmethod
    async def create(cls, user_id: str, graph_id: str, use_direct_entities: bool = True) -> "MemoryTool":
        """Async factory to construct and initialize the tool."""
        self = cls(user_id, graph_id)

        await self._ensure_entity_nodes_direct(user_id, graph_id)


        vector_size = Config.EMBEDDING_MODEL.get_vector_size()
        driver = self.graphiti_client.driver
        await driver.execute_query(f"CREATE VECTOR INDEX FOR (p:Query) ON (p.embeddings) OPTIONS {{dimension:{vector_size}, similarityFunction:'euclidean'}}")

        return self

    async def _ensure_entity_nodes_direct(self, user_id: str, database_name: str) -> bool:
        """
        Ensure user and database entity nodes exist using direct Cypher queries.
        This function creates Entity nodes similar to what Graphiti does but with hardcoded Cypher.
        """
        try:
            graph_driver = self.graphiti_client.driver
            
            # Check if user entity node already exists
            user_node_name = f"{user_id}"
            check_user_query = """
                MATCH (n:Entity {name: $name})
                RETURN n.uuid AS uuid
                LIMIT 1
            """
            user_check_result = await graph_driver.execute_query(check_user_query, name=user_node_name)
            
            if not user_check_result[0]:  # If no records found, create user node
                user_uuid = str(uuid.uuid4())
                user_name_embedding = Config.EMBEDDING_MODEL.embed(user_node_name)[0]
                
                user_node_data = {
                    'uuid': user_uuid,
                    'name': user_node_name,
                    'group_id': '\\_',
                    'created_at': datetime.now().isoformat(),
                    'summary': 'The User is using QueryWeaver',
                    'name_embedding': user_name_embedding
                }
                
                # Execute Cypher query for user entity node
                user_cypher = """
                    MERGE (n:Entity {uuid: $node.uuid})
                    SET n = $node
                    SET n.timestamp = timestamp()
                    WITH n, $node AS node
                    SET n.name_embedding = vecf32(node.name_embedding)
                    RETURN n.uuid AS uuid
                """
                
                await graph_driver.execute_query(user_cypher, node=user_node_data)
                logging.info("Created user entity node with UUID: %s", user_uuid)
            else:
                logging.info("User entity node already exists")
            
            # Check if database entity node already exists
            database_node_name = f"Database {database_name}"
            check_database_query = """
                MATCH (n:Entity {name: $name})
                RETURN n.uuid AS uuid
                LIMIT 1
            """
            database_check_result = await graph_driver.execute_query(check_database_query, name=database_node_name)
            
            if not database_check_result[0]:  # If no records found, create database node
                database_uuid = str(uuid.uuid4())
                database_name_embedding = Config.EMBEDDING_MODEL.embed(database_node_name)[0]
                
                database_node_data = {
                    'uuid': database_uuid,
                    'name': database_node_name,
                    'group_id': '\\_',
                    'created_at': datetime.now().isoformat(),
                    'summary': f'Database {database_name} available for querying by user {user_id}',
                    'name_embedding': database_name_embedding
                }
                
                # Execute Cypher query for database entity node
                database_cypher = """
                    MERGE (n:Entity {uuid: $node.uuid})
                    SET n = $node
                    SET n.timestamp = timestamp()
                    WITH n, $node AS node
                    SET n.name_embedding = vecf32(node.name_embedding)
                    RETURN n.uuid AS uuid
                """
                
                await graph_driver.execute_query(database_cypher, node=database_node_data)
                logging.info("Created database entity node: %s with UUID: %s", database_node_name, database_uuid)
            else:
                logging.info("Database entity node already exists: %s", database_node_name)
            
            # Create HAS_DATABASE relationship between user and database entities
            try:
                relationship_query = """
                    MATCH (user:Entity {name: $user_name})
                    MATCH (db:Entity {name: $database_name})
                    MERGE (user)-[r:HAS_DATABASE]->(db)
                    RETURN r
                """
                
                await graph_driver.execute_query(
                    relationship_query, 
                    user_name=user_node_name,
                    database_name=database_node_name
                )
                logging.info("Created HAS_DATABASE relationship between user and %s database", database_node_name)
            except Exception as rel_error:
                logging.error("Error creating HAS_DATABASE relationship: %s", rel_error)
                # Don't fail the entire function if relationship creation fails
            
            return True
            
        except Exception as e:
            logging.error("Error creating entity nodes directly: %s", e)
            return False

    async def update_user_information(self, conversation: Dict[str, Any], history: Tuple[List[str], List[str]]) -> bool:
        driver = self.graphiti_client.driver
        query = """
            MATCH (u:Entity {name: $user_id})
            RETURN u.summary AS summary
        """
        summary_result, __, _ = await driver.execute_query(query, user_id=self.user_id)
        summary = summary_result[0].get("summary", "") if summary_result else ""
        # Format conversation for summarization
        conv_text = ""
        conv_text += f"User: {conversation.get('question', '')}\n"
        if conversation.get('generated_sql'):
            conv_text += f"SQL: {conversation['generated_sql']}\n"
        if conversation.get('error'):
            conv_text += f"Error: {conversation['error']}\n"
        if conversation.get('answer'):
            conv_text += f"Assistant: {conversation['answer']}\n"
        prompt = f"""
                You are updating the personal memory of user.
                ### Inputs
                1. Existing user summary (overall + personal info):
                {summary}

                2. Latest Q&A conversational memory:
                {conv_text}

                ### Task
                - Produce a new user summary of his overall preferences and his personal information.
                - *Important*: Ensure that the summary is contain any personal statements or preferences expressed by the user.
                - Preserve existing personal information, preferences, and tendencies from the old summary.
                - Integrate any **new insights** about the user’s interests, behaviors, or database usage patterns from the latest memory.
                - If new info refines or corrects older info, update accordingly.
                - Focus only on **overall and personal information** — do not include temporary query details.
                - Write in **factual third-person style**, suitable for storage as a user node in a graph.
                - Try to explicitly divide overall summary, usage preferences and personal information.

                ### Output
                An updated user summary.
                """
        try:

            if len(history[1]) == 0:
                messages = [{"role": "user", "content": prompt}]
            else:
                messages = []
                for query, result in zip(history[0], history[1]):
                    messages.append({"role": "user", "content": query})
                    messages.append({"role": "assistant", "content": result})
            messages.append({"role": "user", "content": prompt})
            response = completion(
                model=Config.COMPLETION_MODEL,
                messages=messages,
                temperature=0.1
            )
            
            # Parse the direct text response (no JSON parsing needed)
            content = response.choices[0].message.content.strip()
            query = """
            MATCH (u:Entity {name: $user_id})
            SET u.summary = $summary
            RETURN u.summary AS summary
            """
            await driver.execute_query(query, user_id=self.user_id, summary=content)
            return True
        except Exception as e:
            return False

    async def add_new_memory(self, conversation: Dict[str, Any], history: Tuple[List[str], List[str]]) -> bool:
        # Use LLM to analyze and summarize the conversation with focus on graph-oriented database facts
        analysis = await self.summarize_conversation(conversation, history)
        user_id = self.user_id
        database_name = self.graph_id

        # Extract summaries
        database_summary = analysis.get("database_summary", "")
        
        try:
            # Run episode addition and user information update concurrently
            add_episode_task = self.graphiti_client.add_episode(
                name=f"Database_Facts_{user_id}_{database_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                episode_body=f"Database {database_name}:\n{database_summary}",
                source=EpisodeType.message,
                reference_time=datetime.now(),
                source_description=f"Graph-oriented facts about Database: {database_name} from User: {user_id} interaction"
            )
            
            update_user_task = self.update_user_information(conversation, history=history)
            
            # Wait for both operations to complete
            await asyncio.gather(add_episode_task, update_user_task)

        except Exception as e:
            logging.error("Error adding new memory episodes: %s", e)
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
            database_node_name = f"Database {database_name}"
            graph_driver = self.graphiti_client.driver
            
            # Find the database node using direct Cypher query
            find_database_query = """
                MATCH (n:Entity {name: $name})
                RETURN n.uuid AS uuid
                LIMIT 1
            """
            
            database_result = await graph_driver.execute_query(find_database_query, name=database_node_name)
            
            # Check if database node exists
            if not database_result[0]:  # If no records found
                logging.error("Database entity node %s not found", database_node_name)
                return False
            
            database_node_uuid = database_result[0][0]['uuid']

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
                logging.info("Query with same user_query and sql_query already exists, skipping creation")
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
                logging.error("Error executing Cypher query: %s", cypher_error)
                return False
            
        except Exception as e:
            logging.error("Error saving query memory: %s", e)
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
                logging.error("Error executing Cypher query: %s", cypher_error)
                return []

        except Exception as e:
            logging.error("Error retrieving similar queries: %s", e)
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
            driver = self.graphiti_client.driver
            query = """
                    MATCH (e:Entity {name: $name})
                    RETURN e.summary AS summary
                    """
            result, __, _ = await driver.execute_query(query, name=self.user_id)

            if result:
                user_summary = result[0].get("summary", "")
                return user_summary

            return ""
            
        except Exception as e:
            logging.error("Error searching user node: %s", e)
            return ""
        
    async def extract_episode_from_rel(self, rel_result):
        """
        Extracts the content of episodes associated with a given relationship result.

        Args:
            rel_result: An object containing an 'episodes' attribute, which is a list of episode UUIDs.

        Returns:
            List of episode content strings corresponding to the provided episode UUIDs.
        """
        driver = self.graphiti_client.driver
        query = """
                MATCH (e:Episodic {uuid: $uuid})
                RETURN e.content AS content
                """
        episodes_uuid = rel_result.episodes

        episode_contents = []
        for episode_uuid in episodes_uuid:
            episode_content, _, _ = await driver.execute_query(query, uuid=episode_uuid)
            if episode_content:
                content = episode_content[0].get("content")
                episode_contents.append(content)

        return episode_contents

    async def search_database_facts(self, query: str, limit: int = 5, episode_limit: int = 3) -> str:
        """
        Search for database-specific facts and interaction history using database node as center.
        
        Args:
            query: Natural language query to search for database facts
            limit: Maximum number of results to return
            
        Returns:
            String containing all relevant database facts with time relevancy information
        """
        try:
            driver = self.graphiti_client.driver
            query = """
                    MATCH (e:Entity {name: $name})
                    RETURN e.uuid AS uuid
                    """
            result, __, _ = await driver.execute_query(query, name=f"Database {self.graph_id}")
            center_node_uuid = result[0].get("uuid", "")
            reranked_results = await self.graphiti_client.search(
                query=query,
                center_node_uuid=center_node_uuid,
                num_results=limit
            )
            
            # Filter and format results for database-specific content into a single string
            database_facts_text = []
            episodes_contents = []
            if reranked_results and len(reranked_results) > 0:
                logging.info("Previous session and facts for %s:", self.graph_id)
                for i, result in enumerate(reranked_results, 1):
                    if result.source_node_uuid != center_node_uuid and result.target_node_uuid != center_node_uuid:
                        continue
                    if len(episodes_contents) < episode_limit:
                        episodes_content = await self.extract_episode_from_rel(result)
                        episodes_contents.extend(episodes_content)
                    fact_entry = f"{result.fact}"
                    
                    # Add time information if available
                    time_info = []
                    if hasattr(result, 'valid_at') and result.valid_at:
                        time_info.append(f"Valid from: {result.valid_at}")
                    if hasattr(result, 'invalid_at') and result.invalid_at:
                        time_info.append(f"Valid until: {result.invalid_at}")
                    
                    if time_info:
                        fact_entry += f" ({', '.join(time_info)})"
                    
                    database_facts_text.append(fact_entry)
            facts = "\n".join(database_facts_text) if database_facts_text else ""
            episodes = "\n".join(episodes_contents) if episodes_contents else ""
            database_context = "Previous sessions:\n" + episodes + "\n\nFacts:\n" + facts
            # Join all facts into a single string
            return database_context

        except Exception as e:
            logging.error("Error searching database facts for %s: %s", self.graph_id, e)
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
                memory_context += f"(Personal preferences and information):\n{user_summary}\n\n"
            
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
            logging.error("Error in concurrent memory search: %s", e)
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
            logging.error("Error cleaning memory: %s", e)
            return 0

    async def summarize_conversation(self, conversation: Dict[str, Any], history: List[Dict[str, Any]]) -> Dict[str, Any]:
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
                Rewrite the following QueryWeaver question-answer interaction into a 
                database-oriented conversational summary for database "{self.graph_id}".  

                ### Requirements
                - Always explicitly say: "{self.graph_id} database" (not just "{self.graph_id}").  
                - Always include the user id "{self.user_id}" in the summary.  
                - Capture the Q&A flow in natural, intuitive language (not just facts).
                - Include the full **relevant query results** in the output, summarizing key fields if necessary. 
                - Keep it concise (2–6 sentences).  
                - Emphasize schema, entities, and queries relevant to "{self.graph_id} database".  
                - If no relevant database context exists, return an empty string.  

                ### Input
                {conv_text}

                ### Output
                A conversational database-oriented summary mentioning both "{self.user_id}" and "{self.graph_id} database".
                """
        
        try:

            if len(history[1]) == 0:
                messages = [{"role": "user", "content": prompt}]
            else:
                messages = []
                for query, result in zip(history[0], history[1]):
                    messages.append({"role": "user", "content": query})
                    messages.append({"role": "assistant", "content": result})
            messages.append({"role": "user", "content": prompt})
            response = completion(
                model=Config.COMPLETION_MODEL,
                messages=messages,
                temperature=0.1
            )
            
            # Parse the direct text response (no JSON parsing needed)
            content = response.choices[0].message.content.strip()
            return {
                "database_summary": content
            }
            
        except Exception as e:
            logging.error("Error in LLM summarization: %s", e)
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
        
        # Extract just the model name without provider prefix for Graphiti
        self.embedding_model = extract_embedding_model_name(Config.EMBEDDING_MODEL_NAME)
            
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
    # Initialize Graphiti with Azure OpenAI clients
    if Config.AZURE_FLAG:
        # Get Azure OpenAI clients and config
        llm_client_azure, embedding_client_azure, config = get_azure_openai_clients()

        # Create LLM Config with Azure deployment names
        azure_llm_config = LLMConfig(
            small_model=config.small_model_deployment,
            model=config.llm_deployment,
        )

        graphiti_client = Graphiti(
            graph_driver=falkor_driver,
            llm_client=OpenAIClient(config=azure_llm_config, client=llm_client_azure),
            embedder=OpenAIEmbedder(
                config=OpenAIEmbedderConfig(
                    embedding_model=config.embedding_deployment,
                    embedding_dim=1536
                ),
                client=embedding_client_azure,
            ),
            cross_encoder=OpenAIRerankerClient(
                config=LLMConfig(
                    model=azure_llm_config.small_model  # Use small model for reranking
                ),
                client=llm_client_azure,
            ),
        )
    else:  # Fallback to default OpenAI config but use Config's embedding model
        # Extract just the model name without provider prefix for Graphiti
        embedding_model_name = extract_embedding_model_name(Config.EMBEDDING_MODEL_NAME)
            
        graphiti_client = Graphiti(
            graph_driver=falkor_driver,
            embedder=OpenAIEmbedder(
                config=OpenAIEmbedderConfig(
                    embedding_model=embedding_model_name,
                    embedding_dim=1536
                )
            ),
        )

    return graphiti_client

