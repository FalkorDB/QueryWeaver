# Agents Module

This module contains various AI agents for the text2sql application. Each agent is responsible for a specific task in the query processing pipeline.

## Agents

### AnalysisAgent (`analysis_agent.py`)
- **Purpose**: Analyzes user queries and generates database analysis
- **Key Method**: `get_analysis()` - Analyzes user queries against database schema
- **Features**: Schema formatting, prompt building, conversation history tracking

### RelevancyAgent (`relevancy_agent.py`)
- **Purpose**: Determines if queries are relevant to the database schema
- **Key Method**: `get_answer()` - Assesses query relevancy against database description
- **Features**: Topic classification (On-topic, Off-topic, Inappropriate)

### FollowUpAgent (`follow_up_agent.py`)
- **Purpose**: Handles follow-up questions and conversational context
- **Key Method**: `get_answer()` - Processes follow-up questions using conversation history
- **Features**: Context awareness, data availability assessment

### TaxonomyAgent (`taxonomy_agent.py`)
- **Purpose**: Provides taxonomy classification and clarification for SQL queries
- **Key Method**: `get_answer()` - Generates clarification questions for SQL queries
- **Features**: WHERE clause analysis, user-friendly clarifications

### ResponseFormatterAgent (`response_formatter_agent.py`)
- **Purpose**: Formats SQL query results into user-readable responses
- **Key Method**: `format_response()` - Converts raw SQL results to natural language
- **Features**: Result formatting, operation type detection, user-friendly explanations

## Utilities

### utils.py
- **parse_response()**: Shared utility function for parsing JSON responses from AI models
- Used by multiple agents for consistent response parsing

## Usage

```python
from api.agents import AnalysisAgent, RelevancyAgent, ResponseFormatterAgent

# Initialize agents
analysis_agent = AnalysisAgent(queries_history, result_history)
relevancy_agent = RelevancyAgent(queries_history, result_history)
formatter_agent = ResponseFormatterAgent()

# Use agents
analysis = analysis_agent.get_analysis(query, tables, db_description)
relevancy = relevancy_agent.get_answer(question, database_desc)
response = formatter_agent.format_response(query, sql, results, db_description)
```

## Architecture

Each agent follows a consistent pattern:
1. **Initialization**: Set up with necessary context (history, configuration)
2. **Main Method**: Primary interface for the agent's functionality
3. **Helper Methods**: Private methods for internal processing
4. **Prompt Templates**: Stored as module-level constants for easy maintenance
5. **LLM Integration**: Uses litellm for AI model interactions

This modular structure improves:
- **Maintainability**: Each agent is self-contained
- **Testability**: Agents can be tested independently
- **Reusability**: Agents can be used in different contexts
- **Scalability**: New agents can be added without affecting existing ones
