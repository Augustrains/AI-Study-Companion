from dataclasses import dataclass

from agents.diagnostic_agent import DiagnosticAgent
from domain.assessment_service import AssessmentService
from domain.learner_profile_service import LearnerProfileService
from modules.diagnosis.module import DiagnosisModule
from modules.learner_profile.module import LearnerProfileModule
from repositories.learner_profile_repository import JsonLearnerProfileRepository
from repositories.question_repository import QuestionRepository
from repositories.session_repository import InMemoryLearningSessionRepository
from sdk.llm_client import NullLLMClient
from workflows.diagnosis_workflow import DiagnosisWorkflow
from workflows.learner_profile_workflow import LearnerProfileWorkflow


@dataclass(frozen=True)
class ApiDependencies:
    profile: LearnerProfileModule
    diagnosis: DiagnosisModule


def build_api_dependencies() -> ApiDependencies:
    profile_repository = JsonLearnerProfileRepository()
    profile_service = LearnerProfileService()
    profile_workflow = LearnerProfileWorkflow(profile_repository, profile_service)
    question_repository = QuestionRepository()
    session_repository = InMemoryLearningSessionRepository()
    diagnosis_workflow = DiagnosisWorkflow(
        question_repository=question_repository,
        session_repository=session_repository,
        assessment_service=AssessmentService(),
        diagnostic_agent=DiagnosticAgent(NullLLMClient()),
    )
    return ApiDependencies(
        profile=LearnerProfileModule(profile_repository, profile_service, profile_workflow),
        diagnosis=DiagnosisModule(diagnosis_workflow, question_repository, session_repository),
    )


def build_diagnosis_workflow() -> tuple[DiagnosisWorkflow, InMemoryLearningSessionRepository]:
    session_repository = InMemoryLearningSessionRepository()
    workflow = DiagnosisWorkflow(
        question_repository=QuestionRepository(),
        session_repository=session_repository,
        assessment_service=AssessmentService(),
        diagnostic_agent=DiagnosticAgent(NullLLMClient()),
    )
    return workflow, session_repository
