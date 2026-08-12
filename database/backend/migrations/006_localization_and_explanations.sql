-- Reviewable Quiz localizations and post-submission explanations.
-- Apply after 005_runtime_roles.sql and before localization_seed.sql.

BEGIN;

ALTER TABLE learning_item_localizations
    ADD COLUMN IF NOT EXISTS title TEXT,
    ADD COLUMN IF NOT EXISTS source_locale TEXT NOT NULL DEFAULT 'en',
    ADD COLUMN IF NOT EXISTS translation_method TEXT NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS translation_version TEXT NOT NULL DEFAULT 'v1',
    ADD COLUMN IF NOT EXISTS explanation_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS explanation_status TEXT NOT NULL DEFAULT 'draft'
        CHECK (explanation_status IN ('draft', 'needs_review', 'approved', 'published', 'rejected')),
    ADD COLUMN IF NOT EXISTS content_hash TEXT,
    ADD COLUMN IF NOT EXISTS review_note TEXT,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS item_option_localizations (
    item_option_localization_id TEXT PRIMARY KEY,
    item_option_id TEXT NOT NULL REFERENCES item_options(item_option_id),
    locale TEXT NOT NULL,
    option_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'needs_review', 'approved', 'published', 'rejected')),
    translation_method TEXT NOT NULL DEFAULT 'manual',
    translation_version TEXT NOT NULL DEFAULT 'v1',
    content_hash TEXT,
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    review_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (item_option_id, locale)
);

CREATE TABLE IF NOT EXISTS localization_review_records (
    localization_review_id TEXT PRIMARY KEY,
    learning_item_version_id TEXT NOT NULL REFERENCES learning_item_versions(learning_item_version_id),
    locale TEXT NOT NULL,
    translation_review_status TEXT NOT NULL
        CHECK (translation_review_status IN ('approved', 'changes_requested', 'rejected')),
    explanation_review_status TEXT NOT NULL
        CHECK (explanation_review_status IN ('approved', 'changes_requested', 'rejected')),
    checked_stem BOOLEAN NOT NULL,
    checked_options BOOLEAN NOT NULL,
    checked_explanation BOOLEAN NOT NULL,
    reviewer_id TEXT NOT NULL,
    review_note TEXT,
    content_snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS localization_publication_batches (
    localization_publication_batch_id TEXT PRIMARY KEY,
    batch_name TEXT NOT NULL,
    locale TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    manifest_hash TEXT NOT NULL UNIQUE,
    item_count INTEGER NOT NULL CHECK (item_count > 0),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'published', 'failed', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS localization_publication_batch_items (
    localization_publication_batch_id TEXT NOT NULL
        REFERENCES localization_publication_batches(localization_publication_batch_id),
    learning_item_version_id TEXT NOT NULL REFERENCES learning_item_versions(learning_item_version_id),
    localization_review_id TEXT NOT NULL REFERENCES localization_review_records(localization_review_id),
    publish_status TEXT NOT NULL CHECK (publish_status IN ('published', 'failed')),
    PRIMARY KEY (localization_publication_batch_id, learning_item_version_id)
);

CREATE INDEX IF NOT EXISTS idx_item_option_localizations_locale_status
    ON item_option_localizations(locale, status);
CREATE INDEX IF NOT EXISTS idx_localization_reviews_version_locale
    ON localization_review_records(learning_item_version_id, locale, created_at DESC);

-- Pre-answer delivery. It never exposes answers or explanations. English is
-- always present; a localized row is present only after every localized option
-- and the localized stem have been published.
CREATE OR REPLACE VIEW student_quiz_localized_bank_safe AS
SELECT
    quiz.learning_item_id,
    quiz.learning_item_version_id,
    quiz.title,
    'en'::TEXT AS locale,
    FALSE AS fallback_used,
    quiz.source_id,
    quiz.source_url,
    quiz.stem,
    quiz.options,
    quiz.knowledge_point_ids
FROM student_quiz_bank_safe AS quiz
UNION ALL
SELECT
    quiz.learning_item_id,
    quiz.learning_item_version_id,
    COALESCE(localization.title, quiz.title) AS title,
    localization.locale,
    FALSE AS fallback_used,
    quiz.source_id,
    quiz.source_url,
    localization.stem,
    COALESCE((
        SELECT jsonb_agg(
            jsonb_build_object(
                'key', option.option_key,
                'text', option_localization.option_text,
                'sortOrder', option.sort_order
            ) ORDER BY option.sort_order
        )
        FROM item_options AS option
        JOIN item_option_localizations AS option_localization
          ON option_localization.item_option_id = option.item_option_id
         AND option_localization.locale = localization.locale
         AND option_localization.status = 'published'
        WHERE option.learning_item_version_id = quiz.learning_item_version_id
    ), '[]'::jsonb) AS options,
    quiz.knowledge_point_ids
FROM student_quiz_bank_safe AS quiz
JOIN learning_item_localizations AS localization
  ON localization.learning_item_version_id = quiz.learning_item_version_id
 AND localization.status = 'published'
WHERE (
    SELECT count(*) FROM item_options AS option
    WHERE option.learning_item_version_id = quiz.learning_item_version_id
) = (
    SELECT count(*)
    FROM item_options AS option
    JOIN item_option_localizations AS option_localization
      ON option_localization.item_option_id = option.item_option_id
     AND option_localization.locale = localization.locale
     AND option_localization.status = 'published'
    WHERE option.learning_item_version_id = quiz.learning_item_version_id
);

-- Explanations are returned only for the authenticated student's completed
-- submission. This function intentionally returns no answer_data/is_correct.
CREATE OR REPLACE FUNCTION get_student_quiz_feedback(
    p_submission_id TEXT,
    p_locale TEXT DEFAULT 'en'
) RETURNS TABLE (
    submission_id TEXT,
    learning_item_version_id TEXT,
    locale TEXT,
    fallback_used BOOLEAN,
    explanation_data JSONB
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_user_id TEXT := current_setting('app.current_user_id', TRUE);
    v_version_id TEXT;
BEGIN
    IF v_user_id IS NULL OR btrim(v_user_id) = '' THEN
        RAISE EXCEPTION 'authenticated user context is required';
    END IF;

    SELECT submission.learning_item_version_id
      INTO v_version_id
      FROM public.task_submissions AS submission
      JOIN public.evaluation_results AS result
        ON result.submission_id = submission.submission_id
       AND result.status = 'completed'
     WHERE submission.submission_id = p_submission_id
       AND submission.user_id = v_user_id
     LIMIT 1;

    IF v_version_id IS NULL THEN
        RETURN;
    END IF;

    RETURN QUERY
    SELECT
        p_submission_id,
        v_version_id,
        localization.locale,
        localization.locale <> p_locale,
        localization.explanation_data
    FROM public.learning_item_localizations AS localization
    WHERE localization.learning_item_version_id = v_version_id
      AND localization.explanation_status = 'published'
      AND localization.locale IN (p_locale, 'en')
    ORDER BY CASE WHEN localization.locale = p_locale THEN 0 ELSE 1 END
    LIMIT 1;
END;
$$;

REVOKE ALL ON FUNCTION get_student_quiz_feedback(TEXT, TEXT) FROM PUBLIC;

-- Atomic, guarded localization publisher. The runtime publisher role receives
-- EXECUTE only; it never receives direct UPDATE rights on localization tables.
CREATE OR REPLACE FUNCTION publish_quiz_localization_batch(
    p_batch_id TEXT,
    p_batch_name TEXT,
    p_requested_by TEXT,
    p_manifest_hash TEXT,
    p_payload JSONB
) RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_entry JSONB;
    v_version_id TEXT;
    v_locale TEXT;
    v_reviewer_id TEXT;
    v_option_key TEXT;
    v_option_text TEXT;
    v_option_id TEXT;
    v_review_id TEXT;
    v_localization_id TEXT;
    v_item_count INTEGER := 0;
    v_base_option_count INTEGER;
BEGIN
    IF jsonb_typeof(p_payload) <> 'array' OR jsonb_array_length(p_payload) = 0 THEN
        RAISE EXCEPTION 'Localization release payload must be a non-empty array';
    END IF;

    INSERT INTO public.localization_publication_batches
        (localization_publication_batch_id, batch_name, locale, requested_by,
         manifest_hash, item_count, status)
    VALUES
        (p_batch_id, p_batch_name, 'zh-CN', p_requested_by,
         p_manifest_hash, jsonb_array_length(p_payload), 'draft');

    FOR v_entry IN SELECT value FROM jsonb_array_elements(p_payload)
    LOOP
        v_version_id := v_entry->>'versionId';
        v_locale := v_entry->>'locale';
        v_reviewer_id := btrim(COALESCE(v_entry->>'reviewerId', ''));
        IF v_locale <> 'zh-CN'
           OR v_reviewer_id = ''
           OR v_entry->>'translationReviewStatus' <> 'approved'
           OR v_entry->>'explanationReviewStatus' <> 'approved'
           OR COALESCE((v_entry->'explanation'->>'requiresSubjectMatterReview')::BOOLEAN, FALSE) <> TRUE THEN
            RAISE EXCEPTION 'Localization release precondition failed for %', v_version_id;
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM public.learning_items AS item
            JOIN public.learning_item_versions AS version
              ON version.learning_item_id = item.learning_item_id
            JOIN public.source_documents AS document
              ON document.source_document_id = item.source_document_id
            JOIN public.source_repositories AS repository
              ON repository.source_id = document.source_id
            WHERE version.learning_item_version_id = v_version_id
              AND item.current_version_id = version.learning_item_version_id
              AND item.status = 'published'
              AND repository.commit_sha = v_entry->>'sourceCommit'
              AND document.content_hash = v_entry->>'sourceContentHash'
        ) THEN
            RAISE EXCEPTION 'Base Quiz not published or source changed: %', v_version_id;
        END IF;

        SELECT count(*) INTO v_base_option_count
        FROM public.item_options
        WHERE learning_item_version_id = v_version_id;
        IF jsonb_typeof(v_entry->'options') <> 'object'
           OR v_base_option_count <> (SELECT count(*) FROM jsonb_object_keys(v_entry->'options')) THEN
            RAISE EXCEPTION 'Localized option set does not match base Quiz: %', v_version_id;
        END IF;

        v_localization_id := 'item-localization-' || md5(v_version_id || ':' || v_locale);
        INSERT INTO public.learning_item_localizations
            (learning_item_localization_id, learning_item_version_id, locale, stem,
             explanation, status, source_locale, translation_method, translation_version,
             explanation_data, explanation_status, content_hash, reviewed_by, reviewed_at,
             review_note, updated_at)
        VALUES
            (v_localization_id, v_version_id, v_locale, v_entry->>'stem',
             v_entry->'explanation'->>'summary', 'published', 'en',
             v_entry->>'translationMethod', v_entry->>'translationVersion',
             v_entry->'explanation', 'published',
             md5((v_entry->>'stem') || (v_entry->'explanation')::TEXT),
             v_reviewer_id, now(), v_entry->>'reviewerNote', now())
        ON CONFLICT (learning_item_version_id, locale) DO UPDATE SET
            stem = EXCLUDED.stem,
            explanation = EXCLUDED.explanation,
            status = 'published',
            translation_method = EXCLUDED.translation_method,
            translation_version = EXCLUDED.translation_version,
            explanation_data = EXCLUDED.explanation_data,
            explanation_status = 'published',
            content_hash = EXCLUDED.content_hash,
            reviewed_by = EXCLUDED.reviewed_by,
            reviewed_at = now(),
            review_note = EXCLUDED.review_note,
            updated_at = now();

        FOR v_option_key, v_option_text IN
            SELECT key, value FROM jsonb_each_text(v_entry->'options')
        LOOP
            SELECT item_option_id INTO v_option_id
            FROM public.item_options
            WHERE learning_item_version_id = v_version_id
              AND option_key = v_option_key;
            IF v_option_id IS NULL THEN
                RAISE EXCEPTION 'Unknown localized option % for %', v_option_key, v_version_id;
            END IF;
            INSERT INTO public.item_option_localizations
                (item_option_localization_id, item_option_id, locale, option_text,
                 status, translation_method, translation_version, content_hash,
                 reviewed_by, reviewed_at, review_note, updated_at)
            VALUES
                ('option-localization-' || md5(v_option_id || ':' || v_locale),
                 v_option_id, v_locale, v_option_text, 'published',
                 v_entry->>'translationMethod', v_entry->>'translationVersion',
                 md5(v_option_text), v_reviewer_id, now(), v_entry->>'reviewerNote', now())
            ON CONFLICT (item_option_id, locale) DO UPDATE SET
                option_text = EXCLUDED.option_text,
                status = 'published',
                translation_method = EXCLUDED.translation_method,
                translation_version = EXCLUDED.translation_version,
                content_hash = EXCLUDED.content_hash,
                reviewed_by = EXCLUDED.reviewed_by,
                reviewed_at = now(),
                review_note = EXCLUDED.review_note,
                updated_at = now();
        END LOOP;

        v_review_id := 'localization-review-' || md5(p_batch_id || ':' || v_version_id || ':' || v_locale);
        INSERT INTO public.localization_review_records
            (localization_review_id, learning_item_version_id, locale,
             translation_review_status, explanation_review_status,
             checked_stem, checked_options, checked_explanation,
             reviewer_id, review_note, content_snapshot)
        VALUES
            (v_review_id, v_version_id, v_locale, 'approved', 'approved',
             TRUE, TRUE, TRUE, v_reviewer_id, v_entry->>'reviewerNote', v_entry);
        INSERT INTO public.localization_publication_batch_items
            (localization_publication_batch_id, learning_item_version_id,
             localization_review_id, publish_status)
        VALUES (p_batch_id, v_version_id, v_review_id, 'published');
        v_item_count := v_item_count + 1;
    END LOOP;

    UPDATE public.localization_publication_batches
       SET status = 'published', published_at = now()
     WHERE localization_publication_batch_id = p_batch_id;
    RETURN v_item_count;
END;
$$;

REVOKE ALL ON FUNCTION publish_quiz_localization_batch(TEXT, TEXT, TEXT, TEXT, JSONB) FROM PUBLIC;

COMMIT;
