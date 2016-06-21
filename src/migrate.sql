-- First, create our player entries
INSERT INTO player (
	account,
	hostmask,
	active
)
SELECT DISTINCT
	account,
	NULL,
	1
FROM (
	SELECT player AS account FROM rolestats
	UNION ALL
	SELECT acc AS account FROM allowed_accs
	UNION ALL
	SELECT user AS account FROM deadchat_prefs WHERE is_account = 1
	UNION ALL
	SELECT acc AS account FROM denied_accs
	UNION ALL
	SELECT user AS account FROM pingif_prefs WHERE is_account = 1
	UNION ALL
	SELECT acc AS account FROM prefer_notice_acc
	UNION ALL
	SELECT acc AS account FROM simple_role_accs
	UNION ALL
	SELECT acc AS account FROM stasised_accs
) t1
UNION ALL
SELECT DISTINCT
	NULL,
	hostmask,
	1
FROM (
	SELECT cloak AS hostmask FROM allowed
	UNION ALL
	SELECT user AS hostmask FROM deadchat_prefs WHERE is_account = 0
	UNION ALL
	SELECT cloak AS hostmask FROM denied
	UNION ALL
	SELECT user AS hostmask FROM pingif_prefs WHERE is_account = 0
	UNION ALL
	SELECT cloak AS hostmask FROM prefer_notice
	UNION ALL
	SELECT cloak AS hostmask FROM simple_role_notify
	UNION ALL
	SELECT cloak AS hostmask FROM stasised
) t2;

-- Create our person entries (we assume a 1:1 person:player mapping for migration)
INSERT INTO person (
	primary_player,
	notice,
	simple,
	deadchat,
	pingif,
	stasis_amount,
	stasis_expires
)
SELECT
	pl.id,
	EXISTS(SELECT 1 FROM prefer_notice_acc pna WHERE pna.acc = pl.account)
		OR EXISTS(SELECT 1 FROM prefer_notice pn WHERE pn.cloak = pl.hostmask),
	EXISTS(SELECT 1 FROM simple_role_accs sra WHERE sra.acc = pl.account)
		OR EXISTS(SELECT 1 FROM simple_role_notify srn WHERE srn.cloak = pl.hostmask),
	EXISTS(SELECT 1 FROM deadchat_prefs dp
			WHERE dp.user = COALESCE(pl.account, pl.hostmask)
				AND dp.is_account = CASE WHEN pl.account IS NOT NULL THEN 1 ELSE 0 END),
	pi.players,
	COALESCE(sa.games, sh.games, 0),
	CASE WHEN COALESCE(sa.games, sh.games) IS NOT NULL
		THEN DATETIME('now', '+' || COALESCE(sa.games, sh.games) || ' hours')
		ELSE NULL END
FROM player pl
LEFT JOIN pingif_prefs pi
	ON pi.user = COALESCE(pl.account, pl.hostmask)
	AND pi.is_account = CASE WHEN pl.account IS NOT NULL THEN 1 ELSE 0 END
LEFT JOIN stasised sh
	ON sh.cloak = pl.hostmask
LEFT JOIN stasised_accs sa
	ON sa.acc = pl.account;

INSERT INTO person_player (person, player)
SELECT id, primary_player FROM person;

-- Port allowed/denied stuff to the new format
-- (allowed to access entries, denied to warnings)
CREATE TEMPORARY TABLE access_flags_map (
	command TEXT NOT NULL,
	flag TEXT NOT NULL
);
INSERT INTO access_flags_map
(command, flag)
VALUES
-- uppercase = dangerous to give out, lowercase = more ok to give out
-- F = full admin commands
('fallow', 'F'),
('fdeny', 'F'),
('fsend', 'F'),
-- s = speak commands
('fsay', 's'),
('fact', 's'),
-- d = debug commands
('fday', 'd'),
('fnight', 'd'),
('force', 'd'),
('rforce', 'd'),
('frole', 'd'),
('fgame', 'd'),
-- D = Dangerous commands
('fdie', 'D'),
('frestart', 'D'),
('fpull', 'D'),
('faftergame', 'D'),
('flastgame', 'D'),
-- A = administration commands
('fjoin', 'A'),
('fleave', 'A'),
('fstasis', 'A'),
('fstart', 'A'),
('fstop', 'A'),
('fwait', 'A'),
('fspectate', 'A'),
-- a = auspex commands
('revealroles', 'a'),
-- j = joke commands
('fgoat', 'j'),
-- m = management commands
('fsync', 'm');

INSERT INTO access (person, flags)
SELECT pe.id, GROUP_CONCAT(t.flag, '')
FROM (
	SELECT DISTINCT pl.id AS player, afm.flag AS flag
	FROM allowed a
	JOIN player pl
		ON pl.hostmask = a.cloak
	JOIN access_flags_map afm
		ON afm.command = a.command
	UNION
	SELECT DISTINCT pl.id AS player, afm.flag AS flag
	FROM allowed_accs a
	JOIN player pl
		ON pl.account = a.acc
	JOIN access_flags_map afm
		ON afm.command = a.command
) t
JOIN person pe
	ON pe.primary_player = t.player
GROUP BY pe.id;

INSERT INTO warning (
	target,
	amount,
	issued,
	reason,
	notes
)
SELECT
	pe.id,
	0,
	DATETIME('now'),
	'Unknown',
	'Automatically generated warning from migration'
FROM (
	SELECT DISTINCT pl.id AS player
	FROM denied d
	JOIN player pl
		ON pl.hostmask = d.cloak
	UNION
	SELECT DISTINCT pl.id AS player
	FROM denied_accs d
	JOIN player pl
		ON pl.account = d.acc
) t
JOIN person pe
	ON pe.primary_player = t.player;

INSERT INTO warning_sanction (
	warning,
	sanction,
	data
)
SELECT DISTINCT
	w.id,
	'deny command',
	COALESCE(dh.command, da.command)
FROM warning w
JOIN person pe
	ON pe.id = w.target
JOIN player pl
	ON pl.id = pe.primary_player
LEFT JOIN denied dh
	ON dh.cloak = pl.hostmask
LEFT JOIN denied_accs da
	ON da.acc = pl.account;

DROP TABLE access_flags_map;

-- Finally, clean up old tables
-- gamestats and rolestats are kept for posterity since that data is not migrated
-- pre_restart_state is kept because it is still used in the new schema
DROP TABLE allowed;
DROP TABLE allowed_accs;
DROP TABLE deadchat_prefs;
DROP TABLE denied;
DROP TABLE denied_accs;
DROP TABLE pingif_prefs;
DROP TABLE prefer_notice;
DROP TABLE prefer_notice_acc;
DROP TABLE roles;
DROP TABLE simple_role_accs;
DROP TABLE simple_role_notify;
DROP TABLE stasised;
DROP TABLE stasised_accs;
