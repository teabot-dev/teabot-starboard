"""teabot-starboard: a message that gets enough of a board's emoji is reposted to the board's channel. Imports only
`teabot.sdk`.

- `starboard.set` makes a board, an emoji, a channel and how many reactions it takes, or changes one.
- `starboard.remove` removes a board, after a plan. Its reposts stay in its channel.
- `starboard.list` shows the boards, and `starboard.top` a board's most reacted messages.
- `starboard.ignore` and `starboard.unignore` keep a channel's messages, or a category's, off every board.
- A reaction with a board's emoji queues `refresh` for its message. Reactions often come in bursts, so it waits a
  moment, and the burst's reactions share one run. It counts the reactions from Discord, then posts the repost,
  updates its count, or takes it down when the count falls below the board's.
"""

from datetime import datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, Field
from teabot.sdk import (
    DESTRUCTIVE,
    READ,
    ActionError,
    ChannelRef,
    Context,
    Diff,
    DiffEntry,
    EmptyConfig,
    Guild,
    Plugin,
    Reaction,
    TextChannel,
)

from teabot_starboard.render import board_emoji, emoji_key, header, repost

plugin = Plugin("starboard")
type Ctx = Context[EmptyConfig]

# How long a refresh waits for a burst of reactions to settle, so the burst costs Discord one count.
SETTLE = timedelta(seconds=2)
TOP_MAX = 10


class Board(BaseModel):
    id: int
    emoji: str
    channel_id: int
    threshold: int
    self_stars: bool

    def render(self) -> str:
        own = ", own reactions count" if self.self_stars else ""
        return f"{self.emoji} × {self.threshold} → <#{self.channel_id}>{own}"


class Counted(BaseModel):
    """The board a reaction counts for."""

    id: int


class Reposted(BaseModel):
    post_id: int
    read_at: datetime


class Top(BaseModel):
    stars: int
    channel_id: int
    message_id: int
    author_id: int
    guild_id: int

    def render(self) -> str:
        link = f"https://discord.com/channels/{self.guild_id}/{self.channel_id}/{self.message_id}"
        return f"**{self.stars}** · <@{self.author_id}> · [jump]({link})"


SET_BOARD = """
INSERT INTO boards (guild_id, emoji, emoji_key, channel_id, threshold, self_stars) VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (guild_id, emoji_key) DO UPDATE
SET emoji = EXCLUDED.emoji, channel_id = EXCLUDED.channel_id, threshold = EXCLUDED.threshold,
    self_stars = EXCLUDED.self_stars
"""
BOARDS = "SELECT id, emoji, channel_id, threshold, self_stars FROM boards WHERE guild_id = $1 ORDER BY id"
BOARD = "SELECT id, emoji, channel_id, threshold, self_stars FROM boards WHERE guild_id = $1 AND emoji_key = $2"
BOARD_BY_ID = "SELECT id, emoji, channel_id, threshold, self_stars FROM boards WHERE guild_id = $1 AND id = $2"
# The board a reaction counts for: none when it is in a board's own channel, or in an ignored channel, thread's
# channel or category. `$3` is where the message is, from the channel up.
BOARD_FOR = """
SELECT id FROM boards
WHERE guild_id = $1 AND emoji_key = $2
  AND NOT EXISTS (SELECT 1 FROM boards b WHERE b.guild_id = $1 AND b.channel_id = ANY($3))
  AND NOT EXISTS (SELECT 1 FROM ignored_channels i WHERE i.guild_id = $1 AND i.channel_id = ANY($3))
"""
REMOVE_BOARD = "DELETE FROM boards WHERE guild_id = $1 AND id = $2"
COUNT_POSTS = "SELECT count(*) FROM posts WHERE guild_id = $1 AND board_id = $2"
LOCK_POST = """
SELECT post_id, read_at FROM posts WHERE guild_id = $1 AND board_id = $2 AND message_id = $3 FOR UPDATE
"""
ADD_POST = """
INSERT INTO posts (guild_id, board_id, message_id, channel_id, author_id, post_id, stars, read_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
"""
UPDATE_POST = """
UPDATE posts SET stars = $4, read_at = $5 WHERE guild_id = $1 AND board_id = $2 AND message_id = $3
"""
DROP_POST = "DELETE FROM posts WHERE guild_id = $1 AND board_id = $2 AND message_id = $3"
TOP = """
SELECT stars, channel_id, message_id, author_id, guild_id FROM posts
WHERE guild_id = $1 AND board_id = $2 ORDER BY stars DESC, message_id LIMIT $3
"""
IGNORE = "INSERT INTO ignored_channels (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT DO NOTHING"
UNIGNORE = "DELETE FROM ignored_channels WHERE guild_id = $1 AND channel_id = $2"


async def find_board(ctx: Ctx, emoji: str) -> Board:
    found = await ctx.db.fetchrow(Board, BOARD, ctx.guild.id, emoji_key(emoji.strip()))
    if found is None:
        raise ActionError(f"No board uses {emoji.strip()}. /starboard list shows the boards.")
    return found


@plugin.action(needs="manage_guild")
async def set_(
    ctx: Ctx,
    emoji: Annotated[str, Field(max_length=64)],
    channel: TextChannel,
    threshold: Annotated[int, Field(ge=1, le=1000)] = 3,
    self_stars: bool = False,
) -> str:
    """Make a board, or change the one for this emoji.

    Args:
        emoji: The reaction it counts, such as ⭐ or one of this server's emoji.
        channel: Where messages are reposted.
        threshold: How many reactions a message needs.
        self_stars: Whether the author's own reaction counts.
    """
    shown = board_emoji(emoji)
    await ctx.db.execute(SET_BOARD, ctx.guild.id, shown, emoji_key(shown), channel.id, threshold, self_stars)
    return f"Messages with {threshold} × {shown} are reposted to {channel.mention}."


@plugin.action(risk=READ, reply="public")
async def list_(ctx: Ctx) -> list[Board]:
    """The server's boards."""
    return await ctx.db.fetch(Board, BOARDS, ctx.guild.id)


@plugin.action(risk=READ, reply="public")
async def top(ctx: Ctx, emoji: Annotated[str, Field(max_length=64)]) -> list[Top]:
    """A board's most reacted messages.

    Args:
        emoji: The board's emoji.
    """
    board = await find_board(ctx, emoji)
    return await ctx.db.fetch(Top, TOP, ctx.guild.id, board.id, TOP_MAX)


@plugin.action(risk=DESTRUCTIVE, needs="manage_guild")
async def remove(ctx: Ctx, emoji: Annotated[str, Field(max_length=64)]) -> str:
    """Remove a board. Its reposts stay in its channel.

    Args:
        emoji: The board's emoji.
    """
    board = await find_board(ctx, emoji)
    await ctx.db.execute(REMOVE_BOARD, ctx.guild.id, board.id)
    return f"Removed the {board.emoji} board."


@remove.plan
async def plan_remove(ctx: Ctx, emoji: Annotated[str, Field(max_length=64)]) -> Diff:
    board = await find_board(ctx, emoji)
    reposts = await ctx.db.fetchval(int, COUNT_POSTS, ctx.guild.id, board.id)
    detail = f"{reposts} reposts in <#{board.channel_id}> stay there, and stop being updated"
    return Diff(entries=[DiffEntry(change="remove", target=board.emoji, detail=detail, key=board.id)])


@plugin.action(needs="manage_guild")
async def ignore(ctx: Ctx, channel: ChannelRef) -> str:
    """Keep a channel's messages off every board. A category keeps every channel in it off.

    Args:
        channel: The channel or category.
    """
    await ctx.db.execute(IGNORE, ctx.guild.id, channel)
    return f"No board takes messages from <#{channel}> now."


@plugin.action(needs="manage_guild")
async def unignore(ctx: Ctx, channel: ChannelRef) -> str:
    """Let boards take a channel's messages again.

    Args:
        channel: The channel or category.
    """
    await ctx.db.execute(UNIGNORE, ctx.guild.id, channel)
    return f"Boards take messages from <#{channel}> again."


def places(guild: Guild, channel_id: int) -> list[int]:
    """Where a message is, from its channel up: a thread's channel, then the category."""
    found = [channel_id]
    channel = guild.get_channel(channel_id)
    while channel is not None and channel.parent_id is not None and len(found) < 3:
        found.append(channel.parent_id)
        channel = guild.get_channel(channel.parent_id)
    return found


@plugin.on_reaction_add
async def reacted(ctx: Ctx, reaction: Reaction) -> None:
    await queue_refresh(ctx, reaction)


@plugin.on_reaction_remove
async def unreacted(ctx: Ctx, reaction: Reaction) -> None:
    await queue_refresh(ctx, reaction)


async def queue_refresh(ctx: Ctx, reaction: Reaction) -> None:
    where = places(ctx.guild, reaction.channel_id)
    board = await ctx.db.fetchrow(Counted, BOARD_FOR, ctx.guild.id, emoji_key(reaction.emoji), where)
    if board is None:
        return
    bound = refresh.bind(board=board.id, channel=reaction.channel_id, message=reaction.message_id, emoji=reaction.emoji)
    async with ctx.db.transaction() as tx:
        await tx.schedule(bound, at=ctx.now + SETTLE)


@plugin.job
async def refresh(ctx: Ctx, board: int, channel: int, message: int, emoji: str) -> None:
    """Count a message's reactions for a board, and post, update or take down its repost to match."""
    found = await ctx.db.fetchrow(Board, BOARD_BY_ID, ctx.guild.id, board)
    source = ctx.guild.get_text_channel(channel)
    if found is None or source is None:
        return
    read_at = ctx.now
    original = await source.read_message(message)
    givers = await source.reactors(message, emoji) if original is not None else ()
    stars = len([g for g in givers if found.self_stars or original is None or g != original.author_id])
    shown = original is not None and stars >= found.threshold and not hidden(ctx.guild, channel, found.channel_id)
    embed = None
    if original is not None and shown:
        author = await ctx.guild.get_member(original.author_id)
        link = f"https://discord.com/channels/{ctx.guild.id}/{channel}/{message}"
        embed = repost(original, author, link)
    async with ctx.db.transaction() as tx:
        existing = await tx.fetchrow(Reposted, LOCK_POST, ctx.guild.id, board, message)
        if existing is not None and existing.read_at > read_at:
            return  # a later refresh has counted already
        if original is None or embed is None:
            if existing is not None:
                await tx.delete(existing.post_id)
                await tx.execute(DROP_POST, ctx.guild.id, board, message)
            return
        line = header(found.emoji, stars, channel)
        if existing is not None:
            await tx.edit(existing.post_id, line, embed=embed)
            await tx.execute(UPDATE_POST, ctx.guild.id, board, message, stars, read_at)
            return
        post = await tx.send(found.channel_id, line, embed=embed)
        values = (message, channel, original.author_id, post.id, stars, read_at)
        await tx.execute(ADD_POST, ctx.guild.id, board, *values)


def hidden(guild: Guild, source: int, board_channel: int) -> bool:
    """Whether a message stays off a board: one from an age-restricted channel goes only to an age-restricted
    board."""
    found, board = guild.get_channel(source), guild.get_channel(board_channel)
    return found is not None and found.nsfw and not (board is not None and board.nsfw)
