This is the Werewolf game bot for ##werewolf on freenode. It's a fork of [lycanthrope][1], which was the last bot used in #wolfgame before it died.

We have an active community, and we'd love for you to [join us][2]!

# Running your own copy

You need Python 3.2 or newer to run the bot.

Copy `botconfig.py.example` to `botconfig.py` and modify the settings as needed. You can also copy-paste individual settings from `src/settings.py` into `botconfig.py` if you want to modify them.

To start the bot, run `./wolfbot.py`. You can use `--verbose` to log all raw IRC messages and `--debug` to enable some debugging features. These options should not be used in production.

[1]: https://github.com/LycanthropeTheGreat/lycanthrope
[2]: https://kiwiirc.com/client/chat.freenode.net:+6697/##werewolf
