-- =============================================================================
-- Seed data: the demo user the frontend and the docs assume
-- =============================================================================
-- The frontend and every example in the documentation call the MCP tools with
-- `user_id: 1`. `pantry_inventory.user_id` has a foreign key to `users`, so
-- without this row every write fails and the demo dies on its first insert.
--
-- Run after database/schema.sql
-- =============================================================================

-- `users.id` is GENERATED ALWAYS AS IDENTITY, so the value has to be forced
-- with OVERRIDING SYSTEM VALUE instead of supplied normally.
INSERT INTO users (id, email)
    OVERRIDING SYSTEM VALUE
VALUES (1, 'demo@eatmefirst.local')
ON CONFLICT (id) DO NOTHING;

-- Forcing an id does not advance the identity sequence, so the next ordinary
-- INSERT would try to reuse id 1 and fail on the primary key. Push the
-- sequence past whatever ids now exist.
SELECT setval(
    pg_get_serial_sequence('users', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM users), 1)
);
