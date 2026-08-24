# Text2SQL Accuracy Improvements

## Overview

This document describes the Text2SQL improvements implemented for QueryWeaver based on comprehensive research of 25 academic papers on Text2SQL systems, with focus on Spider 1.0 and Spider 2.0 benchmark performance.

## Research Foundation

Our improvements are based on state-of-the-art research:

### Top-Performing Systems (Spider 1.0)
1. **DAIL-SQL** (86.6%) - Schema-aware prompting with self-consistency
2. **DIN-SQL** (85.3%) - Decomposed in-context learning with self-correction
3. **C3** (82.3%) - Chain-of-chains multi-step reasoning
4. **RESDSQL** (79.9%) - Ranking-enhanced schema linking
5. **Graphix-T5** (77.6%) - Graph-based schema linking

### Top-Performing Systems (Spider 2.0)
1. **DSR-SQL** (63.8%) - Multi-step decomposition and self-refinement
2. **ReFoRCE** (62.9%) - Self-refinement with feedback loops
3. **AutoLink** (54.8%) - Enhanced schema linking

## Implemented Improvements

### Phase 1: Enhanced Prompting Strategies ✅

**Objective:** Improve SQL generation accuracy through better prompts and chain-of-thought reasoning.

**Changes:**

#### 1.1 Enhanced Text_To_SQL_PROMPT
- **Location:** `api/config.py`
- **Improvements:**
  - Structured instructions with step-by-step reasoning
  - Quality checklist for self-validation
  - Explicit rules for JOINs and special character handling
  - Better handling of edge cases
  - Clear output format expectations

**Key Features:**
```python
# Before generating SQL, the model now follows:
1. Schema Understanding
2. Query Intent Analysis (entities, aggregations, filters, sorting)
3. SQL Generation Rules (JOINs, aliases, WHERE clauses)
4. Special Characters Handling (auto-quoting)
5. Value Handling (exact values, TBD placeholders)
6. Quality Checklist validation
```

#### 1.2 Improved FIND_SYSTEM_PROMPT
- **Location:** `api/config.py`
- **Improvements:**
  - Schema linking strategies
  - Relevance ranking guidelines
  - Entity identification and relationship awareness
  - Example reasoning patterns

**Key Features:**
```python
# Schema linking now includes:
1. Relevance Ranking - ordered by importance
2. Generic Descriptions - searchable, no specific values
3. Entity Identification - direct and implied
4. Relationship Awareness - linking tables
5. Column Specificity - for aggregations, filters, temporal
6. Limit Output - max 5 tables, 5 columns
```

#### 1.3 Chain-of-Thought Analysis Agent
- **Location:** `api/agents/analysis_agent.py`
- **Improvements:**
  - 6-step reasoning process
  - Explicit query decomposition
  - Join path planning
  - SQL construction validation

**Reasoning Steps:**
```
STEP 1: Query Understanding
  - What is being asked?
  - Type of SQL operation needed

STEP 2: Schema Mapping
  - Which tables/columns needed?
  - All required elements present?

STEP 3: Join Path Planning
  - Multi-table join path
  - Foreign key relationships only

STEP 4: Condition Analysis
  - Filters, aggregations, grouping, ordering

STEP 5: SQL Construction
  - Build query clause by clause

STEP 6: Validation
  - Verify against intent and schema
```

#### 1.4 Few-Shot SQL Examples
- **Location:** `api/config.py`
- **Feature:** `Config.SQL_EXAMPLES`
- **Improvements:**
  - Example patterns for common query types
  - Demonstrates best practices
  - Shows reasoning process

**Example Types:**
1. Simple Selection with WHERE
2. JOIN with Aggregation
3. Subquery for Comparison
4. Multiple JOINs
5. Temporal Filtering

### Phase 2: Schema Linking & Retrieval Improvements ✅

**Objective:** Improve table/column selection accuracy through ranking and pruning.

**Changes:**

#### 2.1 Relevance Scoring System
- **Location:** `api/graph.py`
- **Function:** `_calculate_relevance_score()`
- **Improvements:**
  - Multi-source ranking
  - Score-based prioritization
  - Configurable thresholds

**Scoring Strategy:**
```python
{
    'table': 1.0,      # Direct table name match - highest priority
    'column': 0.9,     # Matched via specific columns - very relevant
    'sphere': 0.7,     # Related tables in sphere of influence
    'connection': 0.5  # Bridging/connecting tables - support role
}
```

#### 2.2 Schema Pruning
- **Location:** `api/graph.py` and `api/config.py`
- **Configuration:**
  - `MAX_TABLES_IN_CONTEXT = 15` (prevents context overflow)
  - `MIN_RELEVANCE_SCORE = 0.3` (filters low-relevance tables)

**Benefits:**
- Reduces noise in SQL generation
- Prevents context window overflow
- Focuses LLM on most relevant schema elements
- Improves accuracy for large schemas

#### 2.3 Enhanced find() Function
- **Location:** `api/graph.py`
- **Improvements:**
  - Multi-stage schema linking
  - Source tagging for ranking
  - Comprehensive logging

**Pipeline:**
```
1. LLM-based description generation
2. Embedding-based retrieval with scoring
3. Relationship expansion (sphere of influence)
4. Connection path discovery
5. Relevance ranking and pruning
```

### Phase 3: Query Decomposition & Multi-Step Reasoning ✅

**Objective:** Handle complex queries through decomposition (DIN-SQL approach).

**Changes:**

#### 3.1 DecompositionAgent
- **Location:** `api/agents/decomposition_agent.py`
- **Purpose:** Break down complex queries into subtasks
- **Features:**
  - Complexity detection
  - Subtask identification
  - Dependency tracking
  - Query type classification

**Query Types:**
```python
- simple_select: Basic SELECT with WHERE
- aggregation: COUNT, SUM, AVG, etc.
- join: Multiple tables
- nested: Subqueries needed
- ranking: TOP N, ORDER BY with LIMIT
- temporal: Date/time comparisons
- multi_agg: Multiple aggregation levels
```

**Complexity Indicators:**
- Multiple aggregations
- Nested conditions
- Multiple entity references
- Temporal comparisons
- Ranking or top-N queries
- Set operations
- Subqueries or CTEs

#### 3.2 Integration with Pipeline
- **Location:** `api/core/text2sql.py`
- **Configuration:**
  - `ENABLE_QUERY_DECOMPOSITION = True` (can be disabled)
  - `DECOMPOSITION_COMPLEXITY_THRESHOLD = "medium"`

**Pipeline Flow:**
```
1. Relevancy check
2. Schema linking
3. [NEW] Query decomposition (if complex)
4. SQL generation (with decomposition context)
5. Execution
```

## Configuration Options

### api/config.py Settings

```python
# Memory and Context
SHORT_MEMORY_LENGTH = 5  # Max previous queries to consider

# Schema Linking (Phase 2)
MAX_TABLES_IN_CONTEXT = 15  # Max tables for SQL generation
MIN_RELEVANCE_SCORE = 0.3   # Min score for table inclusion

# Query Decomposition (Phase 3)
ENABLE_QUERY_DECOMPOSITION = True  # Enable/disable decomposition
DECOMPOSITION_COMPLEXITY_THRESHOLD = "medium"  # low, medium, high
```

## Usage Examples

### Example 1: Simple Query (No Decomposition)

**Input:**
```
"Show all employees in the Sales department"
```

**Pipeline:**
1. Schema linking finds `employees` table
2. Decomposition agent: NOT complex
3. Analysis agent generates direct SQL
4. Result: `SELECT * FROM employees WHERE department = 'Sales'`

### Example 2: Complex Query (With Decomposition)

**Input:**
```
"Show customers who spent more than the average last year"
```

**Pipeline:**
1. Schema linking finds `customers`, `orders` tables
2. Decomposition agent: COMPLEX (nested, temporal)
3. Subtasks identified:
   - Step 1: Calculate average spending
   - Step 2: Filter customers above average
   - Step 3: Apply temporal filter
4. Analysis agent generates with context
5. Result:
```sql
SELECT c.*
FROM customers c
WHERE c.total_spent > (
    SELECT AVG(total_spent)
    FROM customers
    WHERE last_order_date >= DATE_TRUNC('year', CURRENT_DATE - INTERVAL '1 year')
)
AND c.last_order_date >= DATE_TRUNC('year', CURRENT_DATE - INTERVAL '1 year')
```

### Example 3: Schema Pruning in Action

**Scenario:** Large database with 50+ tables

**Input:**
```
"How many orders were placed last month?"
```

**Pipeline:**
1. Schema linking retrieves 20 potentially relevant tables
2. Ranking scores applied:
   - `orders` table: 1.0 (direct match)
   - `order_items`: 0.9 (column match)
   - `customers`: 0.7 (sphere, related)
   - Various bridge tables: 0.5
3. Pruning applied: Keep top 15 with score ≥ 0.3
4. SQL generation uses focused schema
5. Result: Faster, more accurate generation

## Expected Performance Improvements

### Spider 1.0 Benchmark

Based on research and improvements:

| Component | Expected Gain | Reasoning |
|-----------|--------------|-----------|
| Enhanced Prompting | +5-8% | Better schema understanding, clearer instructions |
| Schema Linking | +3-5% | Improved table selection, reduced noise |
| Query Decomposition | +4-6% | Better handling of complex queries |
| **Combined** | **12-19%** | Synergistic effects |

**Baseline:** 70-75% execution accuracy (typical prompt-based systems)
**Target:** 82-94% execution accuracy
**Best Research:** DAIL-SQL at 86.6%

### Spider 2.0 Benchmark

| Component | Expected Gain | Reasoning |
|-----------|--------------|-----------|
| Enhanced Prompting | +4-6% | Better enterprise query understanding |
| Schema Linking | +2-4% | Critical for complex schemas |
| Query Decomposition | +4-7% | Essential for multi-step workflows |
| **Combined** | **10-17%** | Lower baseline, higher complexity |

**Baseline:** 35-40% (enterprise workflows)
**Target:** 45-57%
**Best Research:** DSR-SQL at 63.8% (with self-refinement)

## Future Improvements (Not Yet Implemented)

### Phase 4: Self-Correction & Execution Feedback
- SQL execution validation
- Self-correction loops for failed queries
- Execution feedback refinement
- Error taxonomy for systematic correction

**Expected Impact:** +6-10% (based on ReFoRCE, DSR-SQL research)

### Phase 5: Self-Consistency & Candidate Generation
- Multiple SQL candidate generation
- Self-consistency voting (DAIL-SQL approach)
- Query ranking by confidence
- Cross-validation

**Expected Impact:** +3-5% (based on DAIL-SQL self-consistency gains)

### Phase 6: Memory & Context Enhancement
- Enhanced memory context usage
- Successful query pattern learning
- Failed query pattern avoidance
- Better conversation context integration

**Expected Impact:** +2-4% (incremental improvements)

## Testing & Validation

### Unit Testing
```bash
# Test individual components
pipenv run pytest tests/ -k "test_decomposition" -v
pipenv run pytest tests/ -k "test_schema_linking" -v
pipenv run pytest tests/ -k "test_analysis_agent" -v
```

### Integration Testing
```bash
# Test full pipeline
pipenv run pytest tests/e2e/ -v
```

### Benchmark Testing (Recommended for Future Implementation)

To properly validate these improvements, benchmarking against Spider datasets is recommended:

```bash
# Example commands for future benchmark implementation
# Note: Benchmark scripts need to be implemented separately
# These are examples of the recommended testing approach

# Run against Spider 1.0 dataset
python benchmark_spider1.py --config improved

# Run against Spider 2.0 dataset
python benchmark_spider2.py --config improved
```

**Note:** The benchmark scripts referenced above are examples and need to be implemented separately to test against Spider 1.0 and Spider 2.0 datasets. The Spider benchmarks are available at: https://yale-lily.github.io/spider

## Troubleshooting

### Common Issues

#### 1. Decomposition Too Aggressive
**Symptom:** Simple queries being decomposed unnecessarily
**Solution:**
```python
# Adjust threshold in api/config.py
DECOMPOSITION_COMPLEXITY_THRESHOLD = "high"  # or disable
ENABLE_QUERY_DECOMPOSITION = False
```

#### 2. Schema Pruning Too Strict
**Symptom:** Missing required tables in complex queries
**Solution:**
```python
# Increase limits in api/config.py
MAX_TABLES_IN_CONTEXT = 20
MIN_RELEVANCE_SCORE = 0.2
```

#### 3. Performance Degradation
**Symptom:** Slower query processing
**Solution:**
- Decomposition adds one LLM call for complex queries
- Can be disabled for simple use cases
- Consider caching decomposition results

## References

1. Gao et al. (2023) - DAIL-SQL: Text-to-SQL Empowered by LLMs
2. Pourreza & Rafiei (2023) - DIN-SQL: Decomposed In-Context Learning
3. Sun et al. (2023) - C3: Chain-of-Chains for Text-to-SQL
4. Li et al. (2023) - RESDSQL: Decoupling Schema Linking
5. Gao et al. (2024) - Survey of Text-to-SQL in Era of LLMs
6. Liu et al. (2025) - RSL-SQL: Robust Schema Linking
7. Chen et al. (2025) - ReFoRCE: Refinement via Feedback
8. Zhang et al. (2025) - DSR-SQL: Multi-step Refinement

## Branch Information

Each improvement phase is implemented in a separate branch:

1. **feature/enhanced-prompting-strategies** - Phase 1 improvements
2. **feature/enhanced-schema-linking** - Phase 2 improvements
3. **feature/query-decomposition** - Phase 3 improvements

All branches are based on `staging` and can be merged independently or together.

## Contributing

When adding new improvements:
1. Create a new branch from `staging`
2. Document changes in this file
3. Add configuration options to `api/config.py`
4. Include tests for new functionality
5. Update performance benchmarks

## License

See main repository LICENSE file.
