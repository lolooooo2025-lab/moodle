-- Wave 5: manual purchases, notifications/campaigns, Web Push and live streams.
-- Additive and idempotent. PostgreSQL only. No payment gateway is involved.
-- Definitions below are generated from the ORM; the repair block also upgrades
-- databases that applied the first draft of this migration. All DDL runs in one
-- transaction, so constraint replacement is atomic.
ALTER TABLE lessons ADD COLUMN IF NOT EXISTS price_cents INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lessons DROP CONSTRAINT IF EXISTS ck_lessons_price_cents;
ALTER TABLE lessons ADD CONSTRAINT ck_lessons_price_cents CHECK (price_cents >= 0);
ALTER TABLE channels DROP CONSTRAINT IF EXISTS ck_channels_channel_kind;
ALTER TABLE channels ADD CONSTRAINT ck_channels_channel_kind CHECK (kind IN ('private','group','division','live'));
ALTER TABLE course_students DROP CONSTRAINT IF EXISTS ck_course_students_enrol_method;
ALTER TABLE course_students ADD CONSTRAINT ck_course_students_enrol_method CHECK (method IN ('division','self','manual','purchase'));


CREATE TABLE IF NOT EXISTS purchases (
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

CREATE TABLE IF NOT EXISTS campaigns (
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

CREATE TABLE IF NOT EXISTS notifications (
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

CREATE TABLE IF NOT EXISTS notification_recipients (
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

CREATE TABLE IF NOT EXISTS push_subscriptions (
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

CREATE TABLE IF NOT EXISTS live_streams (
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

CREATE INDEX IF NOT EXISTS ix_campaigns_publish_at ON campaigns (publish_at);

CREATE INDEX IF NOT EXISTS ix_campaigns_status ON campaigns (status);

CREATE INDEX IF NOT EXISTS ix_push_subscriptions_user_id ON push_subscriptions (user_id);

CREATE INDEX IF NOT EXISTS ix_live_streams_scheduled_at ON live_streams (scheduled_at);

CREATE INDEX IF NOT EXISTS ix_live_streams_status ON live_streams (status);

CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications (created_at);

CREATE INDEX IF NOT EXISTS ix_notifications_kind ON notifications (kind);

CREATE INDEX IF NOT EXISTS ix_notification_recipients_notification_id ON notification_recipients (notification_id);

CREATE INDEX IF NOT EXISTS ix_notification_recipients_push_status ON notification_recipients (push_status);

CREATE INDEX IF NOT EXISTS ix_notification_recipients_user_id ON notification_recipients (user_id);

CREATE INDEX IF NOT EXISTS ix_purchases_course_id ON purchases (course_id);

CREATE INDEX IF NOT EXISTS ix_purchases_created_at ON purchases (created_at);

CREATE INDEX IF NOT EXISTS ix_purchases_lesson_id ON purchases (lesson_id);

CREATE INDEX IF NOT EXISTS ix_purchases_status ON purchases (status);

CREATE INDEX IF NOT EXISTS ix_purchases_user_id ON purchases (user_id);


-- Drop legacy incoming FKs before replacing their referenced primary keys.
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_campaign_id_fkey;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS fk_notifications_campaign_id_campaigns;
ALTER TABLE notification_recipients DROP CONSTRAINT IF EXISTS fk_notification_recipients_notification_id_notifications;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_division_id_fkey;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_course_id_fkey;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_user_id_fkey;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_created_by_fkey;
ALTER TABLE notification_recipients DROP CONSTRAINT IF EXISTS notification_recipients_notification_id_fkey;
ALTER TABLE notification_recipients DROP CONSTRAINT IF EXISTS notification_recipients_user_id_fkey;
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS purchases_user_id_fkey;
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS purchases_course_id_fkey;
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS purchases_lesson_id_fkey;
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS purchases_reviewed_by_fkey;
ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS campaigns_created_by_fkey;
ALTER TABLE push_subscriptions DROP CONSTRAINT IF EXISTS push_subscriptions_user_id_fkey;
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS live_streams_course_id_fkey;
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS live_streams_division_id_fkey;
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS live_streams_chat_channel_id_fkey;
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS live_streams_created_by_fkey;

-- Repair the first-draft column types/nullability (safe narrowing: API limits
-- already enforced these lengths; a legacy violation aborts the transaction).
ALTER TABLE purchases ALTER COLUMN status TYPE VARCHAR(9);
ALTER TABLE campaigns ALTER COLUMN status TYPE VARCHAR(9);
ALTER TABLE campaigns ALTER COLUMN created_by SET NOT NULL;
ALTER TABLE notifications ALTER COLUMN kind TYPE VARCHAR(8);
ALTER TABLE notifications ALTER COLUMN audience_role TYPE VARCHAR(20);
ALTER TABLE notification_recipients ALTER COLUMN push_status TYPE VARCHAR(7);
ALTER TABLE push_subscriptions ALTER COLUMN endpoint TYPE TEXT;
ALTER TABLE push_subscriptions ALTER COLUMN p256dh TYPE VARCHAR(255);
ALTER TABLE push_subscriptions ALTER COLUMN auth TYPE VARCHAR(255);
ALTER TABLE live_streams ALTER COLUMN audience TYPE VARCHAR(20);
ALTER TABLE live_streams ALTER COLUMN status TYPE VARCHAR(9);
ALTER TABLE live_streams ALTER COLUMN playback_url TYPE TEXT;
ALTER TABLE live_streams ALTER COLUMN created_by SET NOT NULL;

-- Replace first-draft constraint names/semantics with the ORM contract.
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS purchases_pkey;
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS ck_purchases_status;
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS ck_purchases_amount_cents;
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS ck_purchases_currency;
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS purchases_user_id_fkey;
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS purchases_course_id_fkey;
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS purchases_lesson_id_fkey;
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS purchases_reviewed_by_fkey;
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS pk_purchases;
ALTER TABLE purchases ADD CONSTRAINT pk_purchases PRIMARY KEY (id);
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS fk_purchases_user_id_users;
ALTER TABLE purchases ADD CONSTRAINT fk_purchases_user_id_users FOREIGN KEY(user_id) REFERENCES users (id);
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS fk_purchases_course_id_courses;
ALTER TABLE purchases ADD CONSTRAINT fk_purchases_course_id_courses FOREIGN KEY(course_id) REFERENCES courses (id);
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS fk_purchases_lesson_id_lessons;
ALTER TABLE purchases ADD CONSTRAINT fk_purchases_lesson_id_lessons FOREIGN KEY(lesson_id) REFERENCES lessons (id);
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS fk_purchases_reviewed_by_users;
ALTER TABLE purchases ADD CONSTRAINT fk_purchases_reviewed_by_users FOREIGN KEY(reviewed_by) REFERENCES users (id);
ALTER TABLE purchases DROP CONSTRAINT IF EXISTS ck_purchases_purchase_status;
ALTER TABLE purchases ADD CONSTRAINT ck_purchases_purchase_status CHECK (status IN ('pending', 'confirmed', 'rejected', 'cancelled'));

ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS campaigns_pkey;
ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS campaigns_week_date_key;
ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS ck_campaigns_status;
ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS campaigns_created_by_fkey;
ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS pk_campaigns;
ALTER TABLE campaigns ADD CONSTRAINT pk_campaigns PRIMARY KEY (id);
ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS uq_campaigns_week_date;
ALTER TABLE campaigns ADD CONSTRAINT uq_campaigns_week_date UNIQUE (week_date);
ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS ck_campaigns_campaign_status;
ALTER TABLE campaigns ADD CONSTRAINT ck_campaigns_campaign_status CHECK (status IN ('scheduled', 'published', 'cancelled'));
ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS fk_campaigns_created_by_users;
ALTER TABLE campaigns ADD CONSTRAINT fk_campaigns_created_by_users FOREIGN KEY(created_by) REFERENCES users (id);

ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_pkey;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS ck_notifications_kind;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_division_id_fkey;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_course_id_fkey;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_user_id_fkey;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_campaign_id_fkey;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_campaign_id_key;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_created_by_fkey;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS pk_notifications;
ALTER TABLE notifications ADD CONSTRAINT pk_notifications PRIMARY KEY (id);
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS ck_notifications_notification_kind;
ALTER TABLE notifications ADD CONSTRAINT ck_notifications_notification_kind CHECK (kind IN ('targeted', 'campaign', 'purchase', 'system'));
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS fk_notifications_division_id_divisions;
ALTER TABLE notifications ADD CONSTRAINT fk_notifications_division_id_divisions FOREIGN KEY(division_id) REFERENCES divisions (id);
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS fk_notifications_course_id_courses;
ALTER TABLE notifications ADD CONSTRAINT fk_notifications_course_id_courses FOREIGN KEY(course_id) REFERENCES courses (id);
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS fk_notifications_user_id_users;
ALTER TABLE notifications ADD CONSTRAINT fk_notifications_user_id_users FOREIGN KEY(user_id) REFERENCES users (id);
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS uq_notifications_campaign_id;
ALTER TABLE notifications ADD CONSTRAINT uq_notifications_campaign_id UNIQUE (campaign_id);
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS fk_notifications_campaign_id_campaigns;
ALTER TABLE notifications ADD CONSTRAINT fk_notifications_campaign_id_campaigns FOREIGN KEY(campaign_id) REFERENCES campaigns (id);
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS fk_notifications_created_by_users;
ALTER TABLE notifications ADD CONSTRAINT fk_notifications_created_by_users FOREIGN KEY(created_by) REFERENCES users (id);

ALTER TABLE notification_recipients DROP CONSTRAINT IF EXISTS notification_recipients_pkey;
ALTER TABLE notification_recipients DROP CONSTRAINT IF EXISTS notification_recipients_notification_id_fkey;
ALTER TABLE notification_recipients DROP CONSTRAINT IF EXISTS notification_recipients_user_id_fkey;
ALTER TABLE notification_recipients DROP CONSTRAINT IF EXISTS pk_notification_recipients;
ALTER TABLE notification_recipients ADD CONSTRAINT pk_notification_recipients PRIMARY KEY (id);
ALTER TABLE notification_recipients DROP CONSTRAINT IF EXISTS fk_notification_recipients_notification_id_notifications;
ALTER TABLE notification_recipients ADD CONSTRAINT fk_notification_recipients_notification_id_notifications FOREIGN KEY(notification_id) REFERENCES notifications (id);
ALTER TABLE notification_recipients DROP CONSTRAINT IF EXISTS fk_notification_recipients_user_id_users;
ALTER TABLE notification_recipients ADD CONSTRAINT fk_notification_recipients_user_id_users FOREIGN KEY(user_id) REFERENCES users (id);
ALTER TABLE notification_recipients DROP CONSTRAINT IF EXISTS uq_notification_recipient;
ALTER TABLE notification_recipients ADD CONSTRAINT uq_notification_recipient UNIQUE (notification_id, user_id);
ALTER TABLE notification_recipients DROP CONSTRAINT IF EXISTS ck_notification_recipients_push_status;
ALTER TABLE notification_recipients ADD CONSTRAINT ck_notification_recipients_push_status CHECK (push_status IN ('pending', 'sent', 'failed', 'skipped'));

ALTER TABLE push_subscriptions DROP CONSTRAINT IF EXISTS push_subscriptions_pkey;
ALTER TABLE push_subscriptions DROP CONSTRAINT IF EXISTS push_subscriptions_user_id_fkey;
ALTER TABLE push_subscriptions DROP CONSTRAINT IF EXISTS push_subscriptions_endpoint_key;
ALTER TABLE push_subscriptions DROP CONSTRAINT IF EXISTS ck_push_subscriptions_failure_count;
ALTER TABLE push_subscriptions DROP CONSTRAINT IF EXISTS pk_push_subscriptions;
ALTER TABLE push_subscriptions ADD CONSTRAINT pk_push_subscriptions PRIMARY KEY (id);
ALTER TABLE push_subscriptions DROP CONSTRAINT IF EXISTS fk_push_subscriptions_user_id_users;
ALTER TABLE push_subscriptions ADD CONSTRAINT fk_push_subscriptions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id);
ALTER TABLE push_subscriptions DROP CONSTRAINT IF EXISTS uq_push_subscriptions_endpoint;
ALTER TABLE push_subscriptions ADD CONSTRAINT uq_push_subscriptions_endpoint UNIQUE (endpoint);

ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS live_streams_pkey;
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS ck_live_streams_audience;
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS ck_live_streams_status;
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS live_streams_course_id_fkey;
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS live_streams_division_id_fkey;
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS live_streams_chat_channel_id_fkey;
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS live_streams_chat_channel_id_key;
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS live_streams_created_by_fkey;
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS pk_live_streams;
ALTER TABLE live_streams ADD CONSTRAINT pk_live_streams PRIMARY KEY (id);
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS fk_live_streams_course_id_courses;
ALTER TABLE live_streams ADD CONSTRAINT fk_live_streams_course_id_courses FOREIGN KEY(course_id) REFERENCES courses (id);
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS fk_live_streams_division_id_divisions;
ALTER TABLE live_streams ADD CONSTRAINT fk_live_streams_division_id_divisions FOREIGN KEY(division_id) REFERENCES divisions (id);
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS ck_live_streams_stream_status;
ALTER TABLE live_streams ADD CONSTRAINT ck_live_streams_stream_status CHECK (status IN ('scheduled', 'live', 'ended', 'cancelled'));
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS uq_live_streams_chat_channel_id;
ALTER TABLE live_streams ADD CONSTRAINT uq_live_streams_chat_channel_id UNIQUE (chat_channel_id);
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS fk_live_streams_chat_channel_id_channels;
ALTER TABLE live_streams ADD CONSTRAINT fk_live_streams_chat_channel_id_channels FOREIGN KEY(chat_channel_id) REFERENCES channels (id);
ALTER TABLE live_streams DROP CONSTRAINT IF EXISTS fk_live_streams_created_by_users;
ALTER TABLE live_streams ADD CONSTRAINT fk_live_streams_created_by_users FOREIGN KEY(created_by) REFERENCES users (id);

DROP INDEX IF EXISTS ix_purchases_reviewed_by;
DROP INDEX IF EXISTS ix_campaigns_created_by;
DROP INDEX IF EXISTS ix_notifications_division_id;
DROP INDEX IF EXISTS ix_notifications_course_id;
DROP INDEX IF EXISTS ix_notifications_user_id;
DROP INDEX IF EXISTS ix_notifications_created_by;
DROP INDEX IF EXISTS ix_live_streams_course_id;
DROP INDEX IF EXISTS ix_live_streams_division_id;
DROP INDEX IF EXISTS ix_live_streams_created_by;
DROP INDEX IF EXISTS ix_purchases_pending_course;
DROP INDEX IF EXISTS ix_purchases_pending_lesson;
DROP INDEX IF EXISTS uq_purchase_pending_course;
DROP INDEX IF EXISTS uq_purchase_pending_lesson;
CREATE UNIQUE INDEX uq_purchase_pending_course ON purchases (user_id, course_id) WHERE lesson_id IS NULL AND status = 'pending';
CREATE UNIQUE INDEX uq_purchase_pending_lesson ON purchases (user_id, lesson_id) WHERE lesson_id IS NOT NULL AND status = 'pending';

-- PostgreSQL-side conveniences for manual SQL inserts; the ORM also supplies
-- these defaults in Python. They do not change the reflected column types.
ALTER TABLE purchases ALTER COLUMN currency SET DEFAULT 'EGP';
ALTER TABLE purchases ALTER COLUMN status SET DEFAULT 'pending';
ALTER TABLE purchases ALTER COLUMN note SET DEFAULT '';
ALTER TABLE purchases ALTER COLUMN review_note SET DEFAULT '';
ALTER TABLE purchases ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE purchases ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE campaigns ALTER COLUMN status SET DEFAULT 'scheduled';
ALTER TABLE campaigns ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE notifications ALTER COLUMN kind SET DEFAULT 'targeted';
ALTER TABLE notifications ALTER COLUMN url SET DEFAULT '/notifications';
ALTER TABLE notifications ALTER COLUMN audience_role SET DEFAULT '';
ALTER TABLE notifications ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE notification_recipients ALTER COLUMN push_status SET DEFAULT 'pending';
ALTER TABLE notification_recipients ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE push_subscriptions ALTER COLUMN user_agent SET DEFAULT '';
ALTER TABLE push_subscriptions ALTER COLUMN failure_count SET DEFAULT 0;
ALTER TABLE push_subscriptions ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE live_streams ALTER COLUMN description SET DEFAULT '';
ALTER TABLE live_streams ALTER COLUMN audience SET DEFAULT 'all';
ALTER TABLE live_streams ALTER COLUMN status SET DEFAULT 'scheduled';
ALTER TABLE live_streams ALTER COLUMN playback_url SET DEFAULT '';
ALTER TABLE live_streams ALTER COLUMN ingest_url_encrypted SET DEFAULT '';
ALTER TABLE live_streams ALTER COLUMN publish_key_encrypted SET DEFAULT '';
ALTER TABLE live_streams ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE live_streams ALTER COLUMN updated_at SET DEFAULT now();

-- Wave 5 narrows live management to owner/admin; remove the old placeholder grant.
DELETE FROM role_capabilities WHERE capability = 'stream/manage' AND role = 'teacher';
