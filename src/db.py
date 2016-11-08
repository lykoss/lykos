import sqlite3
import os
import json
import shutil
import sys
import time
from collections import defaultdict
import threading
from datetime import datetime, timedelta

import botconfig
import src.settings as var
from src.utilities import irc_lower, break_long_message, role_order, singular

# increment this whenever making a schema change so that the schema upgrade functions run on start
# they do not run by default for performance reasons
SCHEMA_VERSION = 5

_ts = threading.local()

def init_vars():
    with var.GRAVEYARD_LOCK:
        conn = _conn()
        c = conn.cursor()
        c.execute("""SELECT
                       pl.account,
                       pl.hostmask,
                       pe.notice,
                       pe.simple,
                       pe.deadchat,
                       pe.pingif,
                       pe.stasis_amount,
                       pe.stasis_expires,
                       COALESCE(at.flags, a.flags)
                     FROM person pe
                     JOIN player pl
                       ON pl.person = pe.id
                     LEFT JOIN access a
                       ON a.person = pe.id
                     LEFT JOIN access_template at
                       ON at.id = a.template
                     WHERE pl.active = 1""")

        var.SIMPLE_NOTIFY = set()  # cloaks of people who !simple, who don't want detailed instructions
        var.SIMPLE_NOTIFY_ACCS = set() # same as above, except accounts. takes precedence
        var.PREFER_NOTICE = set()  # cloaks of people who !notice, who want everything /notice'd
        var.PREFER_NOTICE_ACCS = set() # Same as above, except accounts. takes precedence
        var.STASISED = defaultdict(int)
        var.STASISED_ACCS = defaultdict(int)
        var.PING_IF_PREFS = {}
        var.PING_IF_PREFS_ACCS = {}
        var.PING_IF_NUMS = defaultdict(set)
        var.PING_IF_NUMS_ACCS = defaultdict(set)
        var.DEADCHAT_PREFS = set()
        var.DEADCHAT_PREFS_ACCS = set()
        var.FLAGS = defaultdict(str)
        var.FLAGS_ACCS = defaultdict(str)
        var.DENY = defaultdict(set)
        var.DENY_ACCS = defaultdict(set)

        for acc, host, notice, simple, dc, pi, stasis, stasisexp, flags in c:
            if acc is not None:
                acc = irc_lower(acc)
                if simple == 1:
                    var.SIMPLE_NOTIFY_ACCS.add(acc)
                if notice == 1:
                    var.PREFER_NOTICE_ACCS.add(acc)
                if stasis > 0:
                    var.STASISED_ACCS[acc] = stasis
                if pi is not None and pi > 0:
                    var.PING_IF_PREFS_ACCS[acc] = pi
                    var.PING_IF_NUMS_ACCS[pi].add(acc)
                if dc == 1:
                    var.DEADCHAT_PREFS_ACCS.add(acc)
                if flags:
                    var.FLAGS_ACCS[acc] = flags
            elif host is not None:
                # nick!ident lowercased per irc conventions, host uses normal casing
                try:
                    hl, hr = host.split("@", 1)
                    host = irc_lower(hl) + "@" + hr.lower()
                except ValueError:
                    host = host.lower()
                if simple == 1:
                    var.SIMPLE_NOTIFY.add(host)
                if notice == 1:
                    var.PREFER_NOTICE.add(host)
                if stasis > 0:
                    var.STASISED[host] = stasis
                if pi is not None and pi > 0:
                    var.PING_IF_PREFS[host] = pi
                    var.PING_IF_NUMS[pi].add(host)
                if dc == 1:
                    var.DEADCHAT_PREFS.add(host)
                if flags:
                    var.FLAGS[host] = flags

        c.execute("""SELECT
                       pl.account,
                       pl.hostmask,
                       ws.data
                     FROM warning w
                     JOIN warning_sanction ws
                       ON ws.warning = w.id
                     JOIN person pe
                       ON pe.id = w.target
                     JOIN player pl
                       ON pl.person = pe.id
                     WHERE
                       ws.sanction = 'deny command'
                       AND w.deleted = 0
                       AND (
                         w.expires IS NULL
                         OR w.expires > datetime('now')
                       )""")
        for acc, host, command in c:
            if acc is not None:
                acc = irc_lower(acc)
                var.DENY_ACCS[acc].add(command)
            if host is not None:
                host = irc_lower(host)
                var.DENY[host].add(command)

def decrement_stasis(acc=None, hostmask=None):
    peid, plid = _get_ids(acc, hostmask)
    if (acc is not None or hostmask is not None) and peid is None:
        return
    sql = "UPDATE person SET stasis_amount = MAX(0, stasis_amount - 1)"
    params = ()
    if peid is not None:
        sql += " WHERE id = ?"
        params = (peid,)

    conn = _conn()
    with conn:
        c = conn.cursor()
        c.execute(sql, params)

def set_stasis(newamt, acc=None, hostmask=None, relative=False):
    peid, plid = _get_ids(acc, hostmask, add=True)
    _set_stasis(int(newamt), peid, relative)

def _set_stasis(newamt, peid, relative=False):
    conn = _conn()
    with conn:
        c = conn.cursor()
        c.execute("SELECT stasis_amount, stasis_expires FROM person WHERE id = ?", (peid,))
        oldamt, expiry = c.fetchone()
        if relative:
            newamt = oldamt + newamt
        if newamt < 0:
            newamt = 0
        if newamt > oldamt:
            delta = newamt - oldamt
            # increasing stasis, so need to update expiry
            c.execute("""UPDATE person
                         SET
                           stasis_amount = ?,
                           stasis_expires = datetime(CASE WHEN stasis_expires IS NULL
                                                            OR stasis_expires <= datetime('now')
                                                          THEN 'now'
                                                          ELSE stasis_expires END,
                                                     '+{0} hours')
                         WHERE id = ?""".format(int(delta)), (newamt, peid))
        else:
            # decreasing stasis, don't touch expiry
            c.execute("""UPDATE person
                         SET stasis_amount = ?
                         WHERE id = ?""", (newamt, peid))

def expire_stasis():
    conn = _conn()
    with conn:
        c = conn.cursor()
        c.execute("""UPDATE person
                     SET
                       stasis_amount = 0,
                       stasis_expires = NULL
                     WHERE
                       stasis_expires IS NOT NULL
                       AND stasis_expires <= datetime('now')""")

def get_template(name):
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT id, flags FROM access_template WHERE name = ?", (name,))
    row = c.fetchone()
    if row is None:
        return (None, set())
    return (row[0], row[1])

def get_templates():
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT name, flags FROM access_template ORDER BY name ASC")
    tpls = []
    for name, flags in c:
        tpls.append((name, flags))
    return tpls

def update_template(name, flags):
    conn = _conn()
    with conn:
        tid, _ = get_template(name)
        c = conn.cursor()
        if tid is None:
            c.execute("INSERT INTO access_template (name, flags) VALUES (?, ?)", (name, flags))
        else:
            c.execute("UPDATE access_template SET flags = ? WHERE id = ?", (flags, tid))

def delete_template(name):
    conn = _conn()
    with conn:
        tid, _ = get_template(name)
        if tid is not None:
            c = conn.cursor()
            c.execute("DELETE FROM access WHERE template = ?", (tid,))
            c.execute("DELETE FROM access_template WHERE id = ?", (tid,))

def set_access(acc, hostmask, flags=None, tid=None):
    peid, plid = _get_ids(acc, hostmask, add=True)
    if peid is None:
        return
    conn = _conn()
    with conn:
        c = conn.cursor()
        if flags is None and tid is None:
            c.execute("DELETE FROM access WHERE person = ?", (peid,))
        elif tid is not None:
            c.execute("""INSERT OR REPLACE INTO access
                         (person, template, flags)
                         VALUES (?, ?, NULL)""", (peid, tid))
        else:
            c.execute("""INSERT OR REPLACE INTO access
                         (person, template, flags)
                         VALUES (?, NULL, ?)""", (peid, flags))

def toggle_simple(acc, hostmask):
    _toggle_thing("simple", acc, hostmask)

def toggle_notice(acc, hostmask):
    _toggle_thing("notice", acc, hostmask)

def toggle_deadchat(acc, hostmask):
    _toggle_thing("deadchat", acc, hostmask)

def set_pingif(val, acc, hostmask):
    _set_thing("pingif", val, acc, hostmask, raw=False)

def add_game(mode, size, started, finished, winner, players, options):
    """ Adds a game record to the database.

    mode: Game mode (string)
    size: Game size on start (int)
    started: Time when game started (timestamp)
    finished: Time when game ended (timestamp)
    winner: Winning team (string)
    players: List of players (sequence of dict, described below)
    options: Game options (role reveal, stats type, etc., freeform dict)

    Players dict format:
    {
        nick: "Nickname"
        account: "Account name" (or None, "*" is converted to None)
        ident: "Ident"
        host: "Host"
        role: "role name"
        templates: ["template names", ...]
        special: ["special qualities", ... (lover, entranced, etc.)]
        won: True/False
        iwon: True/False
        dced: True/False
    }
    """

    if mode == "roles":
        # Do not record stats for games with custom roles
        return

    # Normalize players dict
    conn = _conn()
    for p in players:
        if p["account"] == "*":
            p["account"] = None
        p["hostmask"] = "{0}!{1}@{2}".format(p["nick"], p["ident"], p["host"])
        c = conn.cursor()
        p["personid"], p["playerid"] = _get_ids(p["account"], p["hostmask"], add=True)
    with conn:
        c = conn.cursor()
        c.execute("""INSERT INTO game (gamemode, options, started, finished, gamesize, winner)
                     VALUES (?, ?, ?, ?, ?, ?)""", (mode, json.dumps(options), started, finished, size, winner))
        gameid = c.lastrowid
        for p in players:
            c.execute("""INSERT INTO game_player (game, player, team_win, indiv_win, dced)
                         VALUES (?, ?, ?, ?, ?)""", (gameid, p["playerid"], p["won"], p["iwon"], p["dced"]))
            gpid = c.lastrowid
            c.execute("""INSERT INTO game_player_role (game_player, role, special)
                         VALUES (?, ?, 0)""", (gpid, p["role"]))
            for tpl in p["templates"]:
                c.execute("""INSERT INTO game_player_role (game_player, role, special)
                             VALUES (?, ?, 0)""", (gpid, tpl))
            for sq in p["special"]:
                c.execute("""INSERT INTO game_player_role (game_player, role, special)
                             VALUES (?, ?, 1)""", (gpid, sq))

def get_player_stats(acc, hostmask, role):
    peid, plid = _get_ids(acc, hostmask)
    if not _total_games(peid):
        return "\u0002{0}\u0002 has not played any games.".format(acc if acc and acc != "*" else hostmask)
    conn = _conn()
    c = conn.cursor()
    c.execute("""SELECT
                   gpr.role AS role,
                   SUM(gp.team_win) AS team,
                   SUM(gp.indiv_win) AS indiv,
                   SUM(gp.team_win OR gp.indiv_win) AS overall,
                   COUNT(1) AS total
                 FROM person pe
                 JOIN player pl
                   ON pl.person = pe.id
                 JOIN game_player gp
                   ON gp.player = pl.id
                 JOIN game_player_role gpr
                   ON gpr.game_player = gp.id
                   AND gpr.role = ?
                 WHERE pe.id = ?
                 GROUP BY role""", (role, peid))
    row = c.fetchone()
    name = _get_display_name(peid)
    if row:
        return ("\u0002{0}\u0002 as \u0002{1[0]}\u0002 | Team wins: {1[1]} ({2:.0%}), "
                "Individual wins: {1[2]} ({3:.0%}), Overall wins: {1[3]} ({4:.0%}), Total games: {1[4]}.").format(name, row, row[1]/row[4], row[2]/row[4], row[3]/row[4])
    return "No stats for \u0002{0}\u0002 as \u0002{1}\u0002.".format(name, role)

def get_player_totals(acc, hostmask):
    peid, plid = _get_ids(acc, hostmask)
    total_games = _total_games(peid)
    if not total_games:
        return "\u0002{0}\u0002 has not played any games.".format(acc if acc and acc != "*" else hostmask)
    conn = _conn()
    c = conn.cursor()
    c.execute("""SELECT
                   gpr.role AS role,
                   COUNT(1) AS total
                 FROM person pe
                 JOIN player pl
                   ON pl.person = pe.id
                 JOIN game_player gp
                   ON gp.player = pl.id
                 JOIN game_player_role gpr
                   ON gpr.game_player = gp.id
                 WHERE pe.id = ?
                 GROUP BY role""", (peid,))
    tmp = {}
    totals = []
    for row in c:
        tmp[row[0]] = row[1]
    order = role_order()
    name = _get_display_name(peid)
    #ordered role stats
    totals = ["\u0002{0}\u0002: {1}".format(r, tmp[r]) for r in order if r in tmp]
    #lover or any other special stats
    totals += ["\u0002{0}\u0002: {1}".format(r, t) for r, t in tmp.items() if r not in order]
    return "\u0002{0}\u0002's totals | \u0002{1}\u0002 games | {2}".format(name, total_games, break_long_message(totals, ", "))

def get_game_stats(mode, size):
    conn = _conn()
    c = conn.cursor()

    if mode == "all":
        c.execute("SELECT COUNT(1) FROM game WHERE gamesize = ?", (size,))
    else:
        c.execute("SELECT COUNT(1) FROM game WHERE gamemode = ? AND gamesize = ?", (mode, size))

    total_games = c.fetchone()[0]
    if not total_games:
        return "No stats for \u0002{0}\u0002 player games.".format(size)

    if mode == "all":
        c.execute("""SELECT
                       winner AS team,
                       COUNT(1) AS games,
                       CASE winner
                         WHEN 'villagers' THEN 0
                         WHEN 'wolves' THEN 1
                         ELSE 2 END AS ord
                     FROM game
                     WHERE
                       gamesize = ?
                       AND winner IS NOT NULL
                     GROUP BY team
                     ORDER BY ord ASC, team ASC""", (size,))
    else:
        c.execute("""SELECT
                       winner AS team,
                       COUNT(1) AS games,
                       CASE winner
                         WHEN 'villagers' THEN 0
                         WHEN 'wolves' THEN 1
                         ELSE 2 END AS ord
                     FROM game
                     WHERE
                       gamemode = ?
                       AND gamesize = ?
                       AND winner IS NOT NULL
                     GROUP BY team
                     ORDER BY ord ASC, team ASC""", (mode, size))

    if mode == "all":
        msg = "\u0002{0}\u0002 player games | ".format(size)
    else:
        msg = "\u0002{0}\u0002 player games (\u0002{1}\u0002) | ".format(size, mode)

    bits = []
    for row in c:
        bits.append("{0} wins: {1} ({2}%)".format(singular(row[0]).title(), row[1], round(row[1]/total_games * 100)))
    bits.append("Total games: {0}".format(total_games))

    return msg + ", ".join(bits)

def get_game_totals(mode):
    conn = _conn()
    c = conn.cursor()

    if mode == "all":
        c.execute("SELECT COUNT(1) FROM game")
    else:
        c.execute("SELECT COUNT(1) FROM game WHERE gamemode = ?", (mode,))

    total_games = c.fetchone()[0]
    if not total_games:
        return "No games have been played in the {0} game mode.".format(mode)

    if mode == "all":
        c.execute("""SELECT
                       gamesize,
                       COUNT(1) AS games
                     FROM game
                     GROUP BY gamesize
                     ORDER BY gamesize ASC""")
    else:
        c.execute("""SELECT
                       gamesize,
                       COUNT(1) AS games
                     FROM game
                     WHERE gamemode = ?
                     GROUP BY gamesize
                     ORDER BY gamesize ASC""", (mode,))
    totals = []
    for row in c:
        totals.append("\u0002{0}p\u0002: {1}".format(*row))

    if mode == "all":
        return "Total games: {0} | {1}".format(total_games, ", ".join(totals))
    else:
        return "Total games (\u0002{0}\u0002): {1} | {2}".format(mode, total_games, ", ".join(totals))

def get_warning_points(acc, hostmask):
    peid, plid = _get_ids(acc, hostmask)
    conn = _conn()
    c = conn.cursor()
    c.execute("""SELECT COALESCE(SUM(amount), 0)
                 FROM warning
                 WHERE
                   target = ?
                   AND deleted = 0
                   AND (
                     expires IS NULL
                     OR expires > datetime('now')
                   )""", (peid,))
    row = c.fetchone()
    return row[0]

def has_unacknowledged_warnings(acc, hostmask):
    peid, plid = _get_ids(acc, hostmask)
    if peid is None:
        return False
    conn = _conn()
    c = conn.cursor()
    c.execute("""SELECT COALESCE(MIN(acknowledged), 1)
                 FROM warning
                 WHERE
                   target = ?
                   AND deleted = 0
                   AND (
                     expires IS NULL
                     OR expires > datetime('now')
                   )""", (peid,))
    row = c.fetchone()
    return not bool(row[0])

def list_all_warnings(list_all=False, skip=0, show=0):
    conn = _conn()
    c = conn.cursor()
    sql = """SELECT
               warning.id,
               COALESCE(plt.account, plt.hostmask) AS target,
               COALESCE(pls.account, pls.hostmask, ?) AS sender,
               warning.amount,
               warning.issued,
               warning.expires,
               CASE WHEN warning.expires IS NULL OR warning.expires > datetime('now')
                    THEN 0 ELSE 1 END AS expired,
               CASE WHEN warning.deleted
                         OR (
                             warning.expires IS NOT NULL
                             AND warning.expires <= datetime('now')
                         )
                    THEN 1 ELSE warning.acknowledged END AS acknowledged,
               warning.deleted,
               warning.reason
             FROM warning
             JOIN person pet
               ON pet.id = warning.target
             JOIN player plt
               ON plt.id = pet.primary_player
             LEFT JOIN person pes
               ON pes.id = warning.sender
             LEFT JOIN player pls
               ON pls.id = pes.primary_player
             """
    if not list_all:
        sql += """WHERE
                    deleted = 0
                    AND (
                      expires IS NULL
                      OR expires > datetime('now')
                    )
                """
    sql += "ORDER BY warning.issued DESC\n"
    if show > 0:
        sql += "LIMIT {0} OFFSET {1}".format(show, skip)

    c.execute(sql, (botconfig.NICK,))
    warnings = []
    for row in c:
        warnings.append({"id": row[0],
                         "target": row[1],
                         "sender": row[2],
                         "amount": row[3],
                         "issued": row[4],
                         "expires": row[5],
                         "expired": row[6],
                         "ack": row[7],
                         "deleted": row[8],
                         "reason": row[9]})
    return warnings

def list_warnings(acc, hostmask, expired=False, deleted=False, skip=0, show=0):
    peid, plid = _get_ids(acc, hostmask)
    conn = _conn()
    c = conn.cursor()
    sql = """SELECT
               warning.id,
               COALESCE(plt.account, plt.hostmask) AS target,
               COALESCE(pls.account, pls.hostmask, ?) AS sender,
               warning.amount,
               warning.issued,
               warning.expires,
               CASE WHEN warning.expires IS NULL OR warning.expires > datetime('now')
                    THEN 0 ELSE 1 END AS expired,
               CASE WHEN warning.deleted
                         OR (
                             warning.expires IS NOT NULL
                             AND warning.expires <= datetime('now')
                         )
                    THEN 1 ELSE warning.acknowledged END AS acknowledged,
               warning.deleted,
               warning.reason
             FROM warning
             JOIN person pet
               ON pet.id = warning.target
             JOIN player plt
               ON plt.id = pet.primary_player
             LEFT JOIN person pes
               ON pes.id = warning.sender
             LEFT JOIN player pls
               ON pls.id = pes.primary_player
             WHERE
               warning.target = ?
             """
    if not deleted:
        sql += " AND deleted = 0"
    if not expired:
        sql += """ AND (
                      expires IS NULL
                      OR expires > datetime('now')
                    )"""
    sql += " ORDER BY warning.issued DESC"
    if show > 0:
        sql += " LIMIT {0} OFFSET {1}".format(show, skip)

    c.execute(sql, (botconfig.NICK, peid))
    warnings = []
    for row in c:
        warnings.append({"id": row[0],
                         "target": row[1],
                         "sender": row[2],
                         "amount": row[3],
                         "issued": row[4],
                         "expires": row[5],
                         "expired": row[6],
                         "ack": row[7],
                         "deleted": row[8],
                         "reason": row[9]})
    return warnings

def get_warning(warn_id, acc=None, hm=None):
    peid, plid = _get_ids(acc, hm)
    conn = _conn()
    c = conn.cursor()
    sql = """SELECT
               warning.id,
               COALESCE(plt.account, plt.hostmask) AS target,
               COALESCE(pls.account, pls.hostmask, ?) AS sender,
               warning.amount,
               warning.issued,
               warning.expires,
               CASE WHEN warning.expires IS NULL OR warning.expires > datetime('now')
                    THEN 0 ELSE 1 END AS expired,
               warning.acknowledged,
               warning.deleted,
               warning.reason,
               warning.notes,
               COALESCE(pld.account, pld.hostmask) AS deleted_by,
               warning.deleted_on
             FROM warning
             JOIN person pet
               ON pet.id = warning.target
             JOIN player plt
               ON plt.id = pet.primary_player
             LEFT JOIN person pes
               ON pes.id = warning.sender
             LEFT JOIN player pls
               ON pls.id = pes.primary_player
             LEFT JOIN person ped
               ON ped.id = warning.deleted_by
             LEFT JOIN player pld
               ON pld.id = ped.primary_player
             WHERE
               warning.id = ?
             """
    params = (botconfig.NICK, warn_id)
    if acc is not None and hm is not None:
        sql += """  AND warning.target = ?
                    AND warning.deleted = 0"""
        params = (botconfig.NICK, warn_id, peid)

    c.execute(sql, params)
    row = c.fetchone()
    if not row:
        return None

    return {"id": row[0],
            "target": row[1],
            "sender": row[2],
            "amount": row[3],
            "issued": row[4],
            "expires": row[5],
            "expired": row[6],
            "ack": row[7],
            "deleted": row[8],
            "reason": row[9],
            "notes": row[10],
            "deleted_by": row[11],
            "deleted_on": row[12],
            "sanctions": get_warning_sanctions(warn_id)}

def get_warning_sanctions(warn_id):
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT sanction, data FROM warning_sanction WHERE warning=?", (warn_id,))
    sanctions = {}
    for sanc, data in c:
        if sanc == "stasis":
            sanctions["stasis"] = int(data)
        elif sanc == "deny command":
            if "deny" not in sanctions:
                sanctions["deny"] = set()
            sanctions["deny"].add(data)

    return sanctions

def add_warning(tacc, thm, sacc, shm, amount, reason, notes, expires):
    teid, tlid = _get_ids(tacc, thm, add=True)
    seid, slid = _get_ids(sacc, shm)
    conn = _conn()
    with conn:
        c = conn.cursor()
        c.execute("""INSERT INTO warning
                     (
                     target, sender, amount,
                     issued, expires,
                     reason, notes,
                     acknowledged
                     )
                     VALUES
                     (
                       ?, ?, ?,
                       datetime('now'), ?,
                       ?, ?,
                       0
                     )""", (teid, seid, amount, expires, reason, notes))
    return c.lastrowid

def add_warning_sanction(warning, sanction, data):
    conn = _conn()
    with conn:
        c = conn.cursor()
        c.execute("""INSERT INTO warning_sanction
                     (warning, sanction, data)
                     VALUES
                     (?, ?, ?)""", (warning, sanction, data))

        if sanction == "tempban":
            # we want to return a list of all banned accounts/hostmasks
            idlist = set()
            acclist = set()
            hmlist = set()
            c.execute("SELECT target FROM warning WHERE id = ?", (warning,))
            peid = c.fetchone()[0]
            c.execute("SELECT id, account, hostmask FROM player WHERE person = ? AND active = 1", (peid,))
            if isinstance(data, datetime):
                sql = "INSERT OR REPLACE INTO bantrack (player, expires) values (?, ?)"
            else:
                sql = "INSERT OR REPLACE INTO bantrack (player, warning_amount) values (?, ?)"
            for row in c:
                idlist.add(row[0])
                if row[1] is None:
                    hmlist.add(row[2])
                else:
                    acclist.add(row[1])
            for plid in idlist:
                c.execute(sql, (plid, data))
            return (acclist, hmlist)

def del_warning(warning, acc, hm):
    peid, plid = _get_ids(acc, hm)
    conn = _conn()
    with conn:
        c = conn.cursor()
        c.execute("""UPDATE warning
                     SET
                       acknowledged = 1,
                       deleted = 1,
                       deleted_on = datetime('now'),
                       deleted_by = ?
                     WHERE
                       id = ?
                       AND deleted = 0""", (peid, warning))

def set_warning(warning, expires, reason, notes):
    conn = _conn()
    with conn:
        c = conn.cursor()
        c.execute("""UPDATE warning
                     SET reason = ?, notes = ?, expires = ?
                     WHERE id = ?""", (reason, notes, expires, warning))

def acknowledge_warning(warning):
    conn = _conn()
    with conn:
        c = conn.cursor()
        c.execute("UPDATE warning SET acknowledged = 1 WHERE id = ?", (warning,))

def expire_tempbans():
    conn = _conn()
    with conn:
        idlist = set()
        acclist = set()
        hmlist = set()
        c = conn.cursor()
        c.execute("""SELECT
                       bt.player,
                       pl.account,
                       pl.hostmask
                     FROM bantrack bt
                     JOIN player pl
                       ON pl.id = bt.player
                     WHERE
                       (bt.expires IS NOT NULL AND bt.expires < datetime('now'))
                       OR (
                         bt.warning_amount IS NOT NULL
                         AND bt.warning_amount >= (
                           SELECT COALESCE(SUM(w.amount), 0)
                           FROM warning w
                           WHERE
                             w.target = pl.person
                             AND w.deleted = 0
                             AND (
                               w.expires IS NULL
                               OR w.expires > datetime('now')
                             )
                         )
                       )""")
        for row in c:
            idlist.add(row[0])
            if row[1] is None:
                hmlist.add(row[2])
            else:
                acclist.add(row[1])
        for plid in idlist:
            c.execute("DELETE FROM bantrack WHERE player = ?", (plid,))
        return (acclist, hmlist)

def get_pre_restart_state():
    conn = _conn()
    with conn:
        c = conn.cursor()
        c.execute("SELECT players FROM pre_restart_state")
        players = c.fetchone()
        if players is None:
            # missing state row
            c.execute("INSERT INTO pre_restart_state (players) VALUES (NULL)")
            players = []
        else:
            c.execute("UPDATE pre_restart_state SET players=NULL")
            players = players[0]
            if players is not None:
                players = players.split()
    return players

def set_pre_restart_state(players):
    if not players:
        return
    conn = _conn()
    with conn:
        c = conn.cursor()
        c.execute("UPDATE pre_restart_state SET players = ?", (" ".join(players),))

def _upgrade(oldversion):
    # try to make a backup copy of the database
    print ("Performing schema upgrades, this may take a while.", file=sys.stderr)
    have_backup = False
    try:
        print ("Creating database backup...", file=sys.stderr)
        shutil.copyfile("data.sqlite3", "data.sqlite3.bak")
        have_backup = True
        print ("Database backup created at data.sqlite3.bak...", file=sys.stderr)
    except OSError:
        print ("Database backup failed! Hit Ctrl+C to abort, otherwise upgrade will continue in 5 seconds...", file=sys.stderr)
        time.sleep(5)

    dn = os.path.dirname(__file__)
    conn = _conn()
    try:
        with conn:
            c = conn.cursor()
            if oldversion < 2:
                print ("Upgrade from version 1 to 2...", file=sys.stderr)
                # Update FKs to be deferrable, update collations to nocase where it makes sense,
                # and clean up how fool wins are tracked (giving fools team wins instead of saving the winner's
                # player id as a string). When nocasing players, this may cause some records to be merged.
                with open(os.path.join(dn, "db", "upgrade2.sql"), "rt") as f:
                    c.executescript(f.read())
            if oldversion < 3:
                print ("Upgrade from version 2 to 3...", file=sys.stderr)
                with open(os.path.join(dn, "db", "upgrade3.sql"), "rt") as f:
                    c.executescript(f.read())
            if oldversion < 4:
                print ("Upgrade from version 3 to 4...", file=sys.stderr)
                # no actual upgrades, just wanted to force an index rebuild
            if oldversion < 5:
                print ("Upgrade from version 4 to 5...", file=sys.stderr)
                c.execute("CREATE INDEX game_gamesize_idx ON game (gamesize)")

            print ("Rebuilding indexes...", file=sys.stderr)
            c.execute("REINDEX")
            c.execute("PRAGMA user_version = " + str(SCHEMA_VERSION))
            print ("Upgrades complete!", file=sys.stderr)
    except sqlite3.Error:
        print ("An error has occurred while upgrading the database schema.",
               "Please report this issue to ##werewolf-dev on irc.freenode.net.",
               "Include all of the following details in your report:",
               sep="\n", file=sys.stderr)
        if have_backup:
            try:
                shutil.copyfile("data.sqlite3.bak", "data.sqlite3")
            except OSError:
                print ("An error has occurred while restoring your database backup.",
                       "You can manually move data.sqlite3.bak to data.sqlite3 to restore the original database.",
                       sep="\n", file=sys.stderr)
        raise

def _migrate():
    # try to make a backup copy of the database
    import shutil
    try:
        shutil.copyfile("data.sqlite3", "data.sqlite3.bak")
    except OSError:
        pass
    dn = os.path.dirname(__file__)
    conn = _conn()
    with conn, open(os.path.join(dn, "db", "db.sql"), "rt") as f1, open(os.path.join(dn, "db", "migrate.sql"), "rt") as f2:
        c = conn.cursor()
        #######################################################
        # Step 1: install the new schema (from db.sql script) #
        #######################################################
        c.executescript(f1.read())

        ################################################################
        # Step 2: migrate relevant info from the old schema to the new #
        ################################################################
        c.executescript(f2.read())

        ######################################################################
        # Step 3: Indicate we have updated the schema to the current version #
        ######################################################################
        c.execute("PRAGMA user_version = " + str(SCHEMA_VERSION))

def _install():
    dn = os.path.dirname(__file__)
    conn = _conn()
    with conn, open(os.path.join(dn, "db", "db.sql"), "rt") as f1:
        c = conn.cursor()
        c.executescript(f1.read())
        c.execute("PRAGMA user_version = " + str(SCHEMA_VERSION))

def _get_ids(acc, hostmask, add=False):
    conn = _conn()
    c = conn.cursor()
    if acc == "*":
        acc = None
    if acc is None and hostmask is None:
        return (None, None)
    elif acc is None:
        c.execute("""SELECT pe.id, pl.id
                     FROM player pl
                     JOIN person pe
                       ON pe.id = pl.person
                     WHERE
                       pl.account IS NULL
                       AND pl.hostmask = ?
                       AND pl.active = 1""", (hostmask,))
    else:
        hostmask = None
        c.execute("""SELECT pe.id, pl.id
                     FROM player pl
                     JOIN person pe
                       ON pe.id = pl.person
                     WHERE
                       pl.account = ?
                       AND pl.hostmask IS NULL
                       AND pl.active = 1""", (acc,))
    row = c.fetchone()
    peid = None
    plid = None
    if row:
        peid, plid = row
    elif add:
        with conn:
            c.execute("INSERT INTO player (account, hostmask) VALUES (?, ?)", (acc, hostmask))
            plid = c.lastrowid
            c.execute("INSERT INTO person (primary_player) VALUES (?)", (plid,))
            peid = c.lastrowid
            c.execute("UPDATE player SET person=? WHERE id=?", (peid, plid))
    return (peid, plid)

def _get_display_name(peid):
    if peid is None:
        return None
    conn = _conn()
    c = conn.cursor()
    c.execute("""SELECT COALESCE(pp.account, pp.hostmask)
                 FROM person pe
                 JOIN player pp
                   ON pp.id = pe.primary_player
                 WHERE pe.id = ?""", (peid,))
    return c.fetchone()[0]

def _total_games(peid):
    if peid is None:
        return 0
    conn = _conn()
    c = conn.cursor()
    c.execute("""SELECT COUNT(DISTINCT gp.game)
                 FROM person pe
                 JOIN player pl
                   ON pl.person = pe.id
                 JOIN game_player gp
                   ON gp.player = pl.id
                 WHERE
                   pe.id = ?""", (peid,))
    # aggregates without GROUP BY always have exactly one row,
    # so no need to check for None here
    return c.fetchone()[0]

def _set_thing(thing, val, acc, hostmask, raw=False):
    conn = _conn()
    with conn:
        c = conn.cursor()
        peid, plid = _get_ids(acc, hostmask, add=True)
        if raw:
            params = (peid,)
        else:
            params = (val, peid)
            val = "?"
        c.execute("""UPDATE person SET {0} = {1} WHERE id = ?""".format(thing, val), params)

def _toggle_thing(thing, acc, hostmask):
    _set_thing(thing, "CASE {0} WHEN 1 THEN 0 ELSE 1 END".format(thing), acc, hostmask, raw=True)

def _conn():
    try:
        return _ts.conn
    except AttributeError:
        _ts.conn = sqlite3.connect("data.sqlite3")
        with _ts.conn:
            c = _ts.conn.cursor()
            c.execute("PRAGMA foreign_keys = ON")
        # remap NOCASE to be IRC casing
        _ts.conn.create_collation("NOCASE", _collate_irc)
        return _ts.conn

def _collate_irc(s1, s2):
    # treat hostmasks specially, otherwise call irc_lower on stuff
    if "@" in s1:
        hl, hr = s1.split("@", 1)
        s1 = irc_lower(hl) + "@" + hr.lower()
    else:
        s1 = irc_lower(s1)

    if "@" in s2:
        hl, hr = s2.split("@", 1)
        s2 = irc_lower(hl) + "@" + hr.lower()
    else:
        s2 = irc_lower(s2)

    if s1 == s2:
        return 0
    elif s1 < s2:
        return -1
    else:
        return 1

need_install = not os.path.isfile("data.sqlite3")
conn = _conn()
with conn:
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON")
    if need_install:
        _install()
    c.execute("PRAGMA user_version")
    row = c.fetchone()
    ver = row[0]
    c.close()

if ver == 0:
    # new schema does not exist yet, migrate from old schema
    # NOTE: game stats are NOT migrated to the new schema; the old gamestats table
    # will continue to exist to allow queries against it, however given how horribly
    # inaccurate the stats on it are, it would be a disservice to copy those inaccurate
    # statistics over to the new schema which has the capability of actually being accurate.
    _migrate()
elif ver < SCHEMA_VERSION:
    _upgrade(ver)

del need_install, conn, c, ver

# vim: set expandtab:sw=4:ts=4:
