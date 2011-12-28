import botconfig
from datetime import datetime

class WolfgameLogger(object):

    def __init__(self, outfile, boutfile):
        self.outfile = outfile
        self.boutfile = boutfile
        
        self.logged = ""
        self.barelogged = ""
        
    def log(self, message):
        self.logged += datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S ") + message + "\n"
        
    def logBare(self, *args):
        self.barelogged += datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S ") + " ".join(args) + "\n"
        
    def logChannelMessage(self, who, message):
        self.logged += datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S ") + "<{0}> {1}\n".format(who, message)
        
    def logCommand(self, who, cmd, rest):
        self.logged += datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S ") + "<{0}> {1}{2} {3}".format(who, botconfig.CMD_CHAR, cmd, rest) + "\n"
        
    def logMessage(self, message):
        self.logged += datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S ") + "<{0}> ".format(botconfig.NICK)+message+"\n"
        
    def saveToFile(self):
        if self.outfile:
            with open(self.outfile, "a") as lf:
                lf.write(self.logged)
                
        if self.boutfile:
            with open(self.boutfile, "a") as bl:
                bl.write(self.barelogged)
            
        self.logged = ""
        self.barelogged = ""
