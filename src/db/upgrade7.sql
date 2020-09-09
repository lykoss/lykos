PRAGMA foreign_keys = OFF;
BEGIN EXCLUSIVE TRANSACTION;

CREATE TABLE player2 (
    id INTEGER PRIMARY KEY,
    person INTEGER REFERENCES person(id) DEFERRABLE INITIALLY DEFERRED,
    account_display TEXT NOT NULL,
    account_lower_ascii TEXT NOT NULL COLLATE NOCASE,
    account_lower_rfc1459 TEXT NOT NULL COLLATE NOCASE,
    account_lower_rfc1459_strict TEXT NOT NULL COLLATE NOCASE,
    active BOOLEAN NOT NULL DEFAULT 1
);

CREATE TEMPORARY TABLE player_temp (
    id INTEGER,
    person INTEGER,
    account_display TEXT NOT NULL,
    account_lower_ascii TEXT NOT NULL COLLATE NOCASE,
    account_lower_rfc1459 TEXT NOT NULL COLLATE NOCASE,
    account_lower_rfc1459_strict TEXT NOT NULL COLLATE NOCASE,
    active BOOLEAN NOT NULL
);

-- Clear out all old hostmask-based players by merging them into a '*' player
UPDATE player
SET account = '*'
WHERE
    account IS NULL
    AND hostmask IS NOT NULL;

INSERT INTO player_temp
SELECT
    pl.id,
    pl.person,
    pl.account,
    pl.account,
    replace(replace(replace(replace(pl.account, '[', '{'), ']', '}'), '\', '|'), '^', '~'),
    replace(replace(replace(pl.account, '[', '{'), ']', '}'), '\', '|'),
    pl.active
FROM player pl;

CREATE TEMPORARY TABLE player_fold_temp (
    id INTEGER,
    account_lower_rfc1459 TEXT NOT NULL COLLATE NOCASE
);

INSERT INTO player_fold_temp
SELECT MAX(id), account_lower_rfc1459
FROM player_temp
GROUP BY account_lower_rfc1459;

CREATE TEMPORARY TABLE person_map_temp (
    old INTEGER,
    new INTEGER,
    player INTEGER
);

-- Generate a mapping from person id to most recent player id
INSERT INTO person_map_temp
SELECT DISTINCT pt.person, NULL, pf.id
FROM player_temp pt
JOIN player_fold_temp pf
    ON pt.account_lower_rfc1459 = pf.account_lower_rfc1459;

-- Populate person_map_temp.new
UPDATE person_map_temp
SET new = (SELECT MAX(pmt2.old) FROM person_map_temp pmt2 WHERE pmt2.player = person_map_temp.player);

CREATE TEMPORARY TABLE player_map_temp (
    old INTEGER,
    new INTEGER
);

-- Fold old people into new ones
UPDATE warning
SET
    target = (SELECT pmt.new FROM person_map_temp pmt WHERE pmt.old = target),
    sender = CASE WHEN sender IS NULL THEN NULL ELSE (SELECT pmt.new FROM person_map_temp pmt WHERE pmt.old = sender) END,
    deleted_by = CASE WHEN deleted_by IS NULL THEN NULL ELSE (SELECT pmt.new FROM person_map_temp pmt WHERE pmt.old = deleted_by) END;

UPDATE access
SET person = (SELECT pmt.new FROM person_map_temp pmt WHERE pmt.old = person);

-- Delete old people
DELETE FROM person
WHERE id NOT IN (SELECT new FROM person_map_temp);

-- Generate a mapping from old player id to most recent player id
INSERT INTO player_map_temp
SELECT pt.id, pf.id
FROM player_temp pt
JOIN player_fold_temp pf
    ON pt.account_lower_rfc1459 = pf.account_lower_rfc1459;

-- Grab the most recent player entry given account_lower and merge everyone else into it
-- noinspection SqlWithoutWhere
UPDATE person
SET primary_player = (SELECT pmt.player FROM person_map_temp pmt WHERE pmt.new = person.id);

-- Update game records
UPDATE game_player
SET player = (SELECT pmt.new FROM player_map_temp pmt WHERE pmt.old = game_player.player);

UPDATE bantrack
SET player = (SELECT pmt.new FROM player_map_temp pmt WHERE pmt.old = bantrack.player);

-- Populate new table
INSERT INTO player2
SELECT pt.*
FROM player_fold_temp pf
JOIN player_temp pt
    ON pf.id = pt.id;

-- Rename player2 to player
DROP TABLE player;
ALTER TABLE player2 RENAME TO player;

-- Create indexes
CREATE INDEX player_ascii_idx ON player (account_lower_ascii, active);
CREATE INDEX player_rfc1459_idx ON player (account_lower_rfc1459, active);
CREATE INDEX player_rfc1459_strict_idx ON player (account_lower_rfc1459_strict, active);
CREATE INDEX person_idx ON player (person);

-- Mark '*' player as inactive
UPDATE player SET active = 0 WHERE account_lower_ascii = '*';

DROP TABLE player_temp;
DROP TABLE player_fold_temp;
DROP TABLE person_map_temp;
DROP TABLE player_map_temp;

PRAGMA foreign_key_check;

COMMIT;
PRAGMA foreign_keys = ON;
