-- upgrade script to migrate from version 2 to version 3

CREATE TABLE bantrack (
	player INTEGER NOT NULL PRIMARY KEY REFERENCES player(id) DEFERRABLE INITIALLY DEFERRED,
	expires DATETIME,
	warning_amount INTEGER
);

