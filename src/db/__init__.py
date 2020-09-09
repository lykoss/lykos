import sqlite3
import os
import json
import shutil
import sys
import time
from collections import defaultdict
import threading
from datetime import datetime

import botconfig
import src.settings as var
from src.utilities import singular
from src.messages import messages, get_role_name
from src.cats import role_order

# increment this whenever making a schema change so that the schema upgrade functions run on start
# they do not run by default for performance reasons
SCHEMA_VERSION = 7

_ts = threading.local()

def init_vars():
    from src.context import lower
    with var.GRAVEYARD_LOCK:
        conn = _conn()
        c = conn.cursor()
        c.execute("""SELECT
                       pl.account_display,
                       pe.notice,
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

        var.PREFER_NOTICE_ACCS = set() # Same as above, except accounts. takes precedence
        var.STASISED_ACCS = defaultdict(int)
        var.PING_IF_PREFS_ACCS = {}
        var.PING_IF_NUMS_ACCS = defaultdict(set)
        var.DEADCHAT_PREFS_ACCS = set()
        var.FLAGS_ACCS = defaultdict(str)
        var.DENY_ACCS = defaultdict(set)

        for acc, notice, dc, pi, stasis, stasisexp, flags in c:
            if acc is not None:
                lacc = lower(acc)
                if notice == 1:
                    var.PREFER_NOTICE_ACCS.add(lacc)
                if stasis > 0:
                    var.STASISED_ACCS[lacc] = stasis
                if pi is not None and pi > 0:
                    var.PING_IF_PREFS_ACCS[lacc] = pi
                    var.PING_IF_NUMS_ACCS[pi].add(lacc)
                if dc == 1:
                    var.DEADCHAT_PREFS_ACCS.add(lacc)
                if flags:
                    var.FLAGS_ACCS[lacc] = flags

        c.execute("""SELECT
                       pl.account_display,
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
        for acc, command in c:
            if acc is not None:
                lacc = lower(acc)
                var.DENY_ACCS[lacc].add(command)

def decrement_stasis(acc=None):
    peid, plid = _get_ids(acc)
    if acc is not None and peid is None:
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

def set_stasis(newamt, acc=None, relative=False):
    peid, plid = _get_ids(acc, add=True)
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

def set_access(acc, flags=None, tid=None):
    peid, plid = _get_ids(acc, add=True)
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

def toggle_notice(acc):
    _toggle_thing("notice", acc)

def toggle_deadchat(acc):
    _toggle_thing("deadchat", acc)

def set_pingif(val, acc):
    _set_thing("pingif", val, acc, raw=False)

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
        version: 3
        account: "Account name"
        main_role: "role name"
        all_roles: ["role name", ...]
        special: ["special qualities", ... (lover, entranced, etc.)]
        team_win: True/False
        individual_win: True/False
        dced: True/False
    }
    """

    # Normalize players dict
    conn = _conn()
    for p in players:
        c = conn.cursor()
        p["personid"], p["playerid"] = _get_ids(p["account"], add=True)
    with conn:
        c = conn.cursor()
        c.execute("""INSERT INTO game (gamemode, options, started, finished, gamesize, winner)
                     VALUES (?, ?, ?, ?, ?, ?)""", (mode, json.dumps(options), started, finished, size, winner))
        gameid = c.lastrowid
        for p in players:
            c.execute("""INSERT INTO game_player (game, player, team_win, indiv_win, dced)
                         VALUES (?, ?, ?, ?, ?)""", (gameid, p["playerid"], p["team_win"], p["individual_win"], p["dced"]))
            gpid = c.lastrowid
            for role in p["all_roles"]:
                c.execute("""INSERT INTO game_player_role (game_player, role, special)
                             VALUES (?, ?, 0)""", (gpid, role))
            for sq in p["special"]:
                c.execute("""INSERT INTO game_player_role (game_player, role, special)
                             VALUES (?, ?, 1)""", (gpid, sq))

def get_player_stats(acc, role):
    peid, plid = _get_ids(acc)
    if not _total_games(peid):
        return messages["db_pstats_no_game"].format(acc)
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
        role, team, indiv, overall, total = row
        return messages["db_player_stats"].format(name, role=role, team=team, teamp=team/total, indiv=indiv, indivp=indiv/total, overall=overall, overallp=overall/total, total=total)
    return messages["db_pstats_no_role"].format(name, role)

def get_player_totals(acc):
    peid, plid = _get_ids(acc)
    total_games = _total_games(peid)
    if not total_games:
        return (messages["db_pstats_no_game"].format(acc), [])
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
    c.execute("""SELECT SUM(gp.team_win OR gp.indiv_win)
                 FROM game_player gp
                 JOIN player pl
                   ON pl.id = gp.player
                 JOIN person pe
                   ON pe.id = pl.person
                 WHERE pe.id = ?""", (peid,))
    won_games = c.fetchone()[0]
    order = list(role_order())
    name = _get_display_name(peid)
    #ordered role stats
    totals = [messages["db_role_games"].format(r, tmp[r]) for r in order if r in tmp]
    #lover or any other special stats
    totals += [messages["db_role_games"].format(r, t) for r, t in tmp.items() if r not in order]
    return (messages["db_total_games"].format(name, total_games, won_games / total_games), totals)

def get_game_stats(mode, size):
    conn = _conn()
    c = conn.cursor()

    if mode == "all":
        c.execute("SELECT COUNT(1) FROM game WHERE gamesize = ?", (size,))
    else:
        c.execute("SELECT COUNT(1) FROM game WHERE gamemode = ? AND gamesize = ?", (mode, size))

    total_games = c.fetchone()[0]
    if not total_games:
        return messages["db_gstats_no_game"].format(size)

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

    key = "db_gstats_specific"
    if mode == "all":
        key = "db_gstats_all"

    bits = []
    for row in c:
        winner = singular(row[0])
        winner = get_role_name(winner, number=None).title()
        if not winner:
            winner = botconfig.NICK.title()
        bits.append(messages["db_gstats_win"].format(winner, row[1], row[1]/total_games))
    bits.append(messages["db_gstats_total"].format(total_games))

    return messages[key].format(size, mode, bits)

def get_game_totals(mode):
    conn = _conn()
    c = conn.cursor()

    if mode == "all":
        c.execute("SELECT COUNT(1) FROM game")
    else:
        c.execute("SELECT COUNT(1) FROM game WHERE gamemode = ?", (mode,))

    total_games = c.fetchone()[0]
    if not total_games:
        if mode == "all":
            return messages["db_gstats_gm_none_all"]
        return messages["db_gstats_gm_none"].format(mode)

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
        totals.append(messages["db_gstats_gm_p"].format(row[0], row[1]))

    if mode == "all":
        return messages["db_gstats_gm_all_total"].format(total_games, totals)
    return messages["db_gstats_gm_specific_total"].format(mode, total_games, totals)

def get_role_stats(role, mode=None):
    conn = _conn()
    c = conn.cursor()

    if mode is None:
        c.execute("""SELECT
                   gpr.role AS role,
                   SUM(gp.team_win) AS team,
                   SUM(gp.indiv_win) AS indiv,
                   SUM(gp.team_win OR gp.indiv_win) AS overall,
                   COUNT(1) AS total
                 FROM game g
                 JOIN game_player gp
                   ON gp.game = g.id
                 JOIN game_player_role gpr
                   ON gpr.game_player = gp.id
                 WHERE role = ?
                 GROUP BY role""", (role,))
    else:
        c.execute("""SELECT
                   gpr.role AS role,
                   SUM(gp.team_win) AS team,
                   SUM(gp.indiv_win) AS indiv,
                   SUM(gp.team_win OR gp.indiv_win) AS overall,
                   COUNT(1) AS total,
                   g.gamemode AS gamemode
                 FROM game g
                 JOIN game_player gp
                   ON gp.game = g.id
                 JOIN game_player_role gpr
                   ON gpr.game_player = gp.id
                 WHERE role = ?
                   AND gamemode = ?
                 GROUP BY role, gamemode""", (role, mode))

    row = c.fetchone()
    if row:
        if mode is None:
            role, team, indiv, overall, total = row
            return messages["db_role_stats_global"].format(role=role, team=team, teamp=team/total, indiv=indiv, indivp=indiv/total, overall=overall, overallp=overall/total, total=total)

        role, team, indiv, overall, total, gamemode = row
        return messages["db_role_stats_specific"].format(gamemode, role=role, team=team, teamp=team/total, indiv=indiv, indivp=indiv/total, overall=overall, overallp=overall/total, total=total)

    if mode is None:
        return messages["db_rstats_none"].format(role)
    return messages["db_rstats_specific"].format(role, mode)

def get_role_totals(mode=None):
    conn = _conn()
    c = conn.cursor()
    if mode is None:
        c.execute("SELECT COUNT(1) FROM game")
    else:
        c.execute("SELECT COUNT(1) FROM game WHERE gamemode = ?", (mode,))
    total_games = c.fetchone()[0]
    if not total_games:
        if mode is None:
            return (None, [messages["db_rstats_nogame"]])
        return (None, [messages["db_rstats_no_mode"].format(mode)])

    if mode is None:
        c.execute("""SELECT
                   gpr.role AS role,
                  COUNT(1) AS count
                  FROM game_player_role gpr
                  GROUP BY role
                  ORDER BY count DESC""")
    else:
        c.execute("""SELECT
                   gpr.role AS role,
                  COUNT(1) AS count
                  FROM game_player_role gpr
                  JOIN game_player gp
                    ON gp.id = gpr.game_player
                  JOIN game g
                    ON g.id = gp.game
                  WHERE g.gamemode = ?
                  GROUP BY role
                  ORDER BY count DESC""", (mode,))

    totals = []
    for role, count in c:
        totals.append(messages["db_role_games"].format(role, count))
    if mode is None:
        return (messages["db_rstats_total"].format(total_games), totals)
    return (messages["db_rstats_total_mode"].format(mode, total_games), totals)

def get_warning_points(acc):
    peid, plid = _get_ids(acc)
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

def has_unacknowledged_warnings(acc):
    peid, plid = _get_ids(acc)
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
               plt.account_display AS target,
               COALESCE(pls.account_display, ?) AS sender,
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

def list_warnings(acc, expired=False, deleted=False, skip=0, show=0):
    peid, plid = _get_ids(acc)
    conn = _conn()
    c = conn.cursor()
    sql = """SELECT
               warning.id,
               plt.account_display AS target,
               COALESCE(pls.account_display, ?) AS sender,
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

def get_warning(warn_id, acc=None):
    conn = _conn()
    c = conn.cursor()
    sql = """SELECT
               warning.id,
               plt.account_display AS target,
               COALESCE(pls.account_display, ?) AS sender,
               warning.amount,
               warning.issued,
               warning.expires,
               CASE WHEN warning.expires IS NULL OR warning.expires > datetime('now')
                    THEN 0 ELSE 1 END AS expired,
               warning.acknowledged,
               warning.deleted,
               warning.reason,
               warning.notes,
               pld.account_display AS deleted_by,
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
    if acc is not None:
        peid, plid = _get_ids(acc)
        if peid is None:
            return None

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

def add_warning(tacc, sacc, amount, reason, notes, expires):
    teid, tlid = _get_ids(tacc, add=True)
    seid, slid = _get_ids(sacc)
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

def del_warning(warning, acc):
    peid, plid = _get_ids(acc)
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
        c = conn.cursor()
        c.execute("""SELECT
                       bt.player,
                       pl.account_display
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
            if row[1] is not None:
                acclist.add(row[1])
        for plid in idlist:
            c.execute("DELETE FROM bantrack WHERE player = ?", (plid,))
        return acclist

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
    print("Performing schema upgrades, this may take a while.", file=sys.stderr)
    have_backup = False
    try:
        print("Creating database backup...", file=sys.stderr)
        shutil.copyfile("data.sqlite3", "data.sqlite3.bak")
        have_backup = True
        print("Database backup created at data.sqlite3.bak...", file=sys.stderr)
    except OSError:
        print("Database backup failed! Hit Ctrl+C to abort, otherwise upgrade will continue in 5 seconds...", file=sys.stderr)
        time.sleep(5)

    dn = os.path.dirname(__file__)
    conn = _conn()
    try:
        with conn:
            c = conn.cursor()
            if oldversion < 2:
                print("Upgrade from version 1 to 2...", file=sys.stderr)
                # Update FKs to be deferrable, update collations to nocase where it makes sense,
                # and clean up how fool wins are tracked (giving fools team wins instead of saving the winner's
                # player id as a string). When nocasing players, this may cause some records to be merged.
                with open(os.path.join(dn, "upgrade2.sql"), "rt") as f:
                    c.executescript(f.read())
            if oldversion < 3:
                print("Upgrade from version 2 to 3...", file=sys.stderr)
                with open(os.path.join(dn, "upgrade3.sql"), "rt") as f:
                    c.executescript(f.read())
            if oldversion < 4:
                print("Upgrade from version 3 to 4...", file=sys.stderr)
                # no actual upgrades, just wanted to force an index rebuild
            if oldversion < 5:
                print("Upgrade from version 4 to 5...", file=sys.stderr)
                c.execute("CREATE INDEX game_gamesize_idx ON game (gamesize)")
            if oldversion < 6:
                print("Upgrade from version 5 to 6...", file=sys.stderr)
                # no actual upgrades, need to force an index rebuild due to removing custom collation
            if oldversion < 7:
                print("Upgrade from version 6 to 7...", file=sys.stderr)
                # add source column to player and initialize it to 'irc'
                # also delete hostmask column
                with open(os.path.join(dn, "upgrade7.sql"), "rt") as f:
                    c.executescript(f.read())

            print("Rebuilding indexes...", file=sys.stderr)
            c.execute("REINDEX")
            c.execute("PRAGMA user_version = " + str(SCHEMA_VERSION))
            print("Upgrades complete!", file=sys.stderr)
    except sqlite3.Error:
        print("An error has occurred while upgrading the database schema.",
              "Please report this issue to #lykos on irc.freenode.net.",
              "Include all of the following details in your report:",
              sep="\n", file=sys.stderr)
        if have_backup:
            try:
                shutil.copyfile("data.sqlite3.bak", "data.sqlite3")
            except OSError:
                print("An error has occurred while restoring your database backup.",
                      "You can manually move data.sqlite3.bak to data.sqlite3 to restore the original database.",
                      sep="\n", file=sys.stderr)
        raise

def _migrate():
    # try to make a backup copy of the database
    try:
        shutil.copyfile("data.sqlite3", "data.sqlite3.bak")
    except OSError:
        pass
    dn = os.path.dirname(__file__)
    conn = _conn()
    with conn, open(os.path.join(dn, "db.sql"), "rt") as f1, open(os.path.join(dn, "migrate.sql"), "rt") as f2:
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
    with conn, open(os.path.join(dn, "db.sql"), "rt") as f1:
        c = conn.cursor()
        c.executescript(f1.read())
        c.execute("PRAGMA user_version = " + str(SCHEMA_VERSION))

def _get_ids(acc, add=False, casemap="ascii"):
    from src.context import lower
    conn = _conn()
    c = conn.cursor()
    if acc == "*":
        acc = None
    if acc is None:
        return (None, None)

    ascii_acc = lower(acc, casemapping="ascii")
    rfc1459_acc = lower(acc, casemapping="rfc1459")
    strict_acc = lower(acc, casemapping="strict-rfc1459")

    c.execute("""SELECT pe.id, pl.id, pl.account_display
                 FROM player pl
                 JOIN person pe
                   ON pe.id = pl.person
                 WHERE
                   pl.account_lower_{0} = ?
                   AND pl.active = 1""".format(casemap), (acc,))
    row = c.fetchone()
    peid = None
    plid = None
    if not row:
        # Maybe have an IRC casefolded version of this account in the db
        # Check in order of most restrictive to least restrictive
        if casemap == "ascii":
            peid, plid = _get_ids(strict_acc, add=add, casemap="rfc1459_strict")
        else:
            peid, plid = _get_ids(rfc1459_acc, add=add, casemap="rfc1459")
        row = peid, plid, None

    if row:
        peid, plid, display_acc = row
        if acc != display_acc:
            # normalize case in the db to what it should be
            with conn:
                c.execute("""UPDATE player
                             SET
                               account_display=?,
                               account_lower_ascii=?,
                               account_lower_rfc1459=?,
                               account_lower_rfc1459_strict=?
                             WHERE id=?""",
                          (acc, ascii_acc, rfc1459_acc, strict_acc, row[1]))
            # fix up our vars
            init_vars()
    elif add:
        with conn:
            c.execute("""INSERT INTO player
                         (
                           account_display,
                           account_lower_ascii,
                           account_lower_rfc1459,
                           account_lower_rfc1459_strict
                         )
                         VALUES (?, ?, ?, ?)""", (acc, ascii_acc, rfc1459_acc, strict_acc))
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
    c.execute("""SELECT pp.account_display
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

def _set_thing(thing, val, acc, raw=False):
    conn = _conn()
    with conn:
        c = conn.cursor()
        peid, plid = _get_ids(acc, add=True)
        if raw:
            params = (peid,)
        else:
            params = (val, peid)
            val = "?"
        c.execute("""UPDATE person SET {0} = {1} WHERE id = ?""".format(thing, val), params)

def _toggle_thing(thing, acc):
    _set_thing(thing, "CASE {0} WHEN 1 THEN 0 ELSE 1 END".format(thing), acc, raw=True)

def _conn():
    try:
        return _ts.conn
    except AttributeError:
        _ts.conn = sqlite3.connect("data.sqlite3", isolation_level=None)
        with _ts.conn:
            c = _ts.conn.cursor()
            c.execute("PRAGMA foreign_keys = ON")
        return _ts.conn

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
