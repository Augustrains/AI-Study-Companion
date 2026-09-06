-- Speed up infinite-practice question selection and duplicate-answer checks.
-- These are non-unique indexes: existing rows and diagnostic workflows remain unchanged.

CREATE INDEX idx_questions_book_type_id
    ON questions (book_id, item_type, id);

CREATE INDEX idx_diagnostic_answer_session_question
    ON diagnostic_answer (session_id, question_id);
