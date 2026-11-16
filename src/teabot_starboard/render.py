"""What a repost shows, and how a board's emoji is written and matched."""

import re

import discord
from teabot.sdk import ActionError, Member, ReceivedMessage

GOLD = 0xE3A008
TEXT_MAX = 4000  # an embed's description holds 4096 characters
FILES_SHOWN = 5
SERVER_EMOJI = re.compile(r"<a?:\w{2,32}:(\d{15,25})>")
VARIATION_SELECTOR = chr(0xFE0F)  # invisible, so spelled out


def emoji_key(emoji: str) -> str:
    """How a board matches a reaction: a server emoji by its ID, which outlives a rename, and any other by its
    character, without the variation selector Discord writes with some emoji and not others."""
    found = SERVER_EMOJI.fullmatch(emoji)
    return found.group(1) if found else emoji.replace(VARIATION_SELECTOR, "")


def board_emoji(typed: str) -> str:
    """The emoji an admin typed for a board, or an `ActionError` saying what to type instead."""
    emoji = typed.strip()
    if SERVER_EMOJI.fullmatch(emoji):
        return emoji
    if emoji.startswith(":") and emoji.endswith(":"):
        raise ActionError(f"Pick {emoji} from Discord's emoji picker, so it is sent as the emoji itself.")
    if not emoji or len(emoji) > 16 or any(c.isalnum() or c.isspace() for c in emoji):
        raise ActionError("Give one emoji, such as ⭐, or one of this server's own.")
    return emoji


def header(emoji: str, stars: int, channel_id: int) -> str:
    """The line above a repost: the board's emoji, the count, and where the message is."""
    return f"{emoji} **{stars}** · <#{channel_id}>"


def repost(message: ReceivedMessage, author: Member | None, link: str) -> discord.Embed:
    """The repost: who wrote the message, its text, its first picture, its other files, and a link back."""
    embed = discord.Embed(description=message.content[:TEXT_MAX] or None, colour=GOLD, timestamp=message.created_at)
    if author is not None:
        embed.set_author(name=author.display_name, icon_url=author.avatar_url or None)
    else:
        embed.set_author(name="Someone no longer in the server")
    pictures = [a for a in message.attachments if a.image]
    if pictures:
        embed.set_image(url=pictures[0].url)
    others = [a for a in message.attachments if a not in pictures[:1]]
    if others:
        shown = "\n".join(f"[{a.filename}]({a.url})" for a in others[:FILES_SHOWN])
        more = len(others) - FILES_SHOWN
        embed.add_field(name="Files", value=shown + (f"\nand {more} more" if more > 0 else ""), inline=False)
    embed.add_field(name="Original", value=f"[Jump to the message]({link})", inline=False)
    return embed
