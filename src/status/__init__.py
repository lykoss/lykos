"""Core game status are exposed here."""

# For better IDE auto completion, don't try to replace this with a loop
__all__ = [
    "add_absent", "get_absent", "try_absent",
    "add_disease", "remove_disease", "wolves_diseased",
    "add_dying", "is_dying",
    "add_exchange", "try_exchange",
    "add_force_vote", "add_force_abstain", "get_forced_votes", "get_forced_abstains",
    "add_lycanthropy", "add_lycanthropy_scope", "remove_lycanthropy",
    "add_lynch_immunity", "try_lynch_immunity",
    "add_misdirection", "try_misdirection",
    "add_protection", "remove_all_protections", "try_protection",
    "add_silent", "is_silent",
    "add_vote_weight", "get_vote_weight", "remove_vote_weight"
]

from src.status.absent import *
from src.status.disease import *
from src.status.dying import *
from src.status.exchange import *
from src.status.forcevote import *
from src.status.lycanthropy import *
from src.status.lynchimmune import *
from src.status.misdirection import *
from src.status.protection import *
from src.status.silence import *
from src.status.voteweight import *
