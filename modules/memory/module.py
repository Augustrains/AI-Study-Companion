from .models import LearnerMemory, KnowledgePointMemory
class MemoryModule:
    def __init__(self, repository): self.repository = repository
    def get_learner_memory(self, user_id, learning_domain): return self.repository.load(user_id, learning_domain)
    def _save(self, memory): self.repository.save(memory)
    def sync_learner_profile(self, profile):
        memory = self.get_learner_memory(profile.user_id, profile.learning_domain)
        memory.current_confusions = profile.current_confusions
        memory.preferences = profile.preferences.to_dict()
        known = set(profile.known_knowledge_point_ids)
        existing = {p.knowledge_point_id: p for p in memory.knowledge_points}
        for point_id in known:
            if point_id not in existing: existing[point_id] = KnowledgePointMemory(point_id, mastery_level="了解", mastery_score=0.5, confidence=0.3)
        memory.knowledge_points = list(existing.values()); self._save(memory); return memory
