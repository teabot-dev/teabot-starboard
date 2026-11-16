"""Boards repost what gets enough of their emoji, keep the count current, and take reposts down again."""

import discord
import pytest
from teabot.sdk import File
from teabot.testing import (
    ActionFailed,
    FakeCategory,
    FakeChannel,
    FakeMember,
    FakeMessage,
    HarnessFactory,
    PluginHarness,
)

from teabot_starboard import ignore, list_, plugin, refresh, remove, set_, top, unignore

SERVER_EMOJI = "<:raids:123456789012345678>"


@pytest.fixture
async def harness(teabot_harness: HarnessFactory) -> PluginHarness:
    return await teabot_harness(plugin)


def members(harness: PluginHarness, count: int) -> list[FakeMember]:
    return [harness.guild.add_member(discord.Permissions.none(), name=f"fan{i}") for i in range(count)]


async def settle(harness: PluginHarness) -> None:
    """Let a burst of reactions settle, and run the refresh it queued."""
    await harness.advance(seconds=3)
    await harness.run_jobs()


async def react(harness: PluginHarness, message: FakeMessage, fans: list[FakeMember], emoji: str = "⭐") -> None:
    for fan in fans:
        await harness.react(message, fan, emoji)
    await settle(harness)


def reposts(board: FakeChannel) -> list[FakeMessage]:
    return [m for m in board.sent if not m.deleted]


async def setup(harness: PluginHarness, threshold: int = 3) -> tuple[FakeChannel, FakeChannel, FakeMember]:
    chat = harness.guild.add_channel(FakeChannel(name="chat"))
    board = harness.guild.add_channel(FakeChannel(name="starboard"))
    await harness.call(set_, emoji="⭐", channel=board, threshold=threshold)
    author = harness.guild.add_member(discord.Permissions.none(), name="author")
    return chat, board, author


async def test_a_message_is_reposted_at_the_threshold_with_its_text_and_picture(harness: PluginHarness) -> None:
    chat, board, author = await setup(harness)
    message = await harness.post(chat, author, "99 agility!", files=[File("cape.png", b"png")])
    await react(harness, message, members(harness, 2))
    assert reposts(board) == []
    await react(harness, message, members(harness, 1))
    (posted,) = reposts(board)
    assert posted.content == f"⭐ **3** · <#{chat.id}>"
    assert posted.embed is not None
    assert posted.embed.description == "99 agility!"
    assert posted.embed.author.name == "author"
    assert posted.embed.image.url == "https://cdn.discordapp.com/attachments/0/0/cape.png"
    assert str(message.id) in str(posted.embed.fields[-1].value)


async def test_the_count_follows_reactions_and_the_repost_goes_below_the_threshold(harness: PluginHarness) -> None:
    chat, board, author = await setup(harness)
    message = await harness.post(chat, author, "gz")
    fans = members(harness, 4)
    await react(harness, message, fans)
    (posted,) = reposts(board)
    assert posted.content is not None and "**4**" in posted.content
    for fan in fans[:2]:
        await harness.react(message, fan, "⭐", remove=True)
    await settle(harness)
    assert reposts(board) == []


async def test_a_burst_of_reactions_costs_one_refresh_and_a_second_run_changes_nothing(
    harness: PluginHarness,
) -> None:
    chat, board, author = await setup(harness)
    message = await harness.post(chat, author, "gz")
    await react(harness, message, members(harness, 5))
    (posted,) = reposts(board)
    assert posted.edits == 0
    (listed,) = await harness.call(list_)
    await harness.run_job(refresh.bind(board=listed.id, channel=chat.id, message=message.id, emoji="⭐"))
    assert reposts(board) == [posted]


async def test_the_authors_own_reaction_counts_only_with_self_stars(harness: PluginHarness) -> None:
    chat, board, author = await setup(harness, threshold=2)
    message = await harness.post(chat, author, "me")
    await react(harness, message, [author, *members(harness, 1)])
    assert reposts(board) == []
    await harness.call(set_, emoji="⭐", channel=board, threshold=2, self_stars=True)
    await harness.react(message, author, "⭐", remove=True)
    await harness.react(message, author, "⭐")
    await settle(harness)
    assert len(reposts(board)) == 1


async def test_bots_do_not_count(harness: PluginHarness) -> None:
    chat, board, author = await setup(harness, threshold=2)
    message = await harness.post(chat, author, "beep")
    robot = harness.guild.add_member(discord.Permissions.none(), name="robot", bot=True)
    message.react(robot, "⭐")
    await react(harness, message, members(harness, 1))
    assert reposts(board) == []


async def test_reactions_in_a_boards_channel_and_ignored_places_do_not_count(harness: PluginHarness) -> None:
    chat, board, author = await setup(harness, threshold=1)
    reposted = await harness.post(board, author, "on the board")
    await react(harness, reposted, members(harness, 2))
    assert reposts(board) == [reposted]
    await harness.call(ignore, channel=chat.id)
    message = await harness.post(chat, author, "hidden")
    await react(harness, message, members(harness, 1))
    assert reposts(board) == [reposted]
    await harness.call(unignore, channel=chat.id)
    raids = harness.guild.add_channel(FakeCategory(name="raids"))
    loot = harness.guild.add_channel(FakeChannel(name="loot", category=raids))
    await harness.call(ignore, channel=raids.id)
    drop = await harness.post(loot, author, "tbow")
    await react(harness, drop, members(harness, 1))
    assert reposts(board) == [reposted]
    await react(harness, message, members(harness, 1))
    assert len(reposts(board)) == 2


async def test_an_age_restricted_message_goes_only_to_an_age_restricted_board(harness: PluginHarness) -> None:
    _, board, author = await setup(harness, threshold=1)
    spicy = harness.guild.add_channel(FakeChannel(name="spicy", nsfw=True))
    message = await harness.post(spicy, author, "nsfw")
    await react(harness, message, members(harness, 1))
    assert reposts(board) == []
    board.nsfw = True
    await react(harness, message, members(harness, 1))
    assert len(reposts(board)) == 1


async def test_a_deleted_message_takes_its_repost_down(harness: PluginHarness) -> None:
    chat, board, author = await setup(harness, threshold=1)
    message = await harness.post(chat, author, "oops")
    fans = members(harness, 2)
    await react(harness, message, fans)
    message.deleted = True
    await harness.react(message, fans[0], "⭐", remove=True)
    await settle(harness)
    assert reposts(board) == []


async def test_a_server_emoji_counts_after_a_rename_and_a_selector_makes_no_difference(
    harness: PluginHarness,
) -> None:
    chat = harness.guild.add_channel(FakeChannel(name="chat"))
    raids = harness.guild.add_channel(FakeChannel(name="raid-board"))
    hearts = harness.guild.add_channel(FakeChannel(name="love"))
    await harness.call(set_, emoji=SERVER_EMOJI, channel=raids, threshold=1)
    await harness.call(set_, emoji="❤️", channel=hearts, threshold=1)
    author = harness.guild.add_member(discord.Permissions.none())
    message = await harness.post(chat, author, "first cox")
    await react(harness, message, members(harness, 1), emoji="<:raids_new:123456789012345678>")
    await react(harness, message, members(harness, 1), emoji="❤")
    assert (len(reposts(raids)), len(reposts(hearts))) == (1, 1)


@pytest.mark.parametrize("typed", [":star:", "star", "⭐ ⭐", ""])
async def test_a_board_needs_one_real_emoji(harness: PluginHarness, typed: str) -> None:
    board = harness.guild.add_channel(FakeChannel(name="starboard"))
    with pytest.raises(ActionFailed):
        await harness.call(set_, emoji=typed, channel=board)


async def test_boards_are_listed_and_a_board_shows_its_top_messages(harness: PluginHarness) -> None:
    chat, board, author = await setup(harness, threshold=1)
    first = await harness.post(chat, author, "one")
    second = await harness.post(chat, author, "two")
    await react(harness, first, members(harness, 1))
    await react(harness, second, members(harness, 2))
    (listed,) = await harness.call(list_)
    assert listed.render() == f"⭐ × 1 → <#{board.id}>"
    best = await harness.call(top, emoji="⭐")
    assert [(t.stars, t.message_id) for t in best] == [(2, second.id), (1, first.id)]
    with pytest.raises(ActionFailed):
        await harness.call(top, emoji="🔥")


async def test_removing_a_board_leaves_its_reposts(harness: PluginHarness) -> None:
    chat, board, author = await setup(harness, threshold=1)
    message = await harness.post(chat, author, "keep me")
    await react(harness, message, members(harness, 1))
    planned = await harness.plan(remove, emoji="⭐")
    assert [e.detail for e in planned.entries] == [f"1 reposts in <#{board.id}> stay there, and stop being updated"]
    await harness.confirm(planned)
    assert await harness.call(list_) == []
    assert len(reposts(board)) == 1
    await react(harness, message, members(harness, 1))
    assert reposts(board)[0].edits == 0
