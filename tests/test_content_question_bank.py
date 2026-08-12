import unittest

from modules.diagnosis.question_bank import QuestionBank


class ContentQuestionBankTest(unittest.TestCase):
    def test_csv_content_data_is_used_and_mastered_skills_are_excluded(self) -> None:
        bank = QuestionBank()
        question_set = bank.get_questions("ml-001", mastered_skill_ids={"rl-discount"})

        self.assertTrue(question_set.questions)
        self.assertNotIn("rl-discount", question_set.selected_skill_ids)
        self.assertTrue(all("rl-discount" not in question.knowledge_point_ids for question in question_set.questions))
        self.assertTrue(all(question.book_id == "ml-001" for question in question_set.questions))
        self.assertTrue(all(question.chapter_id for question in question_set.questions))


if __name__ == "__main__":
    unittest.main()
