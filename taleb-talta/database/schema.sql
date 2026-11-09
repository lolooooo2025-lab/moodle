-- Taleb Talta schema (PostgreSQL). Import into an already-selected database.
-- No CREATE DATABASE / USE. Generated from app/models by tools/genschema.py.

CREATE TABLE audit_log (
	id BIGSERIAL NOT NULL, 
	actor_id INTEGER, 
	actor_role VARCHAR(20) NOT NULL, 
	action VARCHAR(120) NOT NULL, 
	entity_type VARCHAR(60) NOT NULL, 
	entity_id VARCHAR(60) NOT NULL, 
	before_json JSON, 
	after_json JSON, 
	ip VARCHAR(64) NOT NULL, 
	user_agent VARCHAR(255) NOT NULL, 
	severity VARCHAR(8) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_audit_log PRIMARY KEY (id), 
	CONSTRAINT ck_audit_log_audit_severity CHECK (severity IN ('info', 'notice', 'warning', 'critical'))
);

CREATE INDEX ix_audit_log_action ON audit_log (action);

CREATE INDEX ix_audit_log_created_at ON audit_log (created_at);

CREATE TABLE course_categories (
	id SERIAL NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_course_categories PRIMARY KEY (id), 
	CONSTRAINT uq_course_categories_name UNIQUE (name)
);

CREATE TABLE dashboard_blocks (
	id SERIAL NOT NULL, 
	role VARCHAR(9) NOT NULL, 
	block_key VARCHAR(60) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	CONSTRAINT pk_dashboard_blocks PRIMARY KEY (id), 
	CONSTRAINT uq_dashboard_block UNIQUE (role, block_key), 
	CONSTRAINT ck_dashboard_blocks_user_role CHECK (role IN ('owner', 'admin', 'moderator', 'teacher', 'student', 'parent'))
);

CREATE TABLE divisions (
	id SERIAL NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_divisions PRIMARY KEY (id), 
	CONSTRAINT uq_divisions_name UNIQUE (name)
);

CREATE TABLE login_attempts (
	id BIGSERIAL NOT NULL, 
	phone VARCHAR(20) NOT NULL, 
	ip VARCHAR(64) NOT NULL, 
	success BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_login_attempts PRIMARY KEY (id)
);

CREATE INDEX ix_login_attempts_created_at ON login_attempts (created_at);

CREATE INDEX ix_login_attempts_ip ON login_attempts (ip);

CREATE INDEX ix_login_attempts_phone ON login_attempts (phone);

CREATE TABLE plugins (
	id SERIAL NOT NULL, 
	type VARCHAR(10) NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	component VARCHAR(120) NOT NULL, 
	disk_version INTEGER NOT NULL, 
	installed_version INTEGER NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	installed_at TIMESTAMP WITH TIME ZONE, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_plugins PRIMARY KEY (id), 
	CONSTRAINT uq_plugin_type_name UNIQUE (type, name), 
	CONSTRAINT ck_plugins_plugin_type CHECK (type IN ('block', 'tool', 'report', 'local', 'qtype', 'theme', 'filter', 'auth', 'enrol', 'repository', 'aiprovider')), 
	CONSTRAINT uq_plugins_component UNIQUE (component), 
	CONSTRAINT ck_plugins_plugin_status CHECK (status IN ('present', 'installed', 'enabled', 'disabled'))
);

CREATE TABLE rate_limits (
	id BIGSERIAL NOT NULL, 
	key VARCHAR(160) NOT NULL, 
	hits INTEGER NOT NULL, 
	window_start TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_rate_limits PRIMARY KEY (id)
);

CREATE INDEX ix_rate_limits_key ON rate_limits (key);

CREATE TABLE role_capabilities (
	id SERIAL NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	capability VARCHAR(120) NOT NULL, 
	permission VARCHAR(8) NOT NULL, 
	CONSTRAINT pk_role_capabilities PRIMARY KEY (id), 
	CONSTRAINT uq_role_cap UNIQUE (role, capability), 
	CONSTRAINT ck_role_capabilities_cap_permission CHECK (permission IN ('allow', 'prevent', 'prohibit'))
);

CREATE TABLE role_themes (
	role VARCHAR(9) NOT NULL, 
	theme_key VARCHAR(40) NOT NULL, 
	CONSTRAINT pk_role_themes PRIMARY KEY (role), 
	CONSTRAINT ck_role_themes_user_role CHECK (role IN ('owner', 'admin', 'moderator', 'teacher', 'student', 'parent'))
);

CREATE TABLE site_settings (
	key VARCHAR(120) NOT NULL, 
	value TEXT NOT NULL, 
	CONSTRAINT pk_site_settings PRIMARY KEY (key)
);

CREATE TABLE menu_items (
	id SERIAL NOT NULL, 
	label_key VARCHAR(120) NOT NULL, 
	label VARCHAR(120) NOT NULL, 
	url VARCHAR(255) NOT NULL, 
	icon VARCHAR(60) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	plugin_id INTEGER, 
	enabled BOOLEAN NOT NULL, 
	CONSTRAINT pk_menu_items PRIMARY KEY (id), 
	CONSTRAINT fk_menu_items_plugin_id_plugins FOREIGN KEY(plugin_id) REFERENCES plugins (id)
);

CREATE TABLE plugin_events (
	id SERIAL NOT NULL, 
	plugin_id INTEGER NOT NULL, 
	event VARCHAR(120) NOT NULL, 
	observer VARCHAR(255) NOT NULL, 
	CONSTRAINT pk_plugin_events PRIMARY KEY (id), 
	CONSTRAINT fk_plugin_events_plugin_id_plugins FOREIGN KEY(plugin_id) REFERENCES plugins (id)
);

CREATE INDEX ix_plugin_events_plugin_id ON plugin_events (plugin_id);

CREATE TABLE plugin_settings (
	id SERIAL NOT NULL, 
	plugin_id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	value TEXT NOT NULL, 
	CONSTRAINT pk_plugin_settings PRIMARY KEY (id), 
	CONSTRAINT uq_plugin_setting UNIQUE (plugin_id, name), 
	CONSTRAINT fk_plugin_settings_plugin_id_plugins FOREIGN KEY(plugin_id) REFERENCES plugins (id)
);

CREATE INDEX ix_plugin_settings_plugin_id ON plugin_settings (plugin_id);

CREATE TABLE scheduled_tasks (
	id SERIAL NOT NULL, 
	plugin_id INTEGER, 
	classname VARCHAR(255) NOT NULL, 
	minute VARCHAR(20) NOT NULL, 
	hour VARCHAR(20) NOT NULL, 
	day VARCHAR(20) NOT NULL, 
	dayofweek VARCHAR(20) NOT NULL, 
	month VARCHAR(20) NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	last_run TIMESTAMP WITH TIME ZONE, 
	next_run TIMESTAMP WITH TIME ZONE, 
	lock_token VARCHAR(64) NOT NULL, 
	locked_until TIMESTAMP WITH TIME ZONE, 
	CONSTRAINT pk_scheduled_tasks PRIMARY KEY (id), 
	CONSTRAINT fk_scheduled_tasks_plugin_id_plugins FOREIGN KEY(plugin_id) REFERENCES plugins (id), 
	CONSTRAINT uq_scheduled_tasks_classname UNIQUE (classname)
);

CREATE TABLE users (
	id SERIAL NOT NULL, 
	phone VARCHAR(20) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	guardian_phone VARCHAR(20) NOT NULL, 
	division_id INTEGER, 
	role VARCHAR(9) NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	title VARCHAR(120) NOT NULL, 
	badge VARCHAR(120) NOT NULL, 
	photo_path VARCHAR(255) NOT NULL, 
	failed_attempts INTEGER NOT NULL, 
	locked_until TIMESTAMP WITH TIME ZONE, 
	banned_until TIMESTAMP WITH TIME ZONE, 
	password_changed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_login TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_users PRIMARY KEY (id), 
	CONSTRAINT fk_users_division_id_divisions FOREIGN KEY(division_id) REFERENCES divisions (id), 
	CONSTRAINT ck_users_user_role CHECK (role IN ('owner', 'admin', 'moderator', 'teacher', 'student', 'parent')), 
	CONSTRAINT ck_users_user_status CHECK (status IN ('active', 'banned', 'suspended', 'pending'))
);

CREATE UNIQUE INDEX ix_users_phone ON users (phone);

CREATE TABLE attachments (
	id SERIAL NOT NULL, 
	owner_id INTEGER NOT NULL, 
	purpose VARCHAR(7) NOT NULL, 
	file_path VARCHAR(255) NOT NULL, 
	file_name VARCHAR(255) NOT NULL, 
	file_size BIGINT NOT NULL, 
	mime VARCHAR(120) NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_attachments PRIMARY KEY (id), 
	CONSTRAINT fk_attachments_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id), 
	CONSTRAINT ck_attachments_attachment_purpose CHECK (purpose IN ('chat', 'sticker')), 
	CONSTRAINT uq_attachments_file_path UNIQUE (file_path)
);

CREATE INDEX ix_attachments_owner_id ON attachments (owner_id);

CREATE TABLE backup_artifacts (
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

CREATE TABLE campaigns (
	id SERIAL NOT NULL, 
	week_date DATE NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	body TEXT NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	publish_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	published_at TIMESTAMP WITH TIME ZONE, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_campaigns PRIMARY KEY (id), 
	CONSTRAINT uq_campaigns_week_date UNIQUE (week_date), 
	CONSTRAINT ck_campaigns_campaign_status CHECK (status IN ('scheduled', 'published', 'cancelled')), 
	CONSTRAINT fk_campaigns_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_campaigns_publish_at ON campaigns (publish_at);

CREATE INDEX ix_campaigns_status ON campaigns (status);

CREATE TABLE channels (
	id SERIAL NOT NULL, 
	kind VARCHAR(8) NOT NULL, 
	title VARCHAR(160) NOT NULL, 
	division_id INTEGER, 
	created_by INTEGER NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_channels PRIMARY KEY (id), 
	CONSTRAINT ck_channels_channel_kind CHECK (kind IN ('private', 'group', 'division', 'live')), 
	CONSTRAINT fk_channels_division_id_divisions FOREIGN KEY(division_id) REFERENCES divisions (id), 
	CONSTRAINT fk_channels_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_channels_division_id ON channels (division_id);

CREATE INDEX ix_channels_kind ON channels (kind);

CREATE UNIQUE INDEX uq_division_channel ON channels (division_id) WHERE division_id IS NOT NULL;

CREATE TABLE content_reports (
	id SERIAL NOT NULL, 
	reporter_id INTEGER NOT NULL, 
	target_type VARCHAR(13) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	reason TEXT NOT NULL, 
	snapshot TEXT NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	reviewed_by INTEGER, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_content_reports PRIMARY KEY (id), 
	CONSTRAINT uq_content_report UNIQUE (reporter_id, target_type, entity_id), 
	CONSTRAINT fk_content_reports_reporter_id_users FOREIGN KEY(reporter_id) REFERENCES users (id), 
	CONSTRAINT ck_content_reports_report_entity CHECK (target_type IN ('forum_post', 'chat_message', 'question_post', 'sticker')), 
	CONSTRAINT ck_content_reports_report_status CHECK (status IN ('pending', 'resolved', 'dismissed')), 
	CONSTRAINT fk_content_reports_reviewed_by_users FOREIGN KEY(reviewed_by) REFERENCES users (id)
);

CREATE INDEX ix_content_reports_reporter_id ON content_reports (reporter_id);

CREATE INDEX ix_content_reports_status ON content_reports (status);

CREATE TABLE courses (
	id SERIAL NOT NULL, 
	category_id INTEGER, 
	division_id INTEGER, 
	title VARCHAR(200) NOT NULL, 
	summary TEXT NOT NULL, 
	teacher_id INTEGER, 
	visibility VARCHAR(7) NOT NULL, 
	available_from TIMESTAMP WITH TIME ZONE, 
	available_to TIMESTAMP WITH TIME ZONE, 
	price_cents INTEGER NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_courses PRIMARY KEY (id), 
	CONSTRAINT fk_courses_category_id_course_categories FOREIGN KEY(category_id) REFERENCES course_categories (id), 
	CONSTRAINT fk_courses_division_id_divisions FOREIGN KEY(division_id) REFERENCES divisions (id), 
	CONSTRAINT fk_courses_teacher_id_users FOREIGN KEY(teacher_id) REFERENCES users (id), 
	CONSTRAINT ck_courses_course_visibility CHECK (visibility IN ('visible', 'hidden'))
);

CREATE TABLE custom_fields (
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

CREATE INDEX ix_custom_fields_applies_to ON custom_fields (applies_to);

CREATE TABLE dashboard_preferences (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	block_key VARCHAR(60) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	CONSTRAINT pk_dashboard_preferences PRIMARY KEY (id), 
	CONSTRAINT uq_dashboard_preference UNIQUE (user_id, block_key), 
	CONSTRAINT fk_dashboard_preferences_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_dashboard_preferences_user_id ON dashboard_preferences (user_id);

CREATE TABLE digest_deliveries (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	period_date VARCHAR(10) NOT NULL, 
	payload_json JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_digest_deliveries PRIMARY KEY (id), 
	CONSTRAINT uq_digest_user_day UNIQUE (user_id, period_date), 
	CONSTRAINT fk_digest_deliveries_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_digest_deliveries_user_id ON digest_deliveries (user_id);

CREATE TABLE library_items (
	id SERIAL NOT NULL, 
	uploader_id INTEGER NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	description TEXT NOT NULL, 
	category VARCHAR(120) NOT NULL, 
	division_id INTEGER, 
	file_path VARCHAR(255) NOT NULL, 
	file_name VARCHAR(255) NOT NULL, 
	file_size BIGINT NOT NULL, 
	mime VARCHAR(120) NOT NULL, 
	status VARCHAR(8) NOT NULL, 
	review_reason TEXT NOT NULL, 
	reviewed_by INTEGER, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	download_count INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_library_items PRIMARY KEY (id), 
	CONSTRAINT fk_library_items_uploader_id_users FOREIGN KEY(uploader_id) REFERENCES users (id), 
	CONSTRAINT fk_library_items_division_id_divisions FOREIGN KEY(division_id) REFERENCES divisions (id), 
	CONSTRAINT ck_library_items_library_status CHECK (status IN ('pending', 'approved', 'rejected')), 
	CONSTRAINT fk_library_items_reviewed_by_users FOREIGN KEY(reviewed_by) REFERENCES users (id)
);

CREATE INDEX ix_library_items_status ON library_items (status);

CREATE INDEX ix_library_items_uploader_id ON library_items (uploader_id);

CREATE TABLE message_blocks (
	id SERIAL NOT NULL, 
	blocker_id INTEGER NOT NULL, 
	blocked_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_message_blocks PRIMARY KEY (id), 
	CONSTRAINT uq_message_block UNIQUE (blocker_id, blocked_id), 
	CONSTRAINT fk_message_blocks_blocker_id_users FOREIGN KEY(blocker_id) REFERENCES users (id), 
	CONSTRAINT fk_message_blocks_blocked_id_users FOREIGN KEY(blocked_id) REFERENCES users (id)
);

CREATE INDEX ix_message_blocks_blocked_id ON message_blocks (blocked_id);

CREATE INDEX ix_message_blocks_blocker_id ON message_blocks (blocker_id);

CREATE TABLE moderation_strikes (
	user_id INTEGER NOT NULL, 
	count INTEGER NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_moderation_strikes PRIMARY KEY (user_id), 
	CONSTRAINT fk_moderation_strikes_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE password_history (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_password_history PRIMARY KEY (id), 
	CONSTRAINT fk_password_history_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_password_history_user_id ON password_history (user_id);

CREATE TABLE password_reset_tokens (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	status VARCHAR(7) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_password_reset_tokens PRIMARY KEY (id), 
	CONSTRAINT fk_password_reset_tokens_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT uq_password_reset_tokens_token_hash UNIQUE (token_hash), 
	CONSTRAINT ck_password_reset_tokens_reset_status CHECK (status IN ('pending', 'used', 'expired'))
);

CREATE INDEX ix_password_reset_tokens_user_id ON password_reset_tokens (user_id);

CREATE TABLE profanity_words (
	id SERIAL NOT NULL, 
	word VARCHAR(120) NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_profanity_words PRIMARY KEY (id), 
	CONSTRAINT uq_profanity_words_word UNIQUE (word), 
	CONSTRAINT fk_profanity_words_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE push_subscriptions (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	endpoint TEXT NOT NULL, 
	p256dh VARCHAR(255) NOT NULL, 
	auth VARCHAR(255) NOT NULL, 
	user_agent VARCHAR(255) NOT NULL, 
	failure_count INTEGER NOT NULL, 
	last_success TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_push_subscriptions PRIMARY KEY (id), 
	CONSTRAINT fk_push_subscriptions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT uq_push_subscriptions_endpoint UNIQUE (endpoint)
);

CREATE INDEX ix_push_subscriptions_user_id ON push_subscriptions (user_id);

CREATE TABLE sessions (
	id VARCHAR(64) NOT NULL, 
	user_id INTEGER NOT NULL, 
	sesskey VARCHAR(64) NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	ip VARCHAR(64) NOT NULL, 
	user_agent VARCHAR(255) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE NOT NULL, 
	absolute_expires TIMESTAMP WITH TIME ZONE NOT NULL, 
	revoked BOOLEAN NOT NULL, 
	CONSTRAINT pk_sessions PRIMARY KEY (id), 
	CONSTRAINT fk_sessions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_sessions_user_id ON sessions (user_id);

CREATE TABLE task_runs (
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

CREATE INDEX ix_task_runs_task_id ON task_runs (task_id);

CREATE INDEX ix_task_runs_task_key ON task_runs (task_key);

CREATE TABLE theme_presets (
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

CREATE TABLE user_capability_overrides (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	capability VARCHAR(120) NOT NULL, 
	permission VARCHAR(8) NOT NULL, 
	CONSTRAINT pk_user_capability_overrides PRIMARY KEY (id), 
	CONSTRAINT uq_user_cap UNIQUE (user_id, capability), 
	CONSTRAINT fk_user_capability_overrides_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT ck_user_capability_overrides_cap_permission CHECK (permission IN ('allow', 'prevent', 'prohibit'))
);

CREATE INDEX ix_user_capability_overrides_user_id ON user_capability_overrides (user_id);

CREATE TABLE user_restrictions (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	scope VARCHAR(16) NOT NULL, 
	reason TEXT NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	revoked_at TIMESTAMP WITH TIME ZONE, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_user_restrictions PRIMARY KEY (id), 
	CONSTRAINT fk_user_restrictions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT ck_user_restrictions_restriction_scope CHECK (scope IN ('chat_evaluations', 'all')), 
	CONSTRAINT fk_user_restrictions_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_user_restrictions_user_id ON user_restrictions (user_id);

CREATE TABLE channel_members (
	id SERIAL NOT NULL, 
	channel_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	last_read_message_id INTEGER NOT NULL, 
	joined_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_channel_members PRIMARY KEY (id), 
	CONSTRAINT uq_channel_member UNIQUE (channel_id, user_id), 
	CONSTRAINT fk_channel_members_channel_id_channels FOREIGN KEY(channel_id) REFERENCES channels (id), 
	CONSTRAINT fk_channel_members_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_channel_members_channel_id ON channel_members (channel_id);

CREATE INDEX ix_channel_members_user_id ON channel_members (user_id);

CREATE TABLE course_sections (
	id SERIAL NOT NULL, 
	course_id INTEGER NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	summary TEXT NOT NULL, 
	sort_order INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_course_sections PRIMARY KEY (id), 
	CONSTRAINT fk_course_sections_course_id_courses FOREIGN KEY(course_id) REFERENCES courses (id)
);

CREATE INDEX ix_course_sections_course_id ON course_sections (course_id);

CREATE TABLE course_students (
	id SERIAL NOT NULL, 
	course_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	method VARCHAR(8) NOT NULL, 
	enrolled_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_course_students PRIMARY KEY (id), 
	CONSTRAINT uq_course_student UNIQUE (course_id, user_id), 
	CONSTRAINT fk_course_students_course_id_courses FOREIGN KEY(course_id) REFERENCES courses (id), 
	CONSTRAINT fk_course_students_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT ck_course_students_enrol_method CHECK (method IN ('division', 'self', 'manual', 'purchase'))
);

CREATE INDEX ix_course_students_course_id ON course_students (course_id);

CREATE INDEX ix_course_students_user_id ON course_students (user_id);

CREATE TABLE custom_field_values (
	id SERIAL NOT NULL, 
	field_id INTEGER NOT NULL, 
	entity_id INTEGER NOT NULL, 
	value_text TEXT NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_custom_field_values PRIMARY KEY (id), 
	CONSTRAINT uq_custom_field_value UNIQUE (field_id, entity_id), 
	CONSTRAINT fk_custom_field_values_field_id_custom_fields FOREIGN KEY(field_id) REFERENCES custom_fields (id)
);

CREATE INDEX ix_custom_field_values_entity_id ON custom_field_values (entity_id);

CREATE INDEX ix_custom_field_values_field_id ON custom_field_values (field_id);

CREATE TABLE direct_contacts (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	contact_id INTEGER NOT NULL, 
	channel_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_direct_contacts PRIMARY KEY (id), 
	CONSTRAINT uq_direct_contact UNIQUE (user_id, contact_id), 
	CONSTRAINT fk_direct_contacts_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT fk_direct_contacts_contact_id_users FOREIGN KEY(contact_id) REFERENCES users (id), 
	CONSTRAINT fk_direct_contacts_channel_id_channels FOREIGN KEY(channel_id) REFERENCES channels (id)
);

CREATE INDEX ix_direct_contacts_user_id ON direct_contacts (user_id);

CREATE TABLE exams (
	id SERIAL NOT NULL, 
	course_id INTEGER NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	description TEXT NOT NULL, 
	time_limit_minutes INTEGER NOT NULL, 
	max_attempts INTEGER NOT NULL, 
	visibility VARCHAR(7) NOT NULL, 
	available_from TIMESTAMP WITH TIME ZONE, 
	available_to TIMESTAMP WITH TIME ZONE, 
	shuffle BOOLEAN NOT NULL, 
	created_by INTEGER NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_exams PRIMARY KEY (id), 
	CONSTRAINT fk_exams_course_id_courses FOREIGN KEY(course_id) REFERENCES courses (id), 
	CONSTRAINT ck_exams_course_visibility CHECK (visibility IN ('visible', 'hidden')), 
	CONSTRAINT fk_exams_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_exams_course_id ON exams (course_id);

CREATE TABLE live_streams (
	id SERIAL NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	description TEXT NOT NULL, 
	audience VARCHAR(20) NOT NULL, 
	course_id INTEGER, 
	division_id INTEGER, 
	scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	ended_at TIMESTAMP WITH TIME ZONE, 
	playback_url TEXT NOT NULL, 
	ingest_url_encrypted TEXT NOT NULL, 
	publish_key_encrypted TEXT NOT NULL, 
	chat_channel_id INTEGER, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_live_streams PRIMARY KEY (id), 
	CONSTRAINT fk_live_streams_course_id_courses FOREIGN KEY(course_id) REFERENCES courses (id), 
	CONSTRAINT fk_live_streams_division_id_divisions FOREIGN KEY(division_id) REFERENCES divisions (id), 
	CONSTRAINT ck_live_streams_stream_status CHECK (status IN ('scheduled', 'live', 'ended', 'cancelled')), 
	CONSTRAINT uq_live_streams_chat_channel_id UNIQUE (chat_channel_id), 
	CONSTRAINT fk_live_streams_chat_channel_id_channels FOREIGN KEY(chat_channel_id) REFERENCES channels (id), 
	CONSTRAINT fk_live_streams_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_live_streams_scheduled_at ON live_streams (scheduled_at);

CREATE INDEX ix_live_streams_status ON live_streams (status);

CREATE TABLE moderation_actions (
	id SERIAL NOT NULL, 
	actor_id INTEGER NOT NULL, 
	target_user_id INTEGER, 
	report_id INTEGER, 
	decision VARCHAR(7) NOT NULL, 
	reason TEXT NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_moderation_actions PRIMARY KEY (id), 
	CONSTRAINT fk_moderation_actions_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id), 
	CONSTRAINT fk_moderation_actions_target_user_id_users FOREIGN KEY(target_user_id) REFERENCES users (id), 
	CONSTRAINT fk_moderation_actions_report_id_content_reports FOREIGN KEY(report_id) REFERENCES content_reports (id), 
	CONSTRAINT ck_moderation_actions_moderation_decision CHECK (decision IN ('approve', 'remove', 'warn', 'ban'))
);

CREATE INDEX ix_moderation_actions_actor_id ON moderation_actions (actor_id);

CREATE INDEX ix_moderation_actions_target_user_id ON moderation_actions (target_user_id);

CREATE TABLE notifications (
	id SERIAL NOT NULL, 
	kind VARCHAR(8) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	body TEXT NOT NULL, 
	url VARCHAR(255) NOT NULL, 
	audience_role VARCHAR(20) NOT NULL, 
	division_id INTEGER, 
	course_id INTEGER, 
	user_id INTEGER, 
	campaign_id INTEGER, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_notifications PRIMARY KEY (id), 
	CONSTRAINT ck_notifications_notification_kind CHECK (kind IN ('targeted', 'campaign', 'purchase', 'system')), 
	CONSTRAINT fk_notifications_division_id_divisions FOREIGN KEY(division_id) REFERENCES divisions (id), 
	CONSTRAINT fk_notifications_course_id_courses FOREIGN KEY(course_id) REFERENCES courses (id), 
	CONSTRAINT fk_notifications_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT uq_notifications_campaign_id UNIQUE (campaign_id), 
	CONSTRAINT fk_notifications_campaign_id_campaigns FOREIGN KEY(campaign_id) REFERENCES campaigns (id), 
	CONSTRAINT fk_notifications_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_notifications_created_at ON notifications (created_at);

CREATE INDEX ix_notifications_kind ON notifications (kind);

CREATE TABLE questions (
	id SERIAL NOT NULL, 
	course_id INTEGER, 
	qtype VARCHAR(10) NOT NULL, 
	prompt TEXT NOT NULL, 
	options_json JSON, 
	answer_json JSON, 
	explanation TEXT NOT NULL, 
	created_by INTEGER NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_questions PRIMARY KEY (id), 
	CONSTRAINT fk_questions_course_id_courses FOREIGN KEY(course_id) REFERENCES courses (id), 
	CONSTRAINT ck_questions_question_type CHECK (qtype IN ('mcq_single', 'mcq_multi', 'truefalse', 'short', 'match', 'numeric')), 
	CONSTRAINT fk_questions_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_questions_course_id ON questions (course_id);

CREATE TABLE stickers (
	id SERIAL NOT NULL, 
	owner_id INTEGER NOT NULL, 
	attachment_id INTEGER NOT NULL, 
	title VARCHAR(120) NOT NULL, 
	status VARCHAR(8) NOT NULL, 
	review_reason TEXT NOT NULL, 
	reviewed_by INTEGER, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_stickers PRIMARY KEY (id), 
	CONSTRAINT fk_stickers_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id), 
	CONSTRAINT uq_stickers_attachment_id UNIQUE (attachment_id), 
	CONSTRAINT fk_stickers_attachment_id_attachments FOREIGN KEY(attachment_id) REFERENCES attachments (id), 
	CONSTRAINT ck_stickers_sticker_status CHECK (status IN ('pending', 'approved', 'rejected')), 
	CONSTRAINT fk_stickers_reviewed_by_users FOREIGN KEY(reviewed_by) REFERENCES users (id)
);

CREATE INDEX ix_stickers_owner_id ON stickers (owner_id);

CREATE INDEX ix_stickers_status ON stickers (status);

CREATE TABLE user_library (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	library_item_id INTEGER NOT NULL, 
	saved_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_user_library PRIMARY KEY (id), 
	CONSTRAINT uq_user_library UNIQUE (user_id, library_item_id), 
	CONSTRAINT fk_user_library_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT fk_user_library_library_item_id_library_items FOREIGN KEY(library_item_id) REFERENCES library_items (id)
);

CREATE INDEX ix_user_library_library_item_id ON user_library (library_item_id);

CREATE INDEX ix_user_library_user_id ON user_library (user_id);

CREATE TABLE chat_messages (
	id SERIAL NOT NULL, 
	channel_id INTEGER NOT NULL, 
	sender_id INTEGER NOT NULL, 
	body TEXT NOT NULL, 
	attachment_id INTEGER, 
	sticker_id INTEGER, 
	was_filtered BOOLEAN NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_chat_messages PRIMARY KEY (id), 
	CONSTRAINT fk_chat_messages_channel_id_channels FOREIGN KEY(channel_id) REFERENCES channels (id), 
	CONSTRAINT fk_chat_messages_sender_id_users FOREIGN KEY(sender_id) REFERENCES users (id), 
	CONSTRAINT uq_chat_messages_attachment_id UNIQUE (attachment_id), 
	CONSTRAINT fk_chat_messages_attachment_id_attachments FOREIGN KEY(attachment_id) REFERENCES attachments (id), 
	CONSTRAINT fk_chat_messages_sticker_id_stickers FOREIGN KEY(sticker_id) REFERENCES stickers (id)
);

CREATE INDEX ix_chat_channel_id_cursor ON chat_messages (channel_id, id);

CREATE INDEX ix_chat_messages_channel_id ON chat_messages (channel_id);

CREATE INDEX ix_chat_messages_sender_id ON chat_messages (sender_id);

CREATE TABLE discussion_threads (
	id SERIAL NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	course_id INTEGER, 
	question_id INTEGER, 
	exam_id INTEGER, 
	created_by INTEGER NOT NULL, 
	locked BOOLEAN NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_discussion_threads PRIMARY KEY (id), 
	CONSTRAINT fk_discussion_threads_course_id_courses FOREIGN KEY(course_id) REFERENCES courses (id), 
	CONSTRAINT uq_discussion_threads_question_id UNIQUE (question_id), 
	CONSTRAINT fk_discussion_threads_question_id_questions FOREIGN KEY(question_id) REFERENCES questions (id), 
	CONSTRAINT fk_discussion_threads_exam_id_exams FOREIGN KEY(exam_id) REFERENCES exams (id), 
	CONSTRAINT fk_discussion_threads_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_discussion_threads_course_id ON discussion_threads (course_id);

CREATE TABLE exam_attempts (
	id SERIAL NOT NULL, 
	exam_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	attempt_number INTEGER NOT NULL, 
	status VARCHAR(11) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE, 
	submitted_at TIMESTAMP WITH TIME ZONE, 
	score FLOAT NOT NULL, 
	max_score FLOAT NOT NULL, 
	graded_by INTEGER, 
	graded_at TIMESTAMP WITH TIME ZONE, 
	CONSTRAINT pk_exam_attempts PRIMARY KEY (id), 
	CONSTRAINT uq_attempt_number UNIQUE (exam_id, user_id, attempt_number), 
	CONSTRAINT fk_exam_attempts_exam_id_exams FOREIGN KEY(exam_id) REFERENCES exams (id), 
	CONSTRAINT fk_exam_attempts_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT ck_exam_attempts_attempt_status CHECK (status IN ('in_progress', 'submitted', 'graded')), 
	CONSTRAINT fk_exam_attempts_graded_by_users FOREIGN KEY(graded_by) REFERENCES users (id)
);

CREATE INDEX ix_exam_attempts_exam_id ON exam_attempts (exam_id);

CREATE INDEX ix_exam_attempts_user_id ON exam_attempts (user_id);

CREATE TABLE exam_questions (
	id SERIAL NOT NULL, 
	exam_id INTEGER NOT NULL, 
	question_id INTEGER NOT NULL, 
	sort_order INTEGER NOT NULL, 
	points INTEGER NOT NULL, 
	CONSTRAINT pk_exam_questions PRIMARY KEY (id), 
	CONSTRAINT uq_exam_question UNIQUE (exam_id, question_id), 
	CONSTRAINT fk_exam_questions_exam_id_exams FOREIGN KEY(exam_id) REFERENCES exams (id), 
	CONSTRAINT fk_exam_questions_question_id_questions FOREIGN KEY(question_id) REFERENCES questions (id)
);

CREATE INDEX ix_exam_questions_exam_id ON exam_questions (exam_id);

CREATE INDEX ix_exam_questions_question_id ON exam_questions (question_id);

CREATE TABLE lessons (
	id SERIAL NOT NULL, 
	section_id INTEGER NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	summary TEXT NOT NULL, 
	price_cents INTEGER NOT NULL, 
	sort_order INTEGER NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_lessons PRIMARY KEY (id), 
	CONSTRAINT fk_lessons_section_id_course_sections FOREIGN KEY(section_id) REFERENCES course_sections (id)
);

CREATE INDEX ix_lessons_section_id ON lessons (section_id);

CREATE TABLE notification_recipients (
	id SERIAL NOT NULL, 
	notification_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	read_at TIMESTAMP WITH TIME ZONE, 
	push_status VARCHAR(7) NOT NULL, 
	push_attempted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_notification_recipients PRIMARY KEY (id), 
	CONSTRAINT uq_notification_recipient UNIQUE (notification_id, user_id), 
	CONSTRAINT fk_notification_recipients_notification_id_notifications FOREIGN KEY(notification_id) REFERENCES notifications (id), 
	CONSTRAINT fk_notification_recipients_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT ck_notification_recipients_push_status CHECK (push_status IN ('pending', 'sent', 'failed', 'skipped'))
);

CREATE INDEX ix_notification_recipients_notification_id ON notification_recipients (notification_id);

CREATE INDEX ix_notification_recipients_push_status ON notification_recipients (push_status);

CREATE INDEX ix_notification_recipients_user_id ON notification_recipients (user_id);

CREATE TABLE question_posts (
	id SERIAL NOT NULL, 
	question_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	body TEXT NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_question_posts PRIMARY KEY (id), 
	CONSTRAINT fk_question_posts_question_id_questions FOREIGN KEY(question_id) REFERENCES questions (id), 
	CONSTRAINT fk_question_posts_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_question_posts_question_id ON question_posts (question_id);

CREATE INDEX ix_question_posts_user_id ON question_posts (user_id);

CREATE TABLE attempt_answers (
	id SERIAL NOT NULL, 
	attempt_id INTEGER NOT NULL, 
	question_id INTEGER NOT NULL, 
	response_json JSON, 
	is_correct BOOLEAN, 
	points_awarded FLOAT NOT NULL, 
	needs_manual BOOLEAN NOT NULL, 
	CONSTRAINT pk_attempt_answers PRIMARY KEY (id), 
	CONSTRAINT uq_attempt_answer UNIQUE (attempt_id, question_id), 
	CONSTRAINT fk_attempt_answers_attempt_id_exam_attempts FOREIGN KEY(attempt_id) REFERENCES exam_attempts (id), 
	CONSTRAINT fk_attempt_answers_question_id_questions FOREIGN KEY(question_id) REFERENCES questions (id)
);

CREATE INDEX ix_attempt_answers_attempt_id ON attempt_answers (attempt_id);

CREATE INDEX ix_attempt_answers_question_id ON attempt_answers (question_id);

CREATE TABLE discussion_posts (
	id SERIAL NOT NULL, 
	thread_id INTEGER NOT NULL, 
	parent_id INTEGER, 
	user_id INTEGER NOT NULL, 
	body TEXT NOT NULL, 
	was_filtered BOOLEAN NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_discussion_posts PRIMARY KEY (id), 
	CONSTRAINT fk_discussion_posts_thread_id_discussion_threads FOREIGN KEY(thread_id) REFERENCES discussion_threads (id), 
	CONSTRAINT fk_discussion_posts_parent_id_discussion_posts FOREIGN KEY(parent_id) REFERENCES discussion_posts (id), 
	CONSTRAINT fk_discussion_posts_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_discussion_posts_parent_id ON discussion_posts (parent_id);

CREATE INDEX ix_discussion_posts_thread_id ON discussion_posts (thread_id);

CREATE INDEX ix_discussion_posts_user_id ON discussion_posts (user_id);

CREATE TABLE forum_subscriptions (
	id SERIAL NOT NULL, 
	thread_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	last_seen_post_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_forum_subscriptions PRIMARY KEY (id), 
	CONSTRAINT uq_forum_subscription UNIQUE (thread_id, user_id), 
	CONSTRAINT fk_forum_subscriptions_thread_id_discussion_threads FOREIGN KEY(thread_id) REFERENCES discussion_threads (id), 
	CONSTRAINT fk_forum_subscriptions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_forum_subscriptions_thread_id ON forum_subscriptions (thread_id);

CREATE INDEX ix_forum_subscriptions_user_id ON forum_subscriptions (user_id);

CREATE TABLE lesson_items (
	id SERIAL NOT NULL, 
	lesson_id INTEGER NOT NULL, 
	item_type VARCHAR(8) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	body TEXT NOT NULL, 
	url VARCHAR(500) NOT NULL, 
	file_path VARCHAR(255) NOT NULL, 
	file_name VARCHAR(255) NOT NULL, 
	options_json JSON, 
	correct_index INTEGER, 
	sort_order INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_lesson_items PRIMARY KEY (id), 
	CONSTRAINT fk_lesson_items_lesson_id_lessons FOREIGN KEY(lesson_id) REFERENCES lessons (id), 
	CONSTRAINT ck_lesson_items_lesson_item_type CHECK (item_type IN ('text', 'file', 'link', 'question'))
);

CREATE INDEX ix_lesson_items_lesson_id ON lesson_items (lesson_id);

CREATE TABLE purchases (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	course_id INTEGER NOT NULL, 
	lesson_id INTEGER, 
	amount_cents INTEGER NOT NULL, 
	currency VARCHAR(3) NOT NULL, 
	status VARCHAR(9) NOT NULL, 
	reference VARCHAR(120) NOT NULL, 
	note TEXT NOT NULL, 
	reviewed_by INTEGER, 
	review_note TEXT NOT NULL, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_purchases PRIMARY KEY (id), 
	CONSTRAINT fk_purchases_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT fk_purchases_course_id_courses FOREIGN KEY(course_id) REFERENCES courses (id), 
	CONSTRAINT fk_purchases_lesson_id_lessons FOREIGN KEY(lesson_id) REFERENCES lessons (id), 
	CONSTRAINT ck_purchases_purchase_status CHECK (status IN ('pending', 'confirmed', 'rejected', 'cancelled')), 
	CONSTRAINT fk_purchases_reviewed_by_users FOREIGN KEY(reviewed_by) REFERENCES users (id)
);

CREATE INDEX ix_purchases_course_id ON purchases (course_id);

CREATE INDEX ix_purchases_created_at ON purchases (created_at);

CREATE INDEX ix_purchases_lesson_id ON purchases (lesson_id);

CREATE INDEX ix_purchases_status ON purchases (status);

CREATE INDEX ix_purchases_user_id ON purchases (user_id);

CREATE UNIQUE INDEX uq_purchase_pending_course ON purchases (user_id, course_id) WHERE lesson_id IS NULL AND status = 'pending';

CREATE UNIQUE INDEX uq_purchase_pending_lesson ON purchases (user_id, lesson_id) WHERE lesson_id IS NOT NULL AND status = 'pending';

CREATE TABLE lesson_progress (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	lesson_id INTEGER NOT NULL, 
	item_id INTEGER, 
	completed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_lesson_progress PRIMARY KEY (id), 
	CONSTRAINT uq_progress_user_item UNIQUE (user_id, item_id), 
	CONSTRAINT fk_lesson_progress_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT fk_lesson_progress_lesson_id_lessons FOREIGN KEY(lesson_id) REFERENCES lessons (id), 
	CONSTRAINT fk_lesson_progress_item_id_lesson_items FOREIGN KEY(item_id) REFERENCES lesson_items (id)
);

CREATE INDEX ix_lesson_progress_lesson_id ON lesson_progress (lesson_id);

CREATE INDEX ix_lesson_progress_user_id ON lesson_progress (user_id);
