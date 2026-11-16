-- A board: messages that get `threshold` reactions of `emoji` are reposted to `channel_id`. One board an emoji,
-- matched by `emoji_key`: a server emoji's ID, which outlives a rename, or the character without its variation
-- selector, which Discord writes with some emoji and not others.
CREATE TABLE boards (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guild_id bigint NOT NULL,
    emoji text NOT NULL,
    emoji_key text NOT NULL,
    channel_id bigint NOT NULL,
    threshold int NOT NULL CHECK (threshold BETWEEN 1 AND 1000),
    self_stars boolean NOT NULL DEFAULT false,
    UNIQUE (guild_id, id),
    UNIQUE (guild_id, emoji_key)
);

-- A message reposted on a board: its repost, the outbox's `post_id`, and its count as of `read_at`, so a refresh
-- that read Discord earlier never overwrites one that read it later.
CREATE TABLE posts (
    guild_id bigint NOT NULL,
    board_id bigint NOT NULL,
    message_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    author_id teabot.member_id NOT NULL,
    post_id bigint NOT NULL,
    stars int NOT NULL,
    read_at timestamptz NOT NULL,
    PRIMARY KEY (guild_id, board_id, message_id),
    FOREIGN KEY (guild_id, board_id) REFERENCES boards (guild_id, id) ON DELETE CASCADE
);

-- Channels, threads' channels or categories whose messages no board takes.
CREATE TABLE ignored_channels (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
);
