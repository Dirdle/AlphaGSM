from utils.cmdparse import cmdparse
from server import Server,ServerError,server as servermodule
from . import multiplexer as mp
import subprocess as sp
import screen
import os
import traceback
from . import program

__all__=["main"]

DEBUG = bool(int(os.environ.get("ALPHAGSM_DEBUG",0)))

def printhandledex(ex):
  if DEBUG:
    traceback.print_exc()
  else:
    print(ex)

def main(name,args):
  if len(args)==1 and args[0].lower() in ("-h","-?","--help"):
    args=["*/*","help"]
  if len(args)<1:
    print("You must specify at least a server to work on")
    print()
    help(name,None)
    return 2
  servers=[args.pop(0)]
  if servers[0].isdigit():
    count=int(servers[0])
    servers=args[:count]
    args=args[count:]
    if count<1:
      print("You must specify at least one server to work on")
      print()
      help(name,None)
      return 2
  banned=set(("help","create")+Server.default_commands)
  for s in servers:
    if s.lower() in banned:
      print(s,"is a banned server name as it's too similar to a command")
      print()
      help(name,None)
      return 2
  if len(args)<1:
    print("You must specify at least a command to run")
    print()
    help(name,None)
    return 1
  cmd,*args=args
  cmd=cmd.lower()
  servers=[tuple(el if el != "all" else "*" for el in splitservername(spec)) for spec in servers]
  if len(servers)==1 and servers[0] == ("*","*") and cmd == "help":
    help(name,None,*args)
    return 0
  servers=[s for user,tag in servers for s in expandserverstar(user,tag,cmd)]
  if len(servers)<1:
    print("No servers found for",cmd)
    print()
    help(name,None)
    return 1
  elif len(servers)>1:
    return runmulti(name,len(servers),servers,[cmd]+args)
  else: # count == 1
    return runone(servers[0],cmd,args)
  return 0

def runone(server,cmd,args):
  user,tag=server
  if user is not None:
    return runas(name,user,tag,[cmd]+args)
  else:
    if cmd == "create":
      if len(args)<1:
        print("Type of server to create is a required argument")
        print()
        help(name,None,cmd)
        return 2
      try:
        server=Server(tag,args[0])
      except ServerError as ex:
        print("Can't create server")
        printhandledex(ex)
        print()
        help(name,None,cmd)
        return 1
      print("Server created")
      if len(args)>1:
        cmd,*args = args[1:]
        cmd = cmd.lower()
        if cmd != "setup":
          print("Only setup can be called after create")
          print()
          help(name,None,cmd)
          return 2
      else:
        cmd = None
        args = ()
    else:
      try:
        server=Server(tag)
      except ServerError as ex:
        print("Can't find server")
        printhandledex(ex)
        print()
        help(name,None)
        return 1
    if cmd is None or cmd == "help":
      help(name,server,*args)
    else:
      try:
        cmdargs=server.get_command_args(cmd)
      except cmdparse.OptionError as ex:
        print("Error parsing arguments and options")
        printhandledex(ex)
        print()
        help(name,server,cmd)
        return 2
      if cmdargs==None:
        print("Unknown command")
        help(name,server,cmd)
        return 2
      try:
        args,opts=cmdparse.parse(args,cmdargs)
      except cmdparse.OptionError as ex:
        print("Error parsing arguments and options")
        printhandledex(ex)
        print()
        help(name,server,cmd)
        return 2
      # needed by activate and deactivate
      program.PATH=os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(os.path.abspath(__file__)))),"alphagsm")
      try:
        server.run_command(cmd,*args,**opts)
      except ServerError as ex:
        print("Error running Command")
        printhandledex(ex)
        return 1
      except Exception as ex:
        print("Error running command")
        traceback.print_exc()
        return 3

def splitservername(name):
  slash=name.find("/")
  if slash<0:
    return None,name
  else:
    return name[:slash],name[slash+1:]

def getallallservers(command):
  if command in {"stop","status","message","backup"}:
    servers=list(screen.list_all_screens())
    if command == "stop":
      print("Saving server list")
      with open(".alphagsmserverlist","w") as f:
        for server in servers:
          f.write(server+"\n")
    print("Using servers for '*/*':",*servers)
    return servers
  elif command == "start":
    servers=[]
    with open(".alphagsmserverlist","r") as f:
      for line in f:
        servers.append(line.strip())
    print("Using servers for '*/*':",*servers)
    return servers
  return []

def getalluserservers():
  servers= [(None,el[:-5]) for el in os.listdir(servermodule.DATAPATH) if el[-5:] == ".json"]
  print("Using servers for '*':",*(tag for user,tag in servers))
  return servers

def expandserverstar(user,tag,cmd):
  if user == "*":
    if tag != "*":
      print("Error: Can't specify a server but '*' user")
      return ()
    else:
      return [splitservername(s) for s in getallallservers(cmd)]
  elif tag == "*" and user == None:
    return getalluserservers()
  else:
    return [(user,tag)]

def getrunascmd(name,user,server,args,multi=False):
  return ["sudo","-Hu",user]+getruncmd(name,server,args,multi=multi)

def getruncmd(name,server,args,multi=False):
  scriptpath=os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(os.path.abspath(__file__)))),"alphagsm-internal")
  return [scriptpath,"1" if multi else "0",name,server]+args

def runas(name,user,server,args):
  ret=sp.call(getrunascmd(name,user,server,args))
  print("Command finished with return status",ret)
  return ret

def _internalisrunning(line):
  return line.decode().strip()=="#%AlphaGSM-INTERNAL%#"

def runmulti(name,count,servers,args):
  multi=mp.Multiplexer()
  for user,server in servers:
    if user is not None:
      cmd=getrunascmd(name,user,server,args,True)
    else:
      cmd=getruncmd(name,server,args,True)
    mp.addtomultiafter(multi,(user+"/" if user is not None else "")+server,_internalisrunning,cmd,stdin=sp.DEVNULL,stdout=sp.PIPE,stderr=sp.STDOUT)
  multi.processall()
  retvals=list(multi.checkreturnvalues().values())
  if len(retvals)!=len(servers):
    print("Warning: Not all servers have returned")
  if all(val==0 for val in retvals):
    return 0
  retvalsnon0=[val for val in retvals if val != 0]
  if all(val==retvalsnon0[0] for val in retvalsnon0):
    return retvalsnon0[0]
  else:
    return 10

def help(name,server,cmd=None,*_):
  if cmd is None:
    print("The Sector-Alpha Game Server Management Script (AlphaGSM)")
    print()
    print(name+" SERVER COMMAND [ARGS...]")
    print(name+" COUNT SERVER... COMMAND [ARGS...]")
    print(
"""
SERVER is the server or servers to process. If a server is specified as 
username/server then we use sudo to run as the relevent user. This is always
possible as root but is up to sudo otherwise and may prompt for a password.
The server can be the special forms "*", which means apply to all the current
user's servers ("username/*" works too), or "*/*" which means run on a command
dependant definitian of "all servers". This last form is only available for a
very limited set of commands. 

If the second calling form is specified there must be EXACTLY COUNT servers
specified.

The available commands are:
  help [COMMAND] : Print a help message. Without a command print this message
        or with a command print detailed help for that command.
  create TYPE [setup ARGS] : Create a new server of the specified type. If setup
        is specified then will call setup on the new server immediately. ARGS is
        passed directly on to setup so see there for the format and options
        available""")
    if server is None:
      for cmd in Server.default_commands:
        cmdparse.shorthelp(cmd,Server.default_command_descriptions.get(cmd,None),Server.default_command_args[cmd])
    else:
      for cmd in server.get_commands():
        cmdparse.shorthelp(cmd,server.get_command_description(cmd),server.get_command_args(cmd))
  else:
    if server is None:
      if cmd not in Server.default_commands:
        print("Unknown Command")
        print()
        help(name,server)
        return
      cmdparse.longhelp(cmd,Server.default_command_descriptions.get(cmd,None),Server.default_command_args[cmd])
    else:
      if cmd not in server.get_commands():
        print("Unknown Command")
        print()
        help(name,server)
        return
      cmdparse.longhelp(cmd,server.get_command_description(cmd),server.get_command_args(cmd))
   
    
