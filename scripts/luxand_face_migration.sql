-- Luxand.cloud face integration
-- Run once against the existing PostgreSQL/Supabase database.

ALTER TABLE student_face_embeddings
    ALTER COLUMN embedding DROP NOT NULL;

ALTER TABLE student_face_embeddings
    ADD COLUMN IF NOT EXISTS luxand_person_id VARCHAR(255);

CREATE UNIQUE INDEX IF NOT EXISTS uq_student_face_luxand_person
    ON student_face_embeddings (luxand_person_id)
    WHERE luxand_person_id IS NOT NULL;
