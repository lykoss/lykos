This is the Werewolf game bot for ##werewolf on freenode. It's a fork of [lycanthrope][1], which was the last bot used in #wolfgame before it died.

We have an active community, and we'd love for you to [join us][2]!

# Running your own copy

You need Python 3.3 or newer to run the bot. Python 3.4 and higher is recommended.

SQLite3 is required for the bot's database. If compiling Python from source, you may need to install the appropriate SQLite3 development libraries for your distribution first.

Copy `botconfig.py.example` to `botconfig.py` and modify the settings as needed. You can also copy-paste individual settings from `src/settings.py` into `botconfig.py` if you want to modify them. You may also add or customize your own game modes by renaming `gamemodes.py.example` to `gamemodes.py` and using the same layout used in `src/gamemodes.py`.

Note: you should never alter files under the `src` folder directly (unless you are submitting a change to the code), use `botconfig.py` and `gamemodes.py` for related changes.

To start the bot, run `./wolfbot.py`. You can use `--verbose` to log all raw IRC messages and `--debug` to enable some debugging features. These options should not be used in production.

[1]: https://github.com/LycanthropeTheGreat/lycanthrope
[2]: https://kiwiirc.com/client/chat.freenode.net:+6697/##werewolf
