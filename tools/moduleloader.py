import os
import botconfig

MODULES = {}

for modfile in os.listdir("modules"):
    if modfile == "common.py":
        continue  # no need to load this one
    if modfile.startswith("__"):
        continue
    if not modfile.endswith(".py"):
        continue  # not a module
    if not os.path.isfile("modules/"+modfile):
        continue  # not a file
        
    modfile = modfile[:-3]
    
    print("Loading module "+modfile)
    
    MODULES[modfile] = getattr(__import__("modules."+modfile), modfile)
    
if botconfig.DEFAULT_MODULE in MODULES.keys():
    CURRENT_MODULE = botconfig.DEFAULT_MODULE.lower()
else:
    CURRENT_MODULE = "wolfgame"
