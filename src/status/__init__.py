"""Core game status are exposed here."""

# Define __all__ in each module and concatenate them together here (also star-import everything)
# This allows minimal modification of this file even when the API changes

from src.status.lycanthropy import *
from src.status.lycanthropy import __all__ as lycanthropy_all

__all__ = []

for all_list in (lycanthropy_all,):
    if set(all_list) & set(__all__):
        raise TypeError("Error: duplicate names {0}".format(set(all_list) & set(__all__)))
    __all__.extend(all_list)

del all_list, lycanthropy_all
