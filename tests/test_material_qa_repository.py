import unittest

from modules.material_qa.agent import MaterialQaAgent, MaterialQaQueryRewriter
from modules.material_qa.models import MaterialQaMessage, MaterialQaRetrievalResult
from modules.material_qa.repository import InMemoryMaterialQaMessageStore
from modules.material_qa.workflow import MaterialQaWorkflow


class _RecordingLlm:
    model = "test-model"

    def __init__(self) -> None:
        self.prompt = ""

    def generate(self, prompt: str) -> str:
        self.prompt = prompt
        return '{"refused": false, "answer": "数据库回答"}'


class _QueuedLlm:
    model = "test-model"

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


class _EmptyRetriever:
    def retrieve(self, **_kwargs) -> MaterialQaRetrievalResult:
        return MaterialQaRetrievalResult(chunks=[])


class _RecordingRetriever:
    def __init__(self) -> None:
        self.question = ""

    def retrieve(self, **kwargs) -> MaterialQaRetrievalResult:
        self.question = str(kwargs["question"])
        return MaterialQaRetrievalResult(chunks=[])


class _FixedQueryRewriter:
    def rewrite(self, **_kwargs) -> str:
        return "CNN是什么结构？"


class InMemoryMaterialQaMessageStoreTest(unittest.TestCase):
    def test_query_rewriter_resolves_follow_up(self) -> None:
        history = [
            MaterialQaMessage(role="user", content="CNN是什么？"),
            MaterialQaMessage(role="assistant", content="CNN是卷积神经网络。"),
        ]
        llm = _RecordingLlm()
        llm.generate = lambda _prompt: '{"standaloneQuestion": "CNN是什么结构？"}'  # type: ignore[method-assign]

        query = MaterialQaQueryRewriter(llm).rewrite(history=history, question="这个是什么结构？")

        self.assertEqual(query, "CNN是什么结构？")

    def test_workflow_retrieves_only_with_standalone_question(self) -> None:
        retriever = _RecordingRetriever()
        workflow = MaterialQaWorkflow(
            agent=MaterialQaAgent(_RecordingLlm()),
            retriever=retriever,
            message_store=InMemoryMaterialQaMessageStore(),
            query_rewriter=_FixedQueryRewriter(),  # type: ignore[arg-type]
        )

        workflow.ask(
            conversation_id="ui-only-token",
            user_id="1",
            book_id="dl",
            question="这个是什么结构？",
        )

        self.assertEqual(retriever.question, "CNN是什么结构？")

    def test_history_is_scoped_by_user_and_book(self) -> None:
        store = InMemoryMaterialQaMessageStore()
        store.add_message(user_id="1", book_id="ml", role="user", content="机器学习问题")
        store.add_message(user_id="1", book_id="dl", role="user", content="深度学习问题")
        store.add_message(user_id="2", book_id="ml", role="user", content="其他用户问题")

        history = store.list_recent(user_id="1", book_id="ml")

        self.assertEqual([message.content for message in history], ["机器学习问题"])

    def test_reset_hides_only_earlier_messages_in_the_same_book(self) -> None:
        store = InMemoryMaterialQaMessageStore()
        store.add_message(user_id="1", book_id="ml", role="user", content="重置前")
        store.add_message(user_id="1", book_id="dl", role="user", content="另一本书")
        store.reset_context(user_id="1", book_id="ml")
        store.add_message(user_id="1", book_id="ml", role="user", content="重置后")

        ml_history = store.list_recent(user_id="1", book_id="ml")
        dl_history = store.list_recent(user_id="1", book_id="dl")

        self.assertEqual([message.content for message in ml_history], ["重置后"])
        self.assertEqual([message.content for message in dl_history], ["另一本书"])

    def test_history_uses_the_latest_twelve_messages(self) -> None:
        store = InMemoryMaterialQaMessageStore()
        for index in range(15):
            store.add_message(user_id="1", book_id="ml", role="user", content=str(index))

        history = store.list_recent(user_id="1", book_id="ml")

        self.assertEqual([message.content for message in history], [str(index) for index in range(3, 15)])

    def test_workflow_reads_history_and_saves_the_successful_exchange(self) -> None:
        store = InMemoryMaterialQaMessageStore()
        store.save_exchange(
            user_id="1",
            book_id="ml",
            question="之前的问题",
            answer="之前的回答",
        )
        llm = _RecordingLlm()
        workflow = MaterialQaWorkflow(
            agent=MaterialQaAgent(llm),
            retriever=_EmptyRetriever(),
            message_store=store,
        )

        result = workflow.ask(
            conversation_id="ui-only-token",
            user_id="1",
            book_id="ml",
            question="现在的问题",
        )

        self.assertEqual(result.answer, "数据库回答")
        self.assertIn("之前的问题", llm.prompt)
        self.assertIn("之前的回答", llm.prompt)
        history = store.list_recent(user_id="1", book_id="ml")
        self.assertEqual(
            [message.content for message in history],
            ["之前的问题", "之前的回答", "现在的问题", "数据库回答"],
        )

    def test_socratic_task_transitions_before_generating_next_reply(self) -> None:
        store = InMemoryMaterialQaMessageStore()
        first_llm = _QueuedLlm(['{"refused": false, "answer": "你认为应该先明确什么？"}'])
        first_workflow = MaterialQaWorkflow(
            agent=MaterialQaAgent(first_llm),
            retriever=_EmptyRetriever(),
            message_store=store,
        )

        first = first_workflow.ask(
            conversation_id="ui-token",
            user_id="1",
            book_id="ml",
            question="设计一个自适应学习系统",
            answer_mode="socratic",
        )

        self.assertEqual(first.socratic_state, "probe")
        self.assertIsNotNone(first.learning_task_id)
        next_llm = _QueuedLlm([
            '{"quality": "wrong"}',
            '{"refused": false, "answer": "如果不记录学习结果，系统如何自适应？"}',
        ])
        next_workflow = MaterialQaWorkflow(
            agent=MaterialQaAgent(next_llm),
            retriever=_EmptyRetriever(),
            message_store=store,
        )
        second = next_workflow.ask(
            conversation_id="ui-token",
            user_id="1",
            book_id="ml",
            question="不需要记录任何信息",
            answer_mode="socratic",
            learning_task_id=first.learning_task_id,
        )

        self.assertEqual(second.response_quality, "wrong")
        self.assertEqual(second.socratic_state, "confront")
        self.assertIn("当前教学状态：confront", next_llm.prompts[-1])

    def test_correct_confirm_reply_completes_and_closes_active_task(self) -> None:
        store = InMemoryMaterialQaMessageStore()
        store.save_exchange(
            user_id="1",
            book_id="ml",
            question="解释过拟合",
            answer="训练集很好但验证集变差说明什么？",
            answer_mode="socratic",
            learning_task_id="task-1",
            socratic_state="confirm",
        )
        llm = _QueuedLlm([
            '{"quality": "correct"}',
            '{"refused": false, "answer": "很好，你已经完成本轮引导。"}',
        ])
        workflow = MaterialQaWorkflow(
            agent=MaterialQaAgent(llm),
            retriever=_EmptyRetriever(),
            message_store=store,
        )

        answer = workflow.ask(
            conversation_id="ui-token",
            user_id="1",
            book_id="ml",
            question="这说明模型过拟合，泛化能力下降",
            answer_mode="socratic",
            learning_task_id="task-1",
        )

        self.assertTrue(answer.socratic_completed)
        self.assertIsNone(store.get_active_learning_task(user_id="1", book_id="ml"))

    def test_explicit_finish_appends_marker_without_putting_system_message_in_history(self) -> None:
        store = InMemoryMaterialQaMessageStore()
        store.save_exchange(
            user_id="1",
            book_id="ml",
            question="一道题",
            answer="先说说你的想法？",
            answer_mode="socratic",
            learning_task_id="task-2",
            socratic_state="probe",
        )

        store.finish_learning_task(user_id="1", book_id="ml", learning_task_id="task-2")

        self.assertIsNone(store.get_active_learning_task(user_id="1", book_id="ml"))
        self.assertEqual(
            [message.content for message in store.list_recent(user_id="1", book_id="ml")],
            ["一道题", "先说说你的想法？"],
        )


if __name__ == "__main__":
    unittest.main()
