import os
import json
import yaml
import re
from typing import List
from datetime import datetime
from softwiki.source_store.models import Event
from softwiki.config import get_config_path

class TimelineExtractor:
    def __init__(self):
        pass

    def load_configs(self):
        self.topics = {}
        topics_path = get_config_path("topics.yaml")
        if os.path.exists(topics_path):
            try:
                with open(topics_path, "r", encoding="utf-8") as f:
                    self.topics = yaml.safe_load(f).get("topics", {}) or {}
            except Exception as e:
                print(f"Error loading topics config: {e}")

    def extract_events(self, doc_id: int, text: str, published_at: datetime) -> List[Event]:
        self.load_configs()
        
        from softwiki.intelligence.llm_client import get_llm_client_and_params
        client, model_name, temperature, max_tokens = get_llm_client_and_params("cheap_extraction")
        
        if not client:
            print("No valid LLM client found. Using rule-based fallback event extraction.")
            return self._fallback_extract_events(doc_id, text, published_at)

        if self.topics:
            topics_str = ", ".join(self.topics.keys())
            topic_instruction = f"The topic area (must map closely to: {topics_str}, or 'general')."
            predefined_section = f"Predefined topics: {topics_str}"
        else:
            topic_instruction = "The topic area (determine this dynamically based on the subject of the event, keeping it concise, lowercase, and hyphen-separated, e.g. 'de-dollarization', 'low-altitude-economy')."
            predefined_section = "Predefined topics: None (infer dynamically from the text)"

        system_prompt = f"""You are a Timeline Event Extraction Assistant.
Your task is to extract concrete chronological events mentioned in the text.
An event represents a specific occurrence at a particular time (e.g. an agreement, a summit, an announcement, a version launch).

{predefined_section}

For each event, you must extract:
1. "title": A short summary of what happened.
2. "description": A details sentence describing the event.
3. "event_date": The date of the event in "YYYY-MM-DD" format. If only a year is mentioned, default to "YYYY-01-01". If only month and year are mentioned, default to "YYYY-MM-01". If no date is found, use the document publish date: "{published_at.strftime('%Y-%m-%d')}".
4. "topic": {topic_instruction}
5. "confidence": A float from 0.0 to 1.0.

Return your response strictly as a JSON object containing a list of events under the key "events".
Example Output:
{{
  "events": [
    {{
      "title": "Project Alpha Launch",
      "description": "The new version of the platform was deployed and opened for public access.",
      "event_date": "2024-10-22",
      "topic": "general",
      "confidence": 0.95
    }}
  ]
}}
"""

        try:
            extra_params = {}
            if max_tokens is not None:
                extra_params["max_tokens"] = max_tokens
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract events from the following document text:\n\n{text}"}
                ],
                temperature=temperature,
                response_format={"type": "json_object"},
                **extra_params
            )

            result_json = json.loads(response.choices[0].message.content)
            extracted = result_json.get("events", [])
            
            events = []
            for ev in extracted:
                date_str = ev.get("event_date")
                parsed_date = published_at
                if date_str:
                    try:
                        # try various formats
                        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
                            try:
                                if len(date_str) == 4:
                                    parsed_date = datetime.strptime(f"{date_str}-01-01", "%Y-%m-%d")
                                elif len(date_str) == 7:
                                    parsed_date = datetime.strptime(f"{date_str}-01", "%Y-%m-%d")
                                else:
                                    parsed_date = datetime.strptime(date_str, fmt)
                                break
                            except ValueError:
                                continue
                    except Exception:
                        parsed_date = published_at

                events.append(Event(
                    title=ev.get("title", "Research Event"),
                    description=ev.get("description", ""),
                    event_date=parsed_date,
                    topic=ev.get("topic", "general"),
                    document_id=doc_id,
                    confidence=float(ev.get("confidence", 0.75))
                ))
            return events

        except Exception as e:
            print(f"API event extraction failed: {e}. Falling back to local rules.")
            return self._fallback_extract_events(doc_id, text, published_at)

    def _fallback_extract_events(self, doc_id: int, text: str, published_at: datetime) -> List[Event]:
        events = []
        sentences = re.split(r'[.!?]\s+', text)
        
        # Regex to find years like 2020-2029
        year_re = re.compile(r'\b(20[23][0-9])\b')
        
        # Find topics dynamically to map to events
        topics_mapping = list(self.topics.keys()) if self.topics else ["general"]

        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            
            match = year_re.search(s_clean)
            if match:
                year = match.group(1)
                try:
                    event_date = datetime(int(year), 1, 1)
                except Exception:
                    event_date = published_at
                
                # Check if it contains keywords related to any topic
                mapped_topic = "general"
                for topic in topics_mapping:
                    if topic in s_clean.lower():
                        mapped_topic = topic
                        break
                
                title = s_clean[:60] + "..." if len(s_clean) > 60 else s_clean
                events.append(Event(
                    title=title,
                    description=s_clean,
                    event_date=event_date,
                    topic=mapped_topic,
                    document_id=doc_id,
                    confidence=0.70
                ))
                
        # If no date references, add a single fallback event for the publish date
        if not events:
            events.append(Event(
                title=f"Publication of Document: {text[:40].strip()}...",
                description=f"Document published containing research material.",
                event_date=published_at,
                topic="general",
                document_id=doc_id,
                confidence=0.80
            ))
            
        return events
