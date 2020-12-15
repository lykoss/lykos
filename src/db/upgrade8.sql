ALTER TABLE person
ADD achievement_current INTEGER NOT NULL DEFAULT 0;

ALTER TABLE person
ADD achievement_total INTEGER NOT NULL DEFAULT 0;

CREATE TABLE achievement (
    id INTEGER PRIMARY KEY,
    player INTEGER NOT NULL REFERENCES person(id) DEFERRABLE INITIALLY DEFERRED,
    achievement TEXT NOT NULL,
    points INTEGER NOT NULL,
    earned DATETIME NOT NULL
);

CREATE INDEX achievement_idx ON achievement (player, achievement);
CREATE INDEX achievement_achievement_idx ON achievement (achievement);
