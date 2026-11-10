-- Wave 3 additive migration; tools/migrate_wave3.py applies it in one transaction.
-- ENUMs use VARCHAR + CHECK, matching schema.sql.

CREATE TABLE IF NOT EXISTS discussion_threads (
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

CREATE INDEX IF NOT EXISTS ix_discussion_threads_course_id ON discussion_threads (course_id);

CREATE TABLE IF NOT EXISTS discussion_posts (
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

CREATE INDEX IF NOT EXISTS ix_discussion_posts_parent_id ON discussion_posts (parent_id);

CREATE INDEX IF NOT EXISTS ix_discussion_posts_thread_id ON discussion_posts (thread_id);

CREATE INDEX IF NOT EXISTS ix_discussion_posts_user_id ON discussion_posts (user_id);

CREATE TABLE IF NOT EXISTS forum_subscriptions (
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

CREATE INDEX IF NOT EXISTS ix_forum_subscriptions_thread_id ON forum_subscriptions (thread_id);

CREATE INDEX IF NOT EXISTS ix_forum_subscriptions_user_id ON forum_subscriptions (user_id);

CREATE TABLE IF NOT EXISTS channels (
	id SERIAL NOT NULL, 
	kind VARCHAR(8) NOT NULL, 
	title VARCHAR(160) NOT NULL, 
	division_id INTEGER, 
	created_by INTEGER NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_channels PRIMARY KEY (id), 
	CONSTRAINT ck_channels_channel_kind CHECK (kind IN ('private', 'group', 'division')), 
	CONSTRAINT fk_channels_division_id_divisions FOREIGN KEY(division_id) REFERENCES divisions (id), 
	CONSTRAINT fk_channels_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_channels_division_id ON channels (division_id);

CREATE INDEX IF NOT EXISTS ix_channels_kind ON channels (kind);

CREATE UNIQUE INDEX IF NOT EXISTS uq_division_channel ON channels (division_id) WHERE division_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS channel_members (
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

CREATE INDEX IF NOT EXISTS ix_channel_members_channel_id ON channel_members (channel_id);

CREATE INDEX IF NOT EXISTS ix_channel_members_user_id ON channel_members (user_id);

CREATE TABLE IF NOT EXISTS direct_contacts (
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

CREATE INDEX IF NOT EXISTS ix_direct_contacts_user_id ON direct_contacts (user_id);

CREATE TABLE IF NOT EXISTS message_blocks (
	id SERIAL NOT NULL, 
	blocker_id INTEGER NOT NULL, 
	blocked_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_message_blocks PRIMARY KEY (id), 
	CONSTRAINT uq_message_block UNIQUE (blocker_id, blocked_id), 
	CONSTRAINT fk_message_blocks_blocker_id_users FOREIGN KEY(blocker_id) REFERENCES users (id), 
	CONSTRAINT fk_message_blocks_blocked_id_users FOREIGN KEY(blocked_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_message_blocks_blocked_id ON message_blocks (blocked_id);

CREATE INDEX IF NOT EXISTS ix_message_blocks_blocker_id ON message_blocks (blocker_id);

CREATE TABLE IF NOT EXISTS attachments (
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

CREATE INDEX IF NOT EXISTS ix_attachments_owner_id ON attachments (owner_id);

CREATE TABLE IF NOT EXISTS stickers (
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

CREATE INDEX IF NOT EXISTS ix_stickers_owner_id ON stickers (owner_id);

CREATE INDEX IF NOT EXISTS ix_stickers_status ON stickers (status);

CREATE TABLE IF NOT EXISTS chat_messages (
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

CREATE INDEX IF NOT EXISTS ix_chat_channel_id_cursor ON chat_messages (channel_id, id);

CREATE INDEX IF NOT EXISTS ix_chat_messages_channel_id ON chat_messages (channel_id);

CREATE INDEX IF NOT EXISTS ix_chat_messages_sender_id ON chat_messages (sender_id);

CREATE TABLE IF NOT EXISTS profanity_words (
	id SERIAL NOT NULL, 
	word VARCHAR(120) NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	created_by INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_profanity_words PRIMARY KEY (id), 
	CONSTRAINT uq_profanity_words_word UNIQUE (word), 
	CONSTRAINT fk_profanity_words_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS content_reports (
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

CREATE INDEX IF NOT EXISTS ix_content_reports_reporter_id ON content_reports (reporter_id);

CREATE INDEX IF NOT EXISTS ix_content_reports_status ON content_reports (status);

CREATE TABLE IF NOT EXISTS moderation_actions (
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

CREATE INDEX IF NOT EXISTS ix_moderation_actions_actor_id ON moderation_actions (actor_id);

CREATE INDEX IF NOT EXISTS ix_moderation_actions_target_user_id ON moderation_actions (target_user_id);

CREATE TABLE IF NOT EXISTS moderation_strikes (
	user_id INTEGER NOT NULL, 
	count INTEGER NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_moderation_strikes PRIMARY KEY (user_id), 
	CONSTRAINT fk_moderation_strikes_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS user_restrictions (
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

CREATE INDEX IF NOT EXISTS ix_user_restrictions_user_id ON user_restrictions (user_id);

INSERT INTO site_settings (key, value) VALUES ('wave3.schema', '1') ON CONFLICT (key) DO NOTHING;
