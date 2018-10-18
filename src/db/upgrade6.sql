-- upgrade script to migrate from version 5 to version 6
PRAGMA foreign_keys = OFF;
BEGIN EXCLUSIVE TRANSACTION;

CREATE TABLE person2 (
    id INTEGER PRIMARY KEY,
    primary_player INTEGER NOT NULL UNIQUE REFERENCES player(id) DEFERRABLE INITIALLY DEFERRED,
    notice BOOLEAN NOT NULL DEFAULT 0,
    simple BOOLEAN NOT NULL DEFAULT 0,
    deadchat BOOLEAN NOT NULL DEFAULT 1,
    pingif TEXT,
    stasis_amount INTEGER NOT NULL DEFAULT 0,
    stasis_expires DATETIME
);

-- pingif has been updated from a single threshold to multiple thresholds
-- as a result, the field is changed from INTEGER to TEXT
-- copy over the entire table and cast pingif to TEXT
INSERT INTO person2 (
    id,
    primary_player,
    notice,
    simple,
    deadchat,
    pingif,
    stasis_amount,
    stasis_expires
)
SELECT
    id,
    primary_player,
    notice,
    simple,
    deadchat,
    CAST(pingif AS TEXT),
    stasis_amount,
    stasis_expires
FROM person;

DROP TABLE person;
ALTER TABLE person2 RENAME TO person;

COMMIT;
PRAGMA foreign_keys = ON;
