""" Extensions for the text2sql library """
import os
from falkordb import FalkorDB

# Connect to FalkorDB
url = os.getenv("FALKORDB_URL", None)
if url is None:
    try:
        db = FalkorDB(host='localhost', port=6379)
    except Exception as e:
        raise Exception(f"Failed to connect to FalkorDB: {e}")
else:
    db = FalkorDB.from_url(os.getenv("FALKORDB_URL"))
