# Lykos, the Open-Source Werewolf bot

## General information

### What does Open-Source mean?

Open-Source means that the code is available for free for everyone to view, download, use, and modify. We however have a [License][license], which requires that you include it in all derivative works and other works which include lykos code.

### What is Werewolf?

Werewolf is a popular party game, similar to and inspired by [mafia][mafia]. In Werewolf, several players take roles as either wolves or their allies, or as villagers - some with special powers - who try to figure out who the wolves are and eliminate them before it is too late. There may also be some other players who play towards their own goals, which may or may not help any side.

### Where can I play this game?

We run an instance of the bot in the [#werewolf channel][game_webchat] on Libera. Off-topic discussion happens in #werewolf-meta on the same network, and channel operators can be reached in #werewolf-ops. There are also other networks listed in the [Networks page][wikinet] of our [official wiki][wiki]. Keep in mind that, just because someone appears online, does not mean they are around or available to play.

## For players

### I've never played such a game before. How do I play?

You can join a new game with `!join`. There must be at least 6 players to be able to start a game. When the game is started, the bot will message you privately telling you your role, what command(s) you have access to as that role, and what your goal is. You may then send commands privately to the bot; for example `see person`. Some roles require you to use the command during the day, and sometimes in the channel. Make sure to pay attention to the message!

If you're a wolf or other wolf-aligned role, you probably have access to the wolfchat. To use it, simply message the bot, and your message will be relayed to all other wolfchat players. You will also get their messages.

The bot contains over 50 roles, so it can take a while to get used to all of them. Practice makes perfect!

### As a player, what commands can I use?

Lykos has a host of commands which can be used for various purposes. [You can view them on our wiki.](https://werewolf.chat/Commands)

## For bot operators

### I want to play this bot on my own network, how can I do that?

The bot requires some setup before it can be up and running. Here are the required steps:

- You need to have Python 3.11 or above installed on your machine or the server on which the bot will be running. Steps on how to install Python on your machine will not be covered here, although if you are using Windows, then you can simply download and install the [official Python binaries][pydownload].
- If building Python from source, you will need to include SQLite3 as part of the building process, as the bot uses it.
- To enable the ability to update the bot with the changes that we bring to it, you will need to [download and install Git][git].
- If your network supports it, create an account for your bot and give it automatic op upon joining your channel via your channel management service (typically the `+O` flag if using `ChanServ`).
- Copy the file `botconfig.example.yml` to `botconfig.yml` (make sure to make a copy and not simply rename), and open it with your favourite text editor. The file is extensively commented with examples and additional info. Modify the sections below. If a setting is not present here, it means the default is fine for most cases.
  * transports: update to point to your IRC network
  * access: point this to your account so you can control the bot over IRC
  * logging: see the comments and update accordingly. For a test bot, you could log everything to stdout (as shown in the first group). If you choose to use transport, make sure you pick a channel and check the comments for more info

### I entered everything correctly, but the bot doesn't work in some way. What can I do?

We can help you with these kinds of issues in our [development channel, #lykos][dev_webchat] on Libera. Ask directly in the channel, and wait for someone to answer. Please do not message people directly, as that prevents other people from helping as well. People who are voiced (typically a '+' before their name in the user list, or a blue circle for Hexchat) are developers and are more likely to be able to help.

### The bot works fine, but there's just something I'd like to tweak. Is that possible?

It absolutely is! For additional gameplay settings, see [the wiki's Configuration page](https://werewolf.chat/Configuration#gameplay). You can copy and paste these settings into your `botconfig.yml` file, and change them as you wish. Time-related settings are in seconds. You will need to restart the bot for the changes to take effect.

If there is something that you would like to tweak but can't find the setting for it, you may ask in [#lykos][dev_webchat]. It may be hidden somewhere, or may not exist. We are usually willing to add new settings to allow other bot owners to customize their bot to the fullest. You may also [open an issue][new_issue] on our bug tracker.

### The roles are nice, but I'd like to add my own. Can I do that?

Yes! You can create your own roles by putting them inside the `roles` folder. There is a base "skeleton" file `src/roles/_skel.py` that you can copy and paste to get some basic stuff in. You will need to define your own commands (if applicable) and [register events][events]. If you need assistance with this, we'll be happy to help you.

### Can I also add a new game mode to go with my new role(s) or just to change things up?

That's also possible! See the existing gamemodes in `src/gamemodes/` and the community modes in [our community-modes repository](https://github.com/lykoss/community-modes) for examples. Put custom modes into the `gamemodes/` directory (*not* `src/gamemodes/`). Then, copy `gamemodes/__init__.py.example` to `gamemodes/__init__.py` so your bot loads them.

### What admin commands can I use?

A [list of admin commands](https://werewolf.chat/Admin_commands) is available on our wiki.

### Our player base is mostly non-English speakers. Is there support for our language?

Not right now. However, Lykos is a community effort, and so we encourage you to submit your own translation! We invite you to [communicate with us][dev_webchat] for questions on how to proceed.

### We would like to do X with a role/gamemode, but the bot doesn't seem to support it. What can I do?

Let us know! We will do the best we can to accomodate third-party roles and modes, and make sure they work fine!

### Additional information for bot operators

You can run the bot by doing `./wolfbot.py` on Linux, or simply double-clicking the `wolfbot.py` file on Windows.

## Credits

This bot wouldn't be what it is today without the contribution of many people. Here are some of those people:

jcao219: Original programmer

moonmoon: Main developer  
Faely: Main developer

jacob1: Developer  
alexia: Developer

Iciloo: Testing

Everyone who contributed to the code, no matter how small.  
Everyone who opened issues in our bug tracker.  
And, of course, to all the bot owners and players who kept this project alive all this time!

Special thanks to LaneAtomic for their work on the messages system, which made coding future features a lot easier.

[mafia]: https://en.wikipedia.org/wiki/Mafia_(party_game)
[license]: https://github.com/lykoss/lykos/blob/master/LICENSE
[game_webchat]: https://web.libera.chat/?channels=#werewolf
[wikinet]: https://werewolf.chat/Networks
[wiki]: https://werewolf.chat/Main_Page
[pydownload]: https://www.python.org/downloads/
[git]: https://git-scm.com/downloads
[dev_webchat]: https://web.libera.chat/?channels=#lykos
[new_issue]: https://github.com/lykoss/lykos/issues/new
[events]: https://werewolf.chat/Events
