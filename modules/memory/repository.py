from datetime import datetime
import json
from pathlib import Path
from .models import LearnerMemory

class JsonMemoryRepository:
    def __init__(self, reader, store): self.reader, self.store = reader, store
    def now(self): return datetime.now().isoformat(timespec="seconds")
    def load(self, user_id, learning_domain):
        raw = self.reader.read() or {}
        value = raw.get(f"{user_id}:{learning_domain}")
        return LearnerMemory(**value) if value else LearnerMemory(str(user_id), learning_domain, updated_at=self.now())
    def save(self, memory):
        data = {"user_id": memory.user_id, "learning_domain": memory.learning_domain, "knowledge_points": [vars(p) for p in memory.knowledge_points], "current_confusions": memory.current_confusions, "preferences": memory.preferences, "updated_at": memory.updated_at, "update_count": memory.update_count}
        self.store.save(path=self.reader.path, content=data, mode="upsert", key_path=[f"{memory.user_id}:{memory.learning_domain}"])
