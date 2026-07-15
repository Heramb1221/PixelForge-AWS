-- PixelForge database schema
-- Target: Amazon RDS PostgreSQL 15+
-- Single-user deployment: one row in `users` is expected, but the schema
-- keeps a users table so the app could grow into multi-user without a
-- structural rewrite.

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS projects (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(150) NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, name)
);

-- A variant profile defines ONE output rendition (e.g. "thumbnail", "social_card")
-- that every image uploaded to the parent project will be transformed into.
CREATE TABLE IF NOT EXISTS variant_profiles (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    label           VARCHAR(80) NOT NULL,        -- e.g. "thumbnail"
    target_width    INTEGER NOT NULL,
    target_height   INTEGER NOT NULL,
    output_format   VARCHAR(10) NOT NULL DEFAULT 'webp', -- webp | jpeg | png
    smart_crop      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, label)
);

CREATE TABLE IF NOT EXISTS images (
    id                  SERIAL PRIMARY KEY,
    project_id          INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    original_key        VARCHAR(512) NOT NULL,   -- S3 key in the "originals" bucket
    original_filename   VARCHAR(255) NOT NULL,
    content_type        VARCHAR(100),
    original_size_bytes INTEGER,
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
                        -- pending -> processing -> done -> failed
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at        TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS image_variants (
    id                  SERIAL PRIMARY KEY,
    image_id            INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    variant_profile_id  INTEGER NOT NULL REFERENCES variant_profiles(id) ON DELETE CASCADE,
    processed_key       VARCHAR(512) NOT NULL,   -- S3 key in the "processed" bucket
    width               INTEGER,
    height              INTEGER,
    size_bytes          INTEGER,
    bytes_saved         INTEGER DEFAULT 0,       -- vs. a naive same-format resize
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Rolling analytics events, aggregated by the dashboard/analytics page.
CREATE TABLE IF NOT EXISTS analytics_events (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    event_type      VARCHAR(40) NOT NULL,  -- upload_completed | processing_failed | cleanup_deleted
    bytes_saved     INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_images_project_id ON images(project_id);
CREATE INDEX IF NOT EXISTS idx_images_status ON images(status);
CREATE INDEX IF NOT EXISTS idx_variant_profiles_project_id ON variant_profiles(project_id);
CREATE INDEX IF NOT EXISTS idx_image_variants_image_id ON image_variants(image_id);
CREATE INDEX IF NOT EXISTS idx_analytics_events_project_id ON analytics_events(project_id);
