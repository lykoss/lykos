-- Upgrade script to migrate from schema version 1 to 2
PRAGMA foreign_keys = OFF;
BEGIN EXCLUSIVE TRANSACTION;

CREATE TEMPORARY TABLE mergeq (
    oldperson INTEGER,
    newperson INTEGER,
    active BOOLEAN
);

CREATE TABLE player2 (
    id INTEGER PRIMARY KEY,
    -- must be nullable so that we can insert new player records
    person INTEGER REFERENCES person(id) DEFERRABLE INITIALLY DEFERRED,
    account TEXT COLLATE NOCASE,
    hostmask TEXT COLLATE NOCASE,
    active BOOLEAN NOT NULL DEFAULT 1
);

INSERT INTO player2 (
    id,
    person,
    account,
    hostmask,
    active
)
SELECT
    p.id,
    pp.person,
    p.account,
    p.hostmask,
    p.active
FROM player p
JOIN person_player pp
    ON pp.player = p.id;

DROP TABLE player;
ALTER TABLE player2 RENAME TO player;

CREATE INDEX player_idx ON player (account, hostmask, active);
CREATE INDEX person_idx ON player (person);

-- Casefold the player table; we may have multiple records
-- with the same account/hostmask that are active
-- in that case, we need to keep track of them to merge
-- them together later on.
INSERT INTO mergeq (oldperson, newperson, active)
SELECT DISTINCT
    pp1.person,
    MAX(pp2.person),
    0
FROM player p1
JOIN player p2
    ON (p1.account IS NOT NULL AND p1.account = p2.account)
    OR (p1.hostmask IS NOT NULL AND p1.hostmask = p2.hostmask)
JOIN person_player pp1
    ON pp1.player = p1.id
JOIN person_player pp2
    ON pp2.player = p2.id
WHERE
    p1.active = 1
    AND p2.active = 1
    AND p1.id < p2.id
GROUP BY p1.id, pp1.person;

-- person_player no longer needs to exist; it was moved to a column on player
-- it was already set up as a one-to-many relationship, so a mapping table
-- was not needed (mapping tables are for many-to-many relationships)
DROP TABLE person_player;

-- set FKs on warning and warning_sanction to be deferrable, and make
-- sanction type case-insensitive.
CREATE TABLE warning2 (
    id INTEGER PRIMARY KEY,
    target INTEGER NOT NULL REFERENCES person(id) DEFERRABLE INITIALLY DEFERRED,
    sender INTEGER REFERENCES person(id) DEFERRABLE INITIALLY DEFERRED,
    amount INTEGER NOT NULL,
    issued DATETIME NOT NULL,
    expires DATETIME,
    reason TEXT NOT NULL,
    notes TEXT,
    acknowledged BOOLEAN NOT NULL DEFAULT 0,
    deleted BOOLEAN NOT NULL DEFAULT 0,
    deleted_by INTEGER REFERENCES person(id) DEFERRABLE INITIALLY DEFERRED,
    deleted_on DATETIME
);

INSERT INTO warning2 (
    id, target, sender, amount, issued, expires, reason, notes,
    acknowledged, deleted, deleted_by, deleted_on
)
SELECT
    id, target, sender, amount, issued, expires, reason, notes,
    acknowledged, deleted, deleted_by, deleted_on
FROM warning;

DROP TABLE warning;
ALTER TABLE warning2 RENAME TO warning;

CREATE INDEX warning_idx ON warning (target, deleted, issued);
CREATE INDEX warning_sender_idx ON warning (target, sender, deleted, issued);

CREATE TABLE warning_sanction2 (
    warning INTEGER NOT NULL REFERENCES warning(id) DEFERRABLE INITIALLY DEFERRED,
    sanction TEXT NOT NULL COLLATE NOCASE,
    data TEXT
);

INSERT INTO warning_sanction2 (warning, sanction, data)
SELECT warning, sanction, data
FROM warning_sanction;

DROP TABLE warning_sanction;
ALTER TABLE warning_sanction2 RENAME TO warning_sanction;

-- Make game caseless, also modify winner for fool
-- instead of @id, make winner 'fool' and then game_player
-- can be checked to see what fool won (the winning fool gets a team win)
CREATE TABLE game2 (
    id INTEGER PRIMARY KEY,
    gamemode TEXT NOT NULL COLLATE NOCASE,
    options TEXT,
    started DATETIME NOT NULL,
    finished DATETIME NOT NULL,
    gamesize INTEGER NOT NULL,
    winner TEXT COLLATE NOCASE
);

INSERT INTO game2 (id, gamemode, options, started, finished, gamesize, winner)
SELECT id, gamemode, options, started, finished, gamesize, winner
FROM game;

DROP TABLE game;
ALTER TABLE game2 RENAME TO game;

CREATE INDEX game_idx ON game (gamemode, gamesize);

CREATE TABLE game_player_role2 (
    game_player INTEGER NOT NULL REFERENCES game_player(id) DEFERRABLE INITIALLY DEFERRED,
    role TEXT NOT NULL COLLATE NOCASE,
    special BOOLEAN NOT NULL
);

INSERT INTO game_player_role2 (game_player, role, special)
SELECT game_player, role, special
FROM game_player_role;

DROP TABLE game_player_role;
ALTER TABLE game_player_role2 RENAME TO game_player_role;

CREATE INDEX game_player_role_idx ON game_player_role (game_player);

UPDATE game_player
SET team_win = 1
WHERE id IN (
    SELECT gp.id
    FROM game_player gp
    JOIN game g
        ON g.id = gp.game
    JOIN game_player_role gpr
        ON gpr.game_player = gp.id
    WHERE
        gpr.role = 'fool'
        AND g.winner = '@' || gp.player
        AND gp.indiv_win = 1
);

UPDATE game
SET winner = 'fool'
WHERE SUBSTR(winner, 1, 1) = '@';

-- deferrable FK on access
CREATE TABLE access2 (
    person INTEGER NOT NULL PRIMARY KEY REFERENCES person(id) DEFERRABLE INITIALLY DEFERRED,
    template INTEGER REFERENCES access_template(id) DEFERRABLE INITIALLY DEFERRED,
    flags TEXT
);

INSERT INTO access2 (person, template, flags)
SELECT person, template, flags
FROM access;

DROP TABLE access;
ALTER TABLE access2 RENAME TO access;

-- Merge player/person records from mergeq
-- We merge into the newest record, only thing
-- to carry over from the old are warnings and stasis
-- access entries are NOT carried over if the new
-- person has access (if old is non-null and new is null,
-- then access is migrated). If the user has multiple old
-- access records, one is selected arbitrarily.

-- annoyingly, CTEs are only supported on sqlite 3.8.3+
-- and ubuntu 14.04 ships with 3.8.2. I *really* want to
-- just move over to postgres >_>
CREATE TEMPORARY TABLE u (
    player INTEGER,
    person INTEGER,
    active BOOLEAN
);

INSERT INTO u (player, person, active)
SELECT
    p.id,
    COALESCE(mergeq.newperson, p.person),
    COALESCE(mergeq.active, p.active)
FROM player p
LEFT JOIN mergeq
    ON mergeq.oldperson = p.person;

UPDATE player
SET
    person = (SELECT u.person FROM u WHERE u.player = player.id),
    active = (SELECT u.active FROM u WHERE u.player = player.id);

DROP TABLE u;

INSERT OR IGNORE INTO access (person, template, flags)
SELECT
    m.newperson,
    a.template,
    a.flags
FROM mergeq m
JOIN access a
    ON a.person = m.oldperson;

DELETE FROM access
WHERE person IN (SELECT oldperson FROM mergeq);

CREATE TEMPORARY TABLE u (
    id INTEGER,
    target INTEGER,
    sender INTEGER,
    deleted_by INTEGER
);

INSERT INTO u (id, target, sender, deleted_by)
SELECT
    w.id,
    COALESCE(m1.newperson, w.target),
    COALESCE(m2.newperson, w.sender),
    COALESCE(m3.newperson, w.deleted_by)
FROM warning w
LEFT JOIN mergeq m1
    ON m1.oldperson = w.target
LEFT JOIN mergeq m2
    ON m2.oldperson = w.sender
LEFT JOIN mergeq m3
    ON m3.oldperson = w.deleted_by;

UPDATE warning
SET
    target = (SELECT u.target FROM u WHERE u.id = warning.id),
    sender = (SELECT u.sender FROM u WHERE u.id = warning.id),
    deleted_by = (SELECT u.deleted_by FROM u WHERE u.id = warning.id);

DROP TABLE u;

-- finally, blow off our old person records
DELETE FROM person WHERE id IN (SELECT oldperson FROM mergeq);

DROP TABLE mergeq;

COMMIT;
PRAGMA foreign_keys = ON;
