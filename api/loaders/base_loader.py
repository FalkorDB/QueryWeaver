from abc import ABC
from typing import Tuple


class BaseLoader(ABC):

    @staticmethod
    def load(_graph_id: str, _data) -> Tuple[bool, str]:
        """
        Load the graph data into the database.
        This method must be implemented by any subclass.
        """
        return False, "Not implemented"
