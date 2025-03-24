import json
from litellm import completion, embedding
from text2sql.graph import find, find_connecting_tables

class base_agent:
    def __init__(self, args):
        pass


class aiming_agent(base_agent):
    def __init__(self, args):
        super().__init__(args)  # Call parent class constructor
        
        # Store arguments as instance variables
        self.args = args
        self.result = args.get('result')
        self.queries_history = args.get('queries_history')
        self.db_description = args.get('db_description')
        self.graph = args.get('graph')
        self.Config = args.get('Config')
        
        # Initialize class attributes
        self.connection_tables = None
        
    def find_connections(self):
        """Find connections between tables based on user query."""
        # Check if we have the necessary data to proceed
        if not (self.queries_history and self.result):
            return None, None
            
        user_content = json.dumps({
            "schema": self.result,
            "previous_queries": self.queries_history[:-1],
            "user_query": self.queries_history[-1]
        })
        
        # Using the imported completion function
        completion_result = completion(
            model=self.Config.COMPLETION_MODEL,
            messages=[
                {
                    "content": self.Config.Text_To_tables_PROMPT.format(db_description=self.db_description),
                    "role": "system"
                },
                {
                    "content": user_content,
                    "role": "user"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0
        )
        
        focus_tables = completion_result.choices[0].message.content
        table_list = json.loads(focus_tables)
        
        # Using the imported find_connecting_tables function
        self.result, self.connection_tables = find_connecting_tables(self.graph, table_list, self.result)
        return self.result, self.connection_tables