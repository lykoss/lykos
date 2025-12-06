# Copyright (c) 2011 Duncan Fordyce, Jimmy Cao
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from oyoyo.ircevents import numeric_events


# avoiding regex
def parse_raw_irc_command(element):
    """
    This function parses a raw irc command and returns a tuple
    of (prefix, command, args).
    The following is a psuedo BNF of the input text:

    <message>  ::= [ '@' <tags> <SPACE> ] [ ':' <prefix> <SPACE> ] <command> <params> <crlf>
    <tags>     ::= <tag> { ';' <tag> }
    <tag>      ::= <key> [ '=' <value> ]
    <prefix>   ::= <servername> | <nick> [ '!' <user> ] [ '@' <host> ]
    <command>  ::= <letter> { <letter> } | <number> <number> <number>
    <SPACE>    ::= ' ' { ' ' }
    <params>   ::= <SPACE> [ ':' <trailing> | <middle> <params> ]
    <key>      ::= [ '+' ] [ <vendor> '/' ] <key_name>

    <middle>   ::= <Any *non-empty* sequence of octets not including SPACE
                   or NUL or CR or LF, the first of which may not be ':'>
    <trailing> ::= <Any, possibly *empty*, sequence of octets not including
                     NUL or CR or LF>

    <key>      ::= <Any *non-empty* sequence of ASCII letters, digits, or hyphens>
    <vendor>   ::= <hostname>
    <value>    ::= <Any, possibly *empty*, sequence of utf-8 characters except
                   NUL, CR, LF, semicolon (';'), and SPACE>

    <crlf>     ::= CR LF
    """
    parts = element.strip().split(bytes(" ", "utf_8"))
    off = 0
    tags = {}
    if parts[0].startswith(bytes('@', "utf_8")):
        off = 1
        tags_str = parts[0][1:].split(bytes(';', "utf_8"))
        for tag in tags_str:
            tag_parts = tag.split(bytes('=', "utf_8"), maxsplit=1)
            if len(tag_parts) == 2 and len(tag_parts[1]) > 0:
                v = []
                esc = False
                for c in tag_parts[1].decode("utf-8"):
                    match (esc, c):
                        case (True, ':'):
                            v.append(';')
                            esc = False
                        case (True, 's'):
                            v.append(' ')
                            esc = False
                        case (True, '\\'):
                            v.append('\\')
                            esc = False
                        case (True, 'r'):
                            v.append('\r')
                            esc = False
                        case (True, 'n'):
                            v.append('\n')
                            esc = False
                        case (True, _):
                            v.append(c)
                            esc = False
                        case (False, '\\'):
                            esc = True
                        case (False, _):
                            v.append(c)
                tags[tag_parts[0].decode("utf-8")] = "".join(v)
            else:
                tags[tag_parts[0].decode("utf-8")] = None

    if parts[off].startswith(bytes(':', 'utf_8')):
        prefix = parts[off][1:]
        command = parts[off+1]
        args = parts[off+2:]
    else:
        prefix = None
        command = parts[off]
        args = parts[off+1:]

    if command.isdigit():
        try:
            command = numeric_events[command]
        except KeyError:
            pass
    command = command.lower()
    if isinstance(command, bytes):
        command = command.decode("utf_8")

    if args[0].startswith(bytes(':', 'utf_8')):
        args = [bytes(" ", "utf_8").join(args)[1:]]
    else:
        for idx, arg in enumerate(args):
            if arg.startswith(bytes(':', 'utf_8')):
                args = args[:idx] + [bytes(" ", 'utf_8').join(args[idx:])[1:]]
                break

    return tags, prefix, command, args


def parse_nick(name):
    """ parse a nickname and return a tuple of (nick, mode, user, host)

    <nick> [ '!' [<mode> = ] <user> ] [ '@' <host> ]
    """

    try:
        nick, rest = name.split('!')
    except ValueError:
        return (name, None, None, None)
    try:
        mode, rest = rest.split('=')
    except ValueError:
        mode, rest = None, rest
    try:
        user, host = rest.split('@')
    except ValueError:
        return (nick, mode, rest, None)

    return (nick, mode, user, host)
