# Lykos, the Open-Source Werewolf bot

## General information

### What does Open-Source mean?

Open-Source means that the code is available for free for everyone to view, download, use, and modify. We however have a [License][license], which essentially means that you're not allowed to sell the code or gain profit from it in some way. We do not take donations yet.

### What is Werewolf?

Werewolf is a popular party game, similar to and inspired by [mafia][mafia]. In Werewolf, several players take roles as either wolves or their allies, or as villagers - some with special powers - who try to figure out who the wolves are and eliminate them before it is too late. There may also be some other players who play towards their own goals, which may or may not help any side.

### Where can I play this game?

We run an instance of the bot in the [##werewolf channel][game_webchat] on freenode. Off-topic discussion happens in ##werewolf-meta on the same network, and channel operators can be reached in ##werewolf-ops. There are also other networks listed in the [Networks page][wikinet] of our [official wiki][wiki]. Keep in mind that, just because someone appears online, does not mean they are around or available to play.

## For players

### I've never played such a game before. How do I play?

You can join a new game with `!join`. There must be at least 4 players to be able to start a game. When the game is started, the bot will message you privately telling you your role, what command(s) you have access to as that role, and what your goal is. You may then send commands privately to the bot; for example `see person`. Some roles require you to use the command during the day, and sometimes in the channel. Make sure to pay attention to the message!

If you're a wolf or other wolf-aligned role, you probably have access to the wolfchat. To use it, simply message the bot, and your message will be relayed to all other wolfchat players. You will also get their messages.

The bot contains over 50 roles, so it can take a while to get used to all of them. Practice makes perfect!

### As a player, what commands can I use?

Lykos has a host of commands which can be used for various purposes. Here is a non-exhaustive list:

```
!join: Joins a new game. If a game is running, this lets you join the deadchat, where dead players and people who are not playing may interact. The command !j is an alias for this.
!quit: Quits the game you're currently in. The command !leave is an alias for this.
!start: Starts a new game of Werewolf. At least 4 players are required for most gamemodes, and sometimes more.
!wait: Increases the wait time before a game can be started. If a game is not started 60 minutes after the first join (configurable by the bot owner), the game will be cancelled. The command !w is an alias for this.
!game: If in the process of joining the game, this allows players to vote for a game mode of their choice. The commands !vote and !v are aliases for this.
!pingif: Set a threshold of players. When there is at least as many players as your preference, you will be pinged by the bot. The commands !pingme and !pingat are aliases for this.

!lynch: During a game and during the day, this allows you to vote for a player to be lynched. Lynching wolves is how the village wins! There needs to be a majority of votes on one person to induce a lynch. The commands !vote and !v are aliases for this.
!abstain: During a game and during the day, this allows you to not vote for this day. This will be calculated along with the votes to determine whether or not a lynch happens. If a majority of players abstain, no lynch will happen for the day. The commands !abs and !nolynch are aliases for this.
!stats: This shows you the current alive players as well as the roles currently alive. The role information is displayed as if a person who isn't playing was keeping track of deaths and showing the current roles to people. As such, it is guaranteed to always be accurate, even if sometimes confusing. The commands !s and !players are aliases for this.
!roles: This shows you all of the roles that can be present in a given gamemode. If a game is running, this outputs what roles the game started with.
!votes: Show how many votes there are for a specific gamemode (while joining the game) or a specific player (when a game is running). The commands !vote and !v are aliases for this.
!time: Shows how much time is left before the game is cancelled (while joining the game), or before day or ngiht is over (when a game is running).

!gamestats: Outputs game statistics for specific gamemodes. The command !gstats is an alias for this.
!playerstats: Outputs player statistics for specific roles. The commands !pstats and !p are aliases for this.
!mystats: Shows you your own player statistics. Same as doing !playerstats <myname>. The command !m is an alias for this.
!rolestats: Outputs global role statistics. The command !rstats is an alias for this.

!help: Get a list of commands, and can also be used to get more detailed information on specific commands.
!wiki: Give a link to the wiki. If an argument is given, such as !wiki seer, the link to the particular article will be retrieved, and the summary from the page will be sent in a private notice to the player.
```

## For bot operators

### I want to play this bot on my own network, how can I do that?

The bot requires some setup before it can be up and running. Here are the required steps:

- You need to have Python 3.5 or above installed on your machine or the server on which the bot will be running. Steps on how to install Python on your machine will not be covered here, although if you are using Windows, then you can simply download and install the [official Python binaries][pydownload].
- If building Python from source, you will need to include SQLite3 as part of the building process, as the bot uses it.
- To enable the ability to update the bot with the changes that we bring to it, you will need to [download and install Git][git].
- If your network supports it, create an account for your bot and give it automatic op upon joining your channel via your channel management service (typically the `+O` flag if using `ChanServ`).
- Copy the file `botconfig.py.example` to `botconfig.py` (make sure to make a copy and not simply rename), and open it with your favourite text editor. Modify the settings as seen below. If a setting is not present here, it means the default is fine for most cases.
```
HOST: Where the bot will connect to. Make sure to surround the name in "quotes".
PORT: The port that the bot will use to connect to the above. Traditionally 6667 or 5555, but 6697 is used for SSL.
NICK: Which nick the bot should connect as. This should be the same as the account you registered above.
PASS: This is the password for your bot, which will be sent upon connection. Make sure it is surrounded by "quotes".
SASL_AUTHENTICATION: We highly recommend leaving this setting as-is, as it is the most secure way to identify.

USE_SSL: We recommend leaving this settings as-is. In that case, PORT needs to be adjusted, typically to 6697.
CHANNEL: This is the channel the game will be played it. Make sure it has the leading # and is surrounded in "quotes".
CMD_CHAR: The command prefix for every command. It is ! by default, but can be anything and of any length. Make sure it is surrounded in "quotes".

OWNERS: This is the hostname of the bot owner. This supports wildcards, but please be careful, as this grants total access over the bot. If the host changes too much or too often, we recommend setting this to ()
OWNERS_ACCOUNTS: This is the account of the owner of the bot. This also supports wildcards. If your network does not support accounts, set this to ()
```

### I entered everything correctly, but the bot doesn't work in some way. What can I do?

We can help you with these kinds of issues in our [development channel, #lykos][dev_webchat] on freenode. Ask directly in the channel, and wait for someone to answer. Please do not message people directly, as that prevents other people from helping as well. People who are voiced (typically a '+' before their name in the user list, or a blue circle for Hexchat) are developers and are more likely to be able to help.

### The bot works fine, but there's just something I'd like to tweak. Is that possible?

It absolutely is! If you open the file `settings.py` under the `src` folder, you will see a lot of different settings, usually accompagnied by a comment briefly explaining what the setting is for. You can copy and paste these settings into your `botconfig.py` file, and change them as you wish. Time-related settings are in seconds. You will need to restart the bot for the changes to take effect.

*Careful: Do __not__ modify the `settings.py` file directly, as that will prevent you from getting any future update.*

If there is something that you would like to tweak but can't find the setting for it, you may ask in [#lykos][dev_webchat]. It may be hidden somewhere, or may not exist. We are usually willing to add new settings to allow other bot owners to customize their bot to the fullest. You may also [open an issue][new_issue] on our bug tracker.

### The roles are nice, but I'd like to add my own. Can I do that?

Yes! You can create your own roles by putting them inside the `roles` folder. There is a base "skeleton" file `src/roles/_skel.py` that you can copy and paste to get some basic stuff in. You will need to define your own commands (if applicable) and [register events][events]. If you need assistance with this, we'll be happy to help you.

### Can I also add a new game mode to go with my new role(s) or just to change things up?

That's also possible! You can copy the `gamemodes.py.example` file into `gamemodes.py` and modify it following the layout inside the `src/gamemodes.py` file. Creating a simple gamemode is a fairly straightforward task compared to creating a new role.

### What admin commands can I use?

```
!fjoin: Forcibly join a player to the game. Bypasses stasis.
!fleave: Forcibly removes a player from the game. Instantly kills them if a game is running.
!fstart: Forcibly start the game without waiting for the start timer
!fstop: Force-stop the game. This is useful if there was an error and the game can't continue.
!flastgame: Prevent players from joining in to a new game until the bot is restarted.

!frestart: Forces the bot to restart. We recommend using '!aftergame frestart', which will queue the command for right after the game is over.
!fdie: Kills the bot. You shouldn't usually need to do this. It will not kill the bot if a game is running. '!fdie -force' will kill the bot even if it's in a game. If there is an error and even that doesn't work, '!fdie -dirty' crashes the bot (all information is lost). Do not use the latter lightly.

!update: Updates the bot with the latest code from the repository. We recommend using '!aftergame update' so that the bot is updated once the game is over.

!fflags: This is the command to add new admins or moderators into your bot. Only a full admin may use it (owners are full admins). The valid flags are:

+A: Grants !fjoin, !fleave, and !fstasis.
+D: Grants !frestart, !aftergame, !flastgame, and !update.
+F: Grants (almost) full control over the bot, including !fdie and !fwarn. User will show up in !admins.
+N: Grants !fday and !fnight, forcing day or night, respectively.
+S: Grants !fstart and !fstop.

+a: Grants !revealroles, which lets player see who is what role at any given time. This command is disabled for anyone currently playing.
+d: Grants !frole, !force and !rforce, which are all debug-mode commands.
+g: Grants !fgame, allowing to force a certain gamemode to be picked.
+j: Grants !fgoat, a silly harmless command.
+m: Grants !fsync and !refreshdb, both useful when the bot is desynced from the IRC server, or if some data isn't accurate. This is usually helpful after recovering from netsplits, but otherwise not so much.
+p: Grants !spectate, letting someone spectate the wolfchat during a game.
+s: Grants !fsay and !fdo, allowing to send messages via the bot to the game channel. Only full admins can send messages anywhere.
+w: Grants !fwait, forcibly increasing the wait time before the game can be started.
```

### Our player base is mostly non-English speakers. Is there support for our language?

Not right now. However, Lykos is a community effort, and so we encourage you to submit your own translation! We invite you to [communicate with us][dev_webchat] for questions on how to proceed.

### We would like to do X with a role/gamemode, but the bot doesn't seem to support it. What can I do?

Let us know! We will do the best we can to accomodate third-party roles and modes, and make sure they work fine!

### Additional information for bot operators

You can run the bot by doing `./wolfbot.py` on Linux, or simply double-clicking the `wolfbot.py` file on Windows.

The bot has a built-in throttling mechanism, preventing the bot from flooding out if too many messages are sent at once. However, depending on the network, these settings may be too strict or too lax. Before running the bot initially, we recommend running `./wolfbot.py --lagcheck`. Wait for it to finish, and it will tell you which settings you should put into your `botconfig.py` file.

## Credits

This bot wouldn't be what it is today without the contribution of many people. Here are some of those people:

jcao219: Original programmer

woffle / Skizzerz: Main developer  
Vgr: Main developer

jacob1: Developer  
nyuszika7h: Developer

Iciloo: Testing

Everyone who contributed to the code, no matter how small.  
Everyone who opened issues in our bug tracker.  
And, of course, to all the bot owners and players who kept this project alive all this time!

Special thanks to LaneAtomic for their work on the messages system, which made coding future features a lot easier.

[mafia]: https://en.wikipedia.org/wiki/Mafia_(party_game)
[license]: https://github.com/lykoss/lykos/blob/master/LICENSE
[game_webchat]: http://webchat.freenode.net/?channels=##werewolf
[wikinet]: https://werewolf.chat/Networks
[wiki]: https://werewolf.chat/Main_Page
[pydownload]: https://www.python.org/downloads/
[git]: https://git-scm.com/downloads
[dev_webchat]: http://webchat.freenode.net/?channels=#lykos
[new_issue]: https://github.com/lykoss/lykos/issues/new
[events]: https://werewolf.chat/Events
