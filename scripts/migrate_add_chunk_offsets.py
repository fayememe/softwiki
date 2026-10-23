from softwiki.config import get_db_url
from softwiki.source_store.db import init_tables

init_tables()
print(f"chunk offset columns ensured: {get_db_url()}")
