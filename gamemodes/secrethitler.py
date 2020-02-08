import random
import re
import threading
import functools
from collections import defaultdict
from src.gamemodes import game_mode, GameMode, InvalidModeException
from src.messages import messages
from src.containers import UserList
from src.decorators import command, handle_error
from src.functions import get_players, change_role, get_target, get_main_role
from src.status import add_dying, kill_players
from src.events import EventListener
from src import channels, users

@game_mode("shitler", minp=5, maxp=10, likelihood=1)
class SecretHitlerMode(GameMode):
    """A group of students denied entry into art school get into politics instead."""
    def __init__(self, arg=""):
        super().__init__(arg)
        self.ROLE_REVEAL = "off"
        self.STATS_TYPE = "disabled"
        #self.DEVOICE_DURING_NIGHT = True # This is now set during d1, because of the fake 0 second n1 (used to send out role PMs)
        self.DEFAULT_ROLE = "liberal"
        #self.START_WITH_DAY = True # Wish we could use this but role PMs don't get sent out
        self.ROLE_GUIDE = {
            5: ["hitler", "fascist"],
            7: ["fascist(2)"],
            9: ["fascist(3)"]
        }
        self.EVENTS = {
            "role_attribution": EventListener(self.startup_hack_PLS_IGNORE),
            "chk_win": EventListener(self.on_chk_win, priority=0.1),
            "begin_night": EventListener(self.on_begin_night),
            "begin_day" : EventListener(self.on_begin_day),
            "chk_nightdone": EventListener(self.prolong_night),
            "transition_day_resolve_end": EventListener(self.on_transition_day_resolve_end, priority=2),
            "transition_day_end" : EventListener(self.on_transition_day_end),
            "del_player": EventListener(self.on_del_player),
            "revealroles" : EventListener(self.on_revealroles)
        }

    def startup(self):
        from src import decorators
        super().startup()

        # Delete werewolf-specific commands
        deleted_commands = ["vote", "lynch", "retract", "abstain", "time", "votes"]
        self.saved_commands = {}
        for todel in deleted_commands:
            aliases = messages.raw("_commands")[todel]
            for alias in aliases:
                self.saved_commands[alias] = decorators.COMMANDS[alias]
                del decorators.COMMANDS[alias]

        self.cards = ['F', 'F', 'F', 'F', 'F', 'F', 'F', 'F', 'F', 'F', 'F', 'L', 'L', 'L', 'L', 'L', 'L']
        self.discard = []
        self.enacted = []
        self.to_enact = None # Card we are going to enact once day starts
        self.policies = [] # Policies under consideration at night
        self.already_nominated = False
        self.already_discarded = False
        self.has_enacted = True
        self.has_vetoed = False
        self.hitler_executed = False
        self.hitler_idled = False
        self.hitler_elected = False
        self.reshuffle()

        # Can't do this stuff in here because if an admin uses !fgame shitler, startup() is called immediately
        #pl = get_players()
        #self.president_ineligible = len(pl) >= 6
        #self.president_candidates = copy.copy(pl)
        #self.president = random.choice(self.president_candidates)
        #self.presidential_index = pl.index(self.president)

        self.cannot_nominate = UserList()
        self._chancellor = UserList()
        self._president = UserList()
        self.votes = defaultdict(UserList)
        self.chaos_counter = 0

        self.executive_action_tracks = {
            5 :  [ None,                  None,                 "Policy Peek",            "Execution", "Execution" ],
            6 :  [ None,                  None,                 "Policy Peek",            "Execution", "Execution" ],
            7 :  [ None,                  "Investigate Loyalty", "Call Special Election", "Execution", "Execution" ],
            8 :  [ None,                  "Investigate Loyalty", "Call Special Election", "Execution", "Execution" ],
            9 :  [ "Investigate Loyalty", "Investigate Loyalty", "Call Special Election", "Execution", "Execution" ],
            10 : [ "Investigate Loyalty", "Investigate Loyalty", "Call Special Election", "Execution", "Execution" ],
        }
        #self.executive_actions = executive_action_tracks[len(pl)]
        self.current_action = None

        # Add commands
        self.can_nominate = UserList()
        cmd_params = dict(chan=True, pm=False, playing=True, phases=("day",), users=self.can_nominate)
        self.nominate_command = command("nominate", **cmd_params)(self.nominate_cmd)

        cmd_params = dict(chan=False, pm=True, playing=True, phases=("day",))
        self.vote_command = command("vote", **cmd_params)(self.vote_cmd)
        self.yes_command = command("yes", **cmd_params)(self.yes_cmd)
        self.no_command = command("no", **cmd_params)(self.no_cmd)

        cmd_params = dict(chan=False, pm=True, playing=True, phases=("night",), users=self.can_nominate)
        self.discard_command = command("discard", **cmd_params)(self.discard_cmd)

        self.can_enact = UserList()
        cmd_params = dict(chan=False, pm=True, playing=True, phases=("night",), users=self.can_enact)
        self.enact_command = command("enact", **cmd_params)(self.enact_cmd)

        self.can_investigate = UserList()
        cmd_params = dict(chan=True, pm=True, playing=True, phases=("day",), users=self.can_investigate)
        self.investigate_command = command("investigate", **cmd_params)(self.investigate_cmd)

        self.can_elect = UserList()
        cmd_params = dict(chan=True, pm=True, playing=True, phases=("day",), users=self.can_elect)
        self.call_special_election_command = command("elect", **cmd_params)(self.call_special_election_cmd)

        self.can_execute = UserList()
        cmd_params = dict(chan=True, pm=True, playing=True, phases=("day",), users=self.can_execute)
        self.execute_command = command("execute", **cmd_params)(self.execute_cmd)

        self.can_veto = UserList()
        cmd_params = dict(chan=False, pm=True, playing=True, phases=("night",), users=self.can_veto)
        self.veto_command = command("veto", **cmd_params)(self.veto_cmd)

        self.can_approve_veto = UserList()
        cmd_params = dict(chan=False, pm=True, playing=True, phases=("night",), users=self.can_approve_veto)
        self.approve_command = command("approve", **cmd_params)(self.approve_cmd)
        self.reject_command = command("reject", **cmd_params)(self.reject_cmd)

        self.status_command = command("status", chan=True, pm=True)(self.status_cmd)
        self.cards_command = command("cards", chan=True, pm=True)(self.cards_cmd)
        self.showtrack_command = command("showtrack", chan=True, pm=True)(self.showtrack_cmd)

        # Delete or replace werewolf-specific messages
        deleted_messages = ["villagers_lynch", "daylight_warning", "daylight_warning_killtie", "sunset", "sunset_lynch",
            "twilight_warning", "sunrise", "welcome_simple", "day_lasted", "night_begin", "first_night_begin", "welcome_options",
            "players_list", "endgame_stats"]
        self.saved_messages = { "hitler_notify" : messages.messages["hitler_notify"] }
        for key in deleted_messages:
            self.saved_messages[key] = messages.messages[key]
            messages.messages[key] = ""
        messages.messages["welcome_simple"] = messages.messages["welcome_shitler"]
        messages.messages["welcome_options"] = messages.messages["welcome_shitler"]
        messages.messages["day_lasted"] = messages.messages["day_lasted_shitler"]
        messages.messages["night_begin"] = messages.messages["first_night_begin_shitler"]
        messages.messages["endgame_stats"] = messages.messages["endgame_stats_shitler"]

    def startup_hack_PLS_IGNORE(self, evt, var, chk_win_conditions, villagers):
        pl = get_players()

        self.president_ineligible = len(pl) >= 6
        self.president_candidates = UserList(pl)
        self.president = random.choice(self.president_candidates)
        self.presidential_index = pl.index(self.president)
        self.can_nominate.append(self.president)
        self.executive_actions = self.executive_action_tracks[len(pl)]

    def teardown(self):
        from src import decorators
        super().teardown()

        def remove_command(name, command):
            aliases = messages.raw("_commands")[name]
            for alias in aliases:
                if len(decorators.COMMANDS[alias]) > 1:
                    decorators.COMMANDS[alias].remove(command)
                else:
                    del decorators.COMMANDS[alias]
        
        remove_command("nominate", self.nominate_command)
        remove_command("vote", self.vote_command)
        remove_command("yes", self.yes_command)
        remove_command("no", self.no_command)
        remove_command("discard", self.discard_command)
        remove_command("enact", self.enact_command)
        remove_command("investigate", self.investigate_command)
        remove_command("elect", self.call_special_election_command)
        remove_command("execute", self.execute_command)
        remove_command("status", self.status_command)
        remove_command("cards", self.cards_command)
        remove_command("showtrack", self.showtrack_command)
        remove_command("veto", self.veto_command)
        remove_command("approve", self.approve_command)
        remove_command("reject", self.reject_command)

        # Restore werewolf-specific messages
        for key, value in self.saved_messages.items():
            messages.messages[key] = value

        # Restore werewolf-specific commands
        for key, value in self.saved_commands.items():
            decorators.COMMANDS[key] = value

    @property
    def president(self):
        if self._president:
            return self._president[0]
        else:
            return None

    @president.setter
    def president(self, president):
        self._president.clear()
        self._president.append(president)

    @property
    def chancellor(self):
        if self._chancellor:
            return self._chancellor[0]
        else:
            return None

    @chancellor.setter
    def chancellor(self, chancellor):
        self._chancellor.clear()
        if chancellor:
            self._chancellor.append(chancellor)

    def reshuffle(self):
        self.cards.extend(self.discard)
        self.discard = []
        random.shuffle(self.cards)

    def enact(self, policy):
        self.enacted.append(policy)

    def card_name(self, card):
        return messages.raw("_cards")[card]

    def get_executive_action(self, num_fascist):
        if num_fascist - 1 >= len(self.executive_actions):
            return None
        return self.executive_actions[num_fascist - 1]

    def get_allegiance(self, player):
        role = get_main_role(player)
        if role == "liberal":
            return "Liberal"
        elif role == "fascist" or role == "hitler":
            return "Fascist"
        else:
            raise Exception("Player {0} has role {1} with unknoan allegiance".format(player, role))

    def consider_new_policies(self):
        # Policies under consideration weren't cleared. This should only happen when a chaos government happens.
        if len(self.policies):
            if len(self.policies) != 2:
                raise Exception("Error: Previous policy considerations haven't been cleared")
            self.cards[:0] = self.policies
        if len(self.cards) < 3:
            self.reshuffle()
            channels.Main.send(messages["reshuffled"])
        self.policies = self.cards[0:3]
        del self.cards[0:3]
        self.already_discarded = False
        self.has_enacted = False
        self.has_vetoed = False

    # Get the next president in line
    # Will use the previously stored president information in case president has been overridden by a special election
    def get_next_president(self):
        pl = get_players()
        if self.presidential_index >= len(pl) - 1:
            self.presidential_index = 0
            return pl[0]
        else:
            self.presidential_index = self.presidential_index + 1
            return pl[self.presidential_index]

    def next_president(self, *, force=None):
        if force:
            self.president = force
        else:
            self.president = self.get_next_president()
        self.can_nominate.clear()
        self.can_nominate.append(self.president)
        self.can_enact.clear()
        self.can_veto.clear()
        self.can_approve_veto.clear()
        self.already_nominated = False

    def on_chk_win(self, evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
        if self.hitler_executed:
            evt.data["winner"] = "liberals"
            evt.data["message"] = messages["winner_by_execution"]
        elif self.hitler_idled:
            evt.data["winner"] = "liberals"
            evt.data["message"] = messages["winner_by_idle"]
        elif self.hitler_elected:
            evt.data["winner"] = "fascists"
            evt.data["message"] = messages["winner_by_hitler"]
        elif self.enacted.count("F") >= 6:
            evt.data["winner"] = "fascists"
            evt.data["message"] = messages["winner_by_fascism"]
        elif self.enacted.count("L") >= 5:
            evt.data["winner"] = "liberals"
            evt.data["message"] = messages["winner_by_liberalism"]

        evt.stop_processing = True
    
    def on_begin_night(self, evt, var):
        if var.NIGHT_COUNT > 1:
            self.notify_president()
            self.chancellor.send(messages["chancellor_wait"])

            # It's now night, update ineligible chancellor list for the next day
            self.cannot_nominate = UserList([self.chancellor])
            if self.president_ineligible:
                self.cannot_nominate.append(self.president)

    def prolong_night(self, evt, var):
        if not self.has_enacted:
            evt.data["actedcount"] = -1

    def on_transition_day_end(self, evt, var):
        if var.NIGHT_COUNT == 1:
            return

        if self.to_enact:
            self.enact(self.to_enact)
            self.chaos_counter = 0
            num_liberal = self.enacted.count("L")
            num_fascist = self.enacted.count("F")
            channels.Main.send(messages["legislative_end1"].format(self.card_name(self.to_enact)))
            channels.Main.send(messages["legislative_end2"].format(num_liberal, num_fascist))

        if self.chaos_counter >= 3:
            self.chaos_government()
        self.current_action = None

    def on_begin_day(self, evt, var):
        if var.NIGHT_COUNT == 1:
            channels.Main.send(messages["welcome_commands"])
            # After first night, change the beginning of night message to one asking players to wait on president / chancellor
            messages.messages["night_begin"] = messages.messages["night_begin_shitler"]
            # Hitler is a "wolf" and gets PMed every night, we don't want that
            messages.messages["hitler_notify"] = ""

            # HACK because var.STARTS_WITH_DAY doesn't work well enough. We fake a first night, but don't want devoicing to happen there
            var.ORIGINAL_SETTINGS["DEVOICE_DURING_NIGHT"] = var.DEVOICE_DURING_NIGHT
            var.DEVOICE_DURING_NIGHT = True

        self.consider_new_policies()

        if self.to_enact == "F":
            num_fascist = self.enacted.count("F")
            action = self.get_executive_action(num_fascist)
            if action:
                channels.Main.send(messages["executive_action_granted"].format(action))
                command_required = self.handle_executive_action(action)
                if command_required:
                    return
                self.current_action = None

        self.to_enact = None
        # Don't change president on the fake first night
        if var.NIGHT_COUNT > 1:
            self.next_president()
        self.print_candidate()

    # Called after an executive action that requires a command is completed, need to finally select the next president here
    def after_executive_action(self, *, next_pres=True):
        self.current_action = None
        if next_pres:
            self.next_president()
        self.print_candidate()

    def print_candidate(self):
        channels.Main.send(messages["presidential_candidate"].format(self.president, self.president.nick))
        if self.cannot_nominate:
            if self.president_ineligible:
                channels.Main.send(messages["chancellor_ineligible_pc"].format(self.cannot_nominate))
            else:
                channels.Main.send(messages["chancellor_ineligible_c"].format(self.cannot_nominate))
        if self.chaos_counter == 2:
            channels.Main.send(messages["chaos_warning"])
        if self.enacted.count("F") >= 3:
            channels.Main.send(messages["fascist_warning"])

    def on_transition_day_resolve_end(self, evt, var, victims):
        evt.data["novictmsg"] = False

    def on_revealroles(self, evt, var):
        if self.policies:
            evt.data["output"].append(messages["revealroles_policy"].format(self.policies))

    def on_del_player(self, evt, var, player, all_roles, death_triggers):
        index = self.president_candidates.index(player)
        if index <= self.presidential_index:
            self.presidential_index = self.presidential_index - 1
        self.president_candidates.remove(player)
        
        self.president_ineligible = len(get_players()) >= 6

        # Things past this point are only for handling idlers and people who leave mid-game
        if death_triggers:
            return

        # If hitler died by idling out, replace him with a fascist
        if evt.params.main_role == "hitler":
            fascists = get_players({"fascist"})
            if not fascists:
                self.hitler_idled = True
                return
            random.shuffle(fascists)
            new_hitler = fascists[0]
            change_role(var, new_hitler, "fascist", "hitler", message="fascist_upgrade")

        if player == self.president:
            if var.PHASE == "day":
                channels.Main.send(messages["president_idled_day"])
                self.vote_rejected()
            elif var.PHASE == "night":
                channels.Main.send(messages["president_idled_night"])
                self.agenda_vetoed()
        elif player == self.chancellor:
            if var.PHASE == "day":
                channels.Main.send(messages["chancellor_idled_day"])
                self.chancellor = None
                self.already_nominated = False
                self.can_enact.clear()
                self.can_veto.clear()
                self.votes = defaultdict(UserList)
            elif var.PHASE == "night":
                channels.Main.send(messages["president_idled_night"])
                self.agenda_vetoed()
        elif var.PHASE == "day":
        	self.count_votes()

    def count_votes(self):
        registered_voters = len(get_players())

        votes_yes = len(self.votes["yes"])
        votes_no = len(self.votes["no"])

        if votes_yes + votes_no == registered_voters:
            vote = "JA" if votes_yes > votes_no else "NEIN"
            channels.Main.send(messages["vote_complete"].format(self.president, self.chancellor, vote))
            channels.Main.send(messages["votes_for"].format(self.votes["yes"]))
            channels.Main.send(messages["votes_against"].format(self.votes["no"]))

            self.votes = defaultdict(UserList)

            if votes_yes > votes_no:
                if self.enacted.count("F") >= 3 and get_main_role(self.chancellor) == "hitler":
                    self.hitler_elected = True
                    from src.wolfgame import chk_win
                    chk_win()
                from src.wolfgame import transition_night
                transition_night()
            else:
                self.vote_rejected()

    def vote_rejected(self):
        self.chaos_counter = self.chaos_counter + 1
        if self.chaos_counter >= 3:
            self.chaos_government()
            from src.wolfgame import chk_win
            if chk_win():
                return

        self.next_president()
        self.print_candidate()

    def agenda_vetoed(self):
        self.chaos_counter = self.chaos_counter + 1
        self.can_approve_veto.clear()
        self.discard += self.policies
        self.policies.clear()
        self.chancellor = None
        self.has_enacted = True

    def chaos_government(self):
        self.chaos_counter = 0
        self.cannot_nominate.clear()
        # Policies are popped off self.cards at the beginning of day, but are still "in" the card pile
        if len(self.policies):
            card = self.policies.pop(0)
            self.consider_new_policies()
        # During veto chaos governments, all policies have already been discarded, take from normal card pile
        else:
            card = self.cards.pop(0)
        self.enact(card)

        channels.Main.send(messages["chaos_government"])
        reveal = messages["chaos_reveal"].format(self.card_name(card))
        if self.get_executive_action(self.enacted.count("F")):
            reveal = reveal + messages["chaos_reveal_noaction"]
        channels.Main.send(reveal)

    def notify_president(self):
        card1 = self.card_name(self.policies[0])
        card2 = self.card_name(self.policies[1])
        card3 = self.card_name(self.policies[2])
        self.president.send(messages["president_list_policies"].format(card1, card2, card3))
        self.president.send(messages["president_discard_info"])
        self.president.send(messages["president_communication_reminder"])
    
    def notify_chancellor(self):
        card1 = self.card_name(self.policies[0])
        card2 = self.card_name(self.policies[1])
        self.chancellor.send(messages["chancellor_list_policies"].format(card1, card2))
        self.chancellor.send(messages["chancellor_enact_info"])
        if self.enacted.count("F") >= 5:
            self.chancellor.send(messages["veto_allowed"])

    def handle_executive_action(self, action):
        self.current_action = action
        if action == "Policy Peek":
            card1 = self.card_name(self.policies[0])
            card2 = self.card_name(self.policies[1])
            card3 = self.card_name(self.policies[2])
            self.president.send(messages["policy_peek"].format(card1, card2, card3))
            return False
        elif action == "Investigate Loyalty":
            self.can_investigate.append(self.president)
            self.president.send(messages["investigate_instructions"])
        elif action == "Call Special Election":
            self.can_elect.append(self.president)
            self.president.send(messages["special_election_instructions"])
        elif action == "Execution":
            self.can_execute.append(self.president)
            self.president.send(messages["execute_instructions"])
        else:
            raise Exception("Invalid executive action: " + action)
        return True

    def nominate_cmd(self, var, wrapper, message):
        """Nominate someone to be chancellor."""

        if self.already_nominated:
            wrapper.pm(messages["already_nominated"], notice=True)
            return

        msg = re.split(" +", message)[0].strip()
        selected_chancellor = get_target(var, wrapper, msg, not_self_message="no_nom_self")
        if not selected_chancellor:
            return

        if selected_chancellor in self.cannot_nominate:
            if self.president_ineligible:
                wrapper.pm(messages["cannot_nom_pc"], notice=True)
            else:
                wrapper.pm(messages["cannot_nom_c"], notice=True)
            return
        self.already_nominated = True

        self.chancellor = selected_chancellor
        wrapper.send(messages["select_chancellor"].format(wrapper.source, selected_chancellor))

        self.can_enact.clear()
        self.can_enact.append(self.chancellor)
        if self.enacted.count("F") >= 5:
            self.can_veto.clear()
            self.can_veto.append(self.chancellor)
    
    def vote_cmd(self, var, wrapper, message):
        """Vote yes or no on a nomination."""

        if not self.already_nominated or not self.chancellor:
            wrapper.send(messages["cannot_vote_yet"].format(self.president))
            return

        vote = re.split(" +", message)[0].strip()
        if not vote in ["yes", "no"]:
            wrapper.send(messages["vote_help"])
            return
        self.do_vote(wrapper, vote)

    def yes_cmd(self, var, wrapper, message):
        """Vote yes on a nomination."""

        if not self.already_nominated or not self.chancellor:
            wrapper.send(messages["cannot_vote_yet"].format(self.president))
            return
        
        self.do_vote(wrapper, "yes")
    
    def no_cmd(self, var, wrapper, message):
        """Vote no on a nomination."""

        if not self.already_nominated or not self.chancellor:
            wrapper.send(messages["cannot_vote_yet"].format(self.president))
            return
        
        self.do_vote(wrapper, "no")

    # Called from !vote, !yes, and !no
    def do_vote(self, wrapper, vote):
        # Clear old votes
        for opt in list(self.votes):
            # defaultdict weirdness
            #if not opt in self.votes:
            #    continue
            if wrapper.source in self.votes[opt]:
                self.votes[opt].remove(wrapper.source)
                if not self.votes[opt]:
                    del self.votes[opt]

        if not wrapper.source in self.votes[vote]:
            self.votes[vote].append(wrapper.source)
            wrapper.send(messages["confirm_vote"].format(vote, self.president, self.chancellor))
        
        self.count_votes()

    def discard_cmd(self, var, wrapper, message):
        """Discard a policy option and send the remaining two policy options to the chancellor."""

        if self.already_discarded:
            wrapper.send(messages["president_already_discarded"])
            return

        arg = re.split(" +", message)[0].strip()
        if arg not in ["1", "2", "3"]:
            wrapper.send(messages["president_discard_help"])
            return
        self.already_discarded = True

        discarded = self.policies.pop(int(arg) - 1)
        self.discard.append(discarded)
        wrapper.send(messages["president_discard"].format(arg, self.card_name(discarded)))

        self.notify_chancellor()
    
    def enact_cmd(self, var, wrapper, message):
        """Enact a policy option sent to you by the president."""

        if not self.already_discarded:
            wrapper.send(messages["president_hasnt_discarded"])
            return
        if self.has_vetoed:
            wrapper.send(messages["president_hasnt_vetoed"])
            return

        arg = re.split(" +", message)[0].strip()
        if arg not in ["1", "2"]:
            wrapper.send(messages["chancellor_enact_help"])
            return

        enacted = self.policies.pop(int(arg) - 1)
        self.to_enact = enacted
        self.discard.append(self.policies.pop(0))
        wrapper.send(messages["chancellor_enact"].format(arg, self.card_name(enacted)))
        self.chancellor = None
        self.has_enacted = True

    def investigate_cmd(self, var, wrapper, message):
        """Investigate a player's party affiliation, either Fascist or Liberal."""

        msg = re.split(" +", message)[0].strip()
        to_investigate = get_target(var, wrapper, msg, not_self_message="no_inv_self")
        if not to_investigate:
            return
        self.can_investigate.clear()

        party = self.get_allegiance(to_investigate)
        channels.Main.send(messages["inv_channel"].format(to_investigate))
        wrapper.pm(messages["inv_private"].format(to_investigate, party))
        self.after_executive_action()
    
    def call_special_election_cmd(self, var, wrapper, message):
        """Select a specific person to be the next president, outside of the normal president track."""

        msg = re.split(" +", message)[0].strip()
        to_select = get_target(var, wrapper, msg, not_self_message="no_select_self")
        if not to_select:
            return
        self.can_elect.clear()
        
        channels.Main.send(messages["call_special_election"].format(to_select))

        self.next_president(force=to_select)
        self.after_executive_action(next_pres=False)

    def execute_cmd(self, var, wrapper, message):
        """Select a person to be executed. They will be removed from the game, and if they were hitler, the Liberals will win."""

        msg = re.split(" +", message)[0].strip()
        to_execute = get_target(var, wrapper, msg, not_self_message="no_execute_self")
        if not to_execute:
            return
        self.can_execute.clear()

        executed_role = get_main_role(to_execute)
        channels.Main.send(messages["execute_order"].format(to_execute))
        add_dying(var, to_execute, killer_role=get_main_role(wrapper.source), reason="shitler_execution")
        kill_players(var)

        if executed_role == "hitler":
            channels.Main.send(messages["execute_result_hitler"].format(to_execute))
            self.hitler_executed = True
            from src.wolfgame import chk_win
            chk_win()
        else:
            channels.Main.send(messages["execute_result_not_hitler"].format(to_execute))
            self.after_executive_action()

    def cards_cmd(self, var, wrapper, message):
        """Shows which policies previously been enacted, and the status of the policy deck and discard pile."""

        num_policies = len(self.cards) + len(self.policies)
        num_discard = len(self.discard)
        # It's the middle of the night and president has already discarded - don't change the numbers until night has ended
        if self.already_discarded:
            num_policies = num_policies + 1
            num_discard = num_discard - 1
        pretty_table = []
        for policy in self.enacted:
            pretty_table.append(self.card_name(policy))        
        wrapper.send(messages["show_table"].format(num_policies, num_discard, pretty_table))
    
    def showtrack_cmd(self, var, wrapper, message):
        """Shows the current executive action track for this player count."""

        track = [ action if action else "No Action" for action in self.executive_actions ]
        track = []
        for i in range(len(self.executive_actions)):
            action = self.executive_actions[i]
            if action:
                track.append(messages["show_track_policy"].format(i + 1, action))
        
        wrapper.send(messages["show_track"].format(track))

    def status_cmd(self, var, wrapper, message):
        """Shows the status of the game - AKA who are we waiting on? STOP IDLING."""

        if var.PHASE == "day":
            if self.current_action:
                if self.current_action == "Investigate Loyalty":
                    wrapper.send(messages["waiting_investigation"].format(self.president))
                elif self.current_action == "Call Special Election":
                    wrapper.send(messages["waiting_special_election"].format(self.president))
                elif self.current_action == "Execution":
                    wrapper.send(messages["waiting_execution"].format(self.president))
                else:
                    raise Exception("Unsure what the current executive action is")
                return
            if self.already_nominated:
                if not self.chancellor:
                    raise Exception("Game in invalid state - there is no chancellor")
                pl = get_players()
                for opt in list(self.votes):
                    for player in self.votes[opt]:
                        pl.remove(player)
                wrapper.send(messages["waiting_votes"].format(pl))
            else:
                wrapper.send(messages["waiting_nomination"].format(self.president))
        elif var.PHASE == "night":
            if self.has_vetoed:
                wrapper.send(messages["waiting_veto"].format(self.chancellor))
            elif self.already_discarded:
                wrapper.send(messages["waiting_enact"].format(self.chancellor))
            else:
                wrapper.send(messages["waiting_discard"].format(self.president))
        else:
            raise Exception("Unusure what the status of the game is")

    def results_cmd(self, var, wrapper, message):
        pass

    def veto_cmd(self, var, wrapper, message):
        """Veto the policy options sent to you by the president. If approved by the president, both policies will be discarded."""

        wrapper.send(messages["vetoed"])
        self.president.send(messages["chancellor_wants_veto_priv"])
        channels.Main.send(messages["chancellor_wants_veto_pub"])

        self.has_vetoed = True
        self.can_veto.clear()
        self.can_approve_veto.clear()
        self.can_approve_veto.append(self.president)

    def approve_cmd(self, var, wrapper, message):
        """Approve the chancellor's veto of the proposed policy options."""

        wrapper.send(messages["president_approves_veto_priv"])
        channels.Main.send(messages["president_approves_veto_pub"])

        self.agenda_vetoed()

    def reject_cmd(self, var, wrapper, message):
        """Reject the chancellor's veto of the proposed policy options."""

        wrapper.send(messages["president_rejects_veto_priv"])
        channels.Main.send(messages["president_rejects_veto_pub"])
        self.chancellor.send(messages["veto_rejected"])

        self.has_vetoed = False
        self.can_approve_veto.clear()
