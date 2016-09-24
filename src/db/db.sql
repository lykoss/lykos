-- Base schema, when editing be sure to increment the SCHEMA_VERSION in src/db.py
-- Additionally, add the appropriate bits to the update function, as this script
-- does not perform alters on already-existing tables

-- Player tracking. This is just what the bot decides is a unique player, two entries
-- here may end up corresponding to the same actual person (see below).
CREATE TABLE player (
    id INTEGER PRIMARY KEY,
    -- What person this player record belongs to
    person INTEGER REFERENCES person(id) DEFERRABLE INITIALLY DEFERRED,
    -- NickServ account name, or NULL if this player is based on a hostmask
    account TEXT COLLATE NOCASE,
    -- Hostmask for the player, if not based on an account (NULL otherwise)
    hostmask TEXT COLLATE NOCASE,
    -- If a player entry needs to be retired (for example, an account expired),
    -- setting this to 0 allows for that entry to be re-used without corrupting old stats/logs
    active BOOLEAN NOT NULL DEFAULT 1
);

CREATE INDEX player_idx ON player (account, hostmask, active);
CREATE INDEX person_idx ON player (person);

-- Person tracking; a person can consist of multiple players (for example, someone may have
-- an account player for when they are logged in and 3 hostmask players for when they are
-- logged out depending on what connection they are using).
CREATE TABLE person (
    id INTEGER PRIMARY KEY,
    -- Primary player for this person
    primary_player INTEGER NOT NULL UNIQUE REFERENCES player(id) DEFERRABLE INITIALLY DEFERRED,
    -- If 1, the bot will notice the player instead of sending privmsgs
    notice BOOLEAN NOT NULL DEFAULT 0,
    -- If 1, the bot will send simple role notifications to the player
    simple BOOLEAN NOT NULL DEFAULT 0,
    -- If 1, the bot will automatically join the player to deadchat upon them dying
    deadchat BOOLEAN NOT NULL DEFAULT 1,
    -- Pingif preference for the person, or NULL if they do not wish to be pinged
    pingif INTEGER,
    -- Amount of stasis this person has (stasis prevents them from joining games while active)
    -- each time a game is started, this is decremented by 1, to a minimum of 0
    stasis_amount INTEGER NOT NULL DEFAULT 0,
    -- When the given stasis expires, represented in 'YYYY-MM-DD HH:MM:SS' format
    stasis_expires DATETIME
);

-- Sometimes people are bad, this keeps track of that for the purpose of automatically applying
-- various sanctions and viewing the past history of someone. Outside of specifically-marked
-- fields, records are never modified or deleted from this table once inserted.
CREATE TABLE warning (
    id INTEGER PRIMARY KEY,
    -- The target (recipient) of the warning
    target INTEGER NOT NULL REFERENCES person(id) DEFERRABLE INITIALLY DEFERRED,
    -- The person who gave out the warning, or NULL if it was automatically generated
    sender INTEGER REFERENCES person(id) DEFERRABLE INITIALLY DEFERRED,
    -- Number of warning points
    amount INTEGER NOT NULL,
    -- When the warning was issued ('YYYY-MM-DD HH:MM:SS')
    issued DATETIME NOT NULL,
    -- When the warning expires ('YYYY-MM-DD HH:MM:SS') or NULL if it never expires
    expires DATETIME,
    -- Reason for the warning (shown to the target)
    -- Can be edited after the warning is issued
    reason TEXT NOT NULL,
    -- Optonal notes for the warning (only visible to admins)
    -- Can be edited after the warning is issued
    notes TEXT,
    -- Set to 1 if the warning was acknowledged by the target
    acknowledged BOOLEAN NOT NULL DEFAULT 0,
    -- Set to 1 if the warning was rescinded by an admin before it expired
    deleted BOOLEAN NOT NULL DEFAULT 0,
    -- If the warning was rescinded, this tracks by whom
    deleted_by INTEGER REFERENCES person(id) DEFERRABLE INITIALLY DEFERRED,
    -- If the warning was rescinded, this tracks when that happened ('YYYY-MM-DD HH:MM:SS')
    deleted_on DATETIME
);

CREATE INDEX warning_idx ON warning (target, deleted, issued);
CREATE INDEX warning_sender_idx ON warning (target, sender, deleted, issued);

-- In addition to giving warning points, a warning may have specific sanctions attached
-- that apply until the warning expires; for example preventing a user from joining deadchat
-- or denying them access to a particular command (such as !goat).
CREATE TABLE warning_sanction (
    -- The warning this sanction is attached to
    warning INTEGER NOT NULL REFERENCES warning(id) DEFERRABLE INITIALLY DEFERRED,
    -- The type of sanction this is
    sanction TEXT NOT NULL COLLATE NOCASE,
    -- If the sanction type has additional data attached, it is listed here
    data TEXT
);

-- A running tally of all games played, game stats are aggregated from this table
-- This shouldn't be too horribly slow, but if it is some strategies can be employed to speed it up:
-- On startup, aggregate everything from this table and store in-memory, then increment those in-memory
-- counts as games are played.
CREATE TABLE game (
    id INTEGER PRIMARY KEY,
    -- The gamemode played
    gamemode TEXT NOT NULL COLLATE NOCASE,
    -- Game options (role reveal, stats type, etc.), stored as JSON string
	-- The json1 extension can be loaded into sqlite to allow for easy querying of these values
	-- lykos itself does not make use of this field when calculating stats at this time
    options TEXT,
    -- When the game was started
    started DATETIME NOT NULL,
    -- When the game was finished
    finished DATETIME NOT NULL,
    -- Game size (at game start)
    gamesize INTEGER NOT NULL,
    -- Winning team (NULL if no winner)
    winner TEXT COLLATE NOCASE
);

CREATE INDEX game_idx ON game (gamemode, gamesize);
CREATE INDEX game_gamesize_idx ON game (gamesize);

-- List of people who played in each game
CREATE TABLE game_player (
    id INTEGER PRIMARY KEY,
    game INTEGER NOT NULL REFERENCES game(id) DEFERRABLE INITIALLY DEFERRED,
    player INTEGER NOT NULL REFERENCES player(id) DEFERRABLE INITIALLY DEFERRED,
    -- 1 if the player has a team win for this game
    team_win BOOLEAN NOT NULL,
    -- 1 if the player has an individual win for this game
    indiv_win BOOLEAN NOT NULL,
    -- 1 if the player died due to a dc (kick, quit, idled out)
    dced BOOLEAN NOT NULL
);

CREATE INDEX game_player_game_idx ON game_player (game);
CREATE INDEX game_player_player_idx ON game_player (player);

-- List of all roles and other special qualities (e.g. lover, entranced, etc.) the player had in game
CREATE TABLE game_player_role (
    game_player INTEGER NOT NULL REFERENCES game_player(id) DEFERRABLE INITIALLY DEFERRED,
    -- Name of the role or other quality recorded
    role TEXT NOT NULL COLLATE NOCASE,
    -- 1 if role is a special quality instead of an actual role/template name
    special BOOLEAN NOT NULL
);

CREATE INDEX game_player_role_idx ON game_player_role (game_player);

-- Access templates; instead of manually specifying flags, a template can be used to add a group of
-- flags simultaneously.
CREATE TABLE access_template (
	id INTEGER PRIMARY KEY,
	-- Template name, for display purposes
	name TEXT NOT NULL,
	-- Flags this template grants
	flags TEXT
);

-- Access control, owners still need to be specified in botconfig, but everyone else goes here
CREATE TABLE access (
	person INTEGER NOT NULL PRIMARY KEY REFERENCES person(id) DEFERRABLE INITIALLY DEFERRED,
	-- Template to base this person's access on, or NULL if it is not based on a template
	template INTEGER REFERENCES access_template(id) DEFERRABLE INITIALLY DEFERRED,
	-- If template is NULL, this is the list of flags that will be used
	-- Has no effect if template is not NULL
	flags TEXT
);

-- Holds bans that the bot is tracking (due to sanctions)
CREATE TABLE bantrack (
	player INTEGER NOT NULL PRIMARY KEY REFERENCES player(id) DEFERRABLE INITIALLY DEFERRED,
	expires DATETIME,
	warning_amount INTEGER
);

-- Used to hold state between restarts
CREATE TABLE pre_restart_state (
	-- List of players to ping after the bot comes back online
	players TEXT
);
