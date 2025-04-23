""" Extensions for the text2sql library """
import os
from falkordb import FalkorDB

# Connect to FalkorDB
db = FalkorDB(host='localhost', port=6379)

# db = FalkorDB(host=os.getenv('FALKOR_HOST'), port=os.getenv('FALKOR_PORT'), username=os.getenv('FALKOR_USERNAME'), password=os.getenv('FALKOR_PASSWORD'))
