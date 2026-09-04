"""学习目标模块：保存并读取用户在某本书上的目标水平与每周投入时长。"""

from .module import LearnerGoalModule
from .repository import JsonLearnerGoalRepository, MysqlLearnerGoalRepository

__all__ = ["JsonLearnerGoalRepository", "LearnerGoalModule", "MysqlLearnerGoalRepository"]
