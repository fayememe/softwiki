import os
import yaml
from softwiki.source_store.db import Base, get_engine, SessionLocal
from softwiki.source_store.models import SourceConfig
from softwiki.source_store.document_repo import DocumentRepository
from softwiki.config import get_config_path

def main():
    print("Initializing Database...")
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")

    # Seed predefined sources from active workspace sources.yaml
    sources_yaml_path = get_config_path("sources.yaml")
    if os.path.exists(sources_yaml_path):
        print(f"Seeding sources from {sources_yaml_path}...")
        with open(sources_yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            sources = data.get("sources", [])
        
        db = SessionLocal()
        try:
            for s in sources:
                source_obj = SourceConfig(
                    id=s.get("id"),
                    name=s.get("name"),
                    type=s.get("type"),
                    url=s.get("url"),
                    trust_level=s.get("trust_level"),
                    source_country=s.get("source_country"),
                    language=s.get("language")
                )
                DocumentRepository.save_source_config(db, source_obj)
                print(f"Seeded source: {s.get('id')} ({s.get('name')})")
            db.commit()
        finally:
            db.close()
        print("Database seeded successfully.")
    else:
        print(f"No config file found at {sources_yaml_path}. Skipping seed.")

if __name__ == "__main__":
    main()
