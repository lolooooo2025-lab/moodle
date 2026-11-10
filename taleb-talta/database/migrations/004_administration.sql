-- Wave 4 additive migration; tools/migrate_wave4.py applies it in one transaction.

-- Existing tables are preserved. New builder/cron/backup tables plus two additive columns.

ALTER TABLE menu_items ADD COLUMN IF NOT EXISTS label VARCHAR(120) NOT NULL DEFAULT '';

ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS lock_token VARCHAR(64) NOT NULL DEFAULT '';

ALTER TABLE scheduled_tasks ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP WITH TIME ZONE;

CREATE TABLE IF NOT EXISTS dashboard_blocks (
	id SERIAL NOT NULL, 
	role VARCHAR(9) NOT NULL, 
	block_key VARCHAR(60) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	CONSTRAINT pk_dashboard_blocks PRIMARY KEY (id), 
	CONSTRAINT uq_dashboard_block UNIQUE (role, block_key), 
	CONSTRAINT ck_dashboard_blocks_user_role CHECK (role IN ('owner', 'admin', 'moderator', 'teacher', 'student', 'parent'))
);

CREATE TABLE IF NOT EXISTS role_themes (
	role VARCHAR(9) NOT NULL, 
	theme_key VARCHAR(40) NOT NULL, 
	CONSTRAINT pk_role_themes PRIMARY KEY (role), 
	CONSTRAINT ck_role_themes_user_role CHECK (role IN ('owner', 'admin', 'moderator', 'teacher', 'student', 'parent'))
);

CREATE TABLE IF NOT EXISTS backup_artifacts (
	id SERIAL NOT NULL, 
	file_name VARCHAR(120) NOT NULL, 
	file_size BIGINT NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	status VARCHAR(8) NOT NULL, 
	include_uploads BOOLEAN NOT NULL, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	error_key VARCHAR(120) NOT NULL, 
	CONSTRAINT pk_backup_artifacts PRIMARY KEY (id), 
	CONSTRAINT uq_backup_artifacts_file_name UNIQUE (file_name), 
	CONSTRAINT ck_backup_artifacts_backup_status CHECK (status IN ('creating', 'ready', 'failed')), 
	CONSTRAINT fk_backup_artifacts_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS custom_fields (
	id SERIAL NOT NULL, 
	applies_to VARCHAR(6) NOT NULL, 
	machine_name VARCHAR(60) NOT NULL, 
	label VARCHAR(120) NOT NULL, 
	field_type VARCHAR(8) NOT NULL, 
	options_json JSON NOT NULL, 
	required BOOLEAN NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	sort_order INTEGER NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_custom_fields PRIMARY KEY (id), 
	CONSTRAINT uq_custom_field_name UNIQUE (applies_to, machine_name), 
	CONSTRAINT ck_custom_fields_field_entity CHECK (applies_to IN ('user', 'course')), 
	CONSTRAINT ck_custom_fields_field_type CHECK (field_type IN ('text', 'number', 'select', 'checkbox')), 
	CONSTRAINT fk_custom_fields_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_custom_fields_applies_to ON custom_fields (applies_to);

CREATE TABLE IF NOT EXISTS dashboard_preferences (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	block_key VARCHAR(60) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	CONSTRAINT pk_dashboard_preferences PRIMARY KEY (id), 
	CONSTRAINT uq_dashboard_preference UNIQUE (user_id, block_key), 
	CONSTRAINT fk_dashboard_preferences_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_dashboard_preferences_user_id ON dashboard_preferences (user_id);

CREATE TABLE IF NOT EXISTS digest_deliveries (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	period_date VARCHAR(10) NOT NULL, 
	payload_json JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_digest_deliveries PRIMARY KEY (id), 
	CONSTRAINT uq_digest_user_day UNIQUE (user_id, period_date), 
	CONSTRAINT fk_digest_deliveries_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_digest_deliveries_user_id ON digest_deliveries (user_id);

CREATE TABLE IF NOT EXISTS task_runs (
	id SERIAL NOT NULL, 
	task_id INTEGER, 
	task_key VARCHAR(255) NOT NULL, 
	status VARCHAR(7) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	detail_json JSON NOT NULL, 
	error_key VARCHAR(120) NOT NULL, 
	triggered_by INTEGER, 
	CONSTRAINT pk_task_runs PRIMARY KEY (id), 
	CONSTRAINT ck_task_runs_task_status CHECK (status IN ('running', 'success', 'failed', 'skipped')), 
	CONSTRAINT fk_task_runs_triggered_by_users FOREIGN KEY(triggered_by) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_task_runs_task_id ON task_runs (task_id);

CREATE INDEX IF NOT EXISTS ix_task_runs_task_key ON task_runs (task_key);

CREATE TABLE IF NOT EXISTS theme_presets (
	id SERIAL NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	base_theme VARCHAR(20) NOT NULL, 
	primary_color VARCHAR(7) NOT NULL, 
	secondary_color VARCHAR(7) NOT NULL, 
	accent_color VARCHAR(7) NOT NULL, 
	radius INTEGER NOT NULL, 
	density VARCHAR(11) NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_theme_presets PRIMARY KEY (id), 
	CONSTRAINT uq_theme_presets_name UNIQUE (name), 
	CONSTRAINT ck_theme_presets_theme_density CHECK (density IN ('comfortable', 'compact')), 
	CONSTRAINT fk_theme_presets_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS custom_field_values (
	id SERIAL NOT NULL, 
	field_id INTEGER NOT NULL, 
	entity_id INTEGER NOT NULL, 
	value_text TEXT NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_custom_field_values PRIMARY KEY (id), 
	CONSTRAINT uq_custom_field_value UNIQUE (field_id, entity_id), 
	CONSTRAINT fk_custom_field_values_field_id_custom_fields FOREIGN KEY(field_id) REFERENCES custom_fields (id)
);

CREATE INDEX IF NOT EXISTS ix_custom_field_values_entity_id ON custom_field_values (entity_id);

CREATE INDEX IF NOT EXISTS ix_custom_field_values_field_id ON custom_field_values (field_id);
