# Starboard

Repost the messages your server likes best. A board pairs an emoji with a channel: when a message gets enough reactions of that emoji, teabot reposts it there, and keeps the count up to date. Have as many boards as you like, such as ⭐ for #starboard and 🔥 for #hall-of-fame. Install it from the [plugin hub](https://teabot-dev.github.io/teabot/hub/), then turn it on in a server with `/plugins enable plugin:starboard`.

It needs the Message Content intent, so that teabot can read the message it reposts. The operator turns it on in Discord's developer portal and sets `TEABOT_MESSAGE_CONTENT=true` (see [Settings](https://teabot-dev.github.io/teabot/host/settings/)). Without it, reposts show the author and a link, but no text or pictures.

## Make a board

```text
/starboard set emoji:⭐ channel:#starboard threshold:3
```

From then on, a message with three ⭐ reactions is reposted to #starboard. Running it again for the same emoji changes that board.

| Option | What it is |
|---|---|
| `emoji` | The reaction the board counts. Pick it from Discord's emoji picker: ⭐, or one of the server's own emoji. |
| `channel` | Where messages are reposted. |
| `threshold` | How many reactions a message needs, from 1 to 1000. `3` if left out. |
| `self_stars` | Whether the author's own reaction counts. `false` if left out. |

## The repost

The repost shows the board's emoji, the count and the message's channel, then the author, the text, the first picture, links to any other files, and a link back to the message. As reactions come and go, teabot updates the count. When it falls below the threshold, or the message is deleted, teabot takes the repost down.

- Bots' reactions never count, and the author's own counts only with `self_stars`.
- Reactions to a board's reposts, in its own channel, do not count.
- A message from an age-restricted channel goes only to an age-restricted board.
- teabot counts the reactions Discord has, so reactions given while teabot was offline count at the next reaction.

## See the boards

```text
/starboard list
```

```text
- ⭐ × 3 → #starboard
- 🔥 × 5 → #hall-of-fame, own reactions count
```

```text
/starboard top emoji:⭐
```

The ten messages with the most reactions on that board, with their authors and links.

## Keep channels off the boards

```text
/starboard ignore channel:#staff
/starboard unignore channel:#staff
```

An ignored channel's messages go to no board. Ignore a category to keep every channel in it off, threads included.

## Remove a board

```text
/starboard remove emoji:⭐
```

teabot shows a plan of what it will remove. Confirm it within 15 minutes. See [Confirming changes](https://teabot-dev.github.io/teabot/use/confirming/). The board's reposts stay in its channel, and stop being updated.

## Who can use it

| Command | Needs |
|---|---|
| `/starboard set` | Manage Server |
| `/starboard remove` | Manage Server |
| `/starboard ignore`, `/starboard unignore` | Manage Server |
| `/starboard list`, `/starboard top` | nothing |

teabot needs to see the channels it counts in, with Read Message History, and to post with Embed Links in the boards' channels.

## External connections

None. It talks only to Discord, through teabot.
