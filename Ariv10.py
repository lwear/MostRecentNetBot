# Binary Search
# Tracking
# Favour close targets
# Smarter varying precision
# Run to safest corner
# Begin scanning before shell explodes

import os
import sys
import argparse
import time
import signal
import math
import random

# include the netbot src directory in sys.path so we can import modules from it.
robotpath = os.path.dirname(os.path.abspath(__file__))
srcpath = os.path.join(os.path.dirname(robotpath),"src") 
sys.path.insert(0,srcpath)

from netbots_log import log
from netbots_log import setLogLevel
import netbots_ipc as nbipc
import netbots_math as nbmath

robotName = "Ariv10"

def scanQuadrant(x1, y1, x2, y2):

    center = nbmath.angle(x1, y1, x2, y2)
    scanStart = nbmath.normalizeAngle(center - math.pi / 4)
    scanEnd = nbmath.normalizeAngle(center + math.pi / 4)

    return botSocket.sendRecvMessage({'type': 'scanRequest', 'startRadians': scanStart, 'endRadians': scanEnd})['distance']

def getPrecision(d, botRadius):

    precision = 2 * math.atan(botRadius / d)

    return precision

def nearCorner(x, y, arenaSize, limit):

    return (x < limit and y < limit) or (x < limit and y > arenaSize - limit) or (x > arenaSize - limit and y < limit) or (x > arenaSize - limit and y > arenaSize - limit)

# returns true if within limit distance of a wall
def nearWall(x, y, arenaSize):
    limit = 100
    return x < limit or x > arenaSize - limit or y < limit or y > arenaSize - limit

# returns direction to closest wall
def findClosestWall(x, y, arenaSize):
    
    # find distance to each wall
    leftWallDist = x
    rightWallDist = arenaSize - x
    topWallDist = arenaSize - y
    bottomWallDist = y
    
    minimum = min(leftWallDist, rightWallDist, topWallDist, bottomWallDist)
    
    if minimum == leftWallDist: return math.pi
    elif minimum == rightWallDist: return 0
    elif minimum == topWallDist: return math.pi / 2
    elif minimum == bottomWallDist: return 3 * math.pi / 2

def play(botSocket, srvConf):
    gameNumber = 0  # The last game number bot got from the server (0 == no game has been started)

    while True:
        try:
            # Get information to determine if bot is alive (health > 0) and if a new game has started.
            getInfoReply = botSocket.sendRecvMessage({'type': 'getInfoRequest'})
        except nbipc.NetBotSocketException as e:
            # We are always allowed to make getInfoRequests, even if our health == 0. Something serious has gone wrong.
            log(str(e), "FAILURE")
            log("Is netbot server still running?")
            quit()

        if getInfoReply['health'] == 0:
            # we are dead, there is nothing we can do until we are alive again.
            continue

        if getInfoReply['gameNumber'] != gameNumber: 
            # A new game has started. Record new gameNumber and reset any variables back to their initial state
            gameNumber = getInfoReply['gameNumber']
            log("Game " + str(gameNumber) + " has started. Points so far = " + str(getInfoReply['points']))

            ############################################################################
            # Reset Variables For New Game
            ############################################################################
            
            # minimum distance a bot's shell can be shot without hurting itself
            minDist = srvConf['explRadius'] + srvConf['botRadius']

            # start game scanning
            mode = "scan"

            # scan the area in this many slices
            scanSlices = 1

            # This is the radians of where the next scan will be
            scanStart = 0

            # width of scan
            scanSliceWidth = math.pi * 2 / scanSlices
			
            # if target has been found
            targetLocked = False
            targetFound = False

            lastKnownDist = 1500

            resetScan = False

            # corner related variables
            inCorner = False
            claimedCorner = False


            #########################
            # Run to safest Corner
            #########################

            getLocationReply = botSocket.sendRecvMessage({'type': 'getLocationRequest'})
            x = getLocationReply['x']
            y = getLocationReply['y']
            a = srvConf['arenaSize']

            center = nbmath.angle(x, y, 1000, 1000)
            scanStart = nbmath.normalizeAngle(center - math.pi / 4)
            scanEnd = nbmath.normalizeAngle(center + math.pi / 4)

            # scan towards each corner
            d1 = scanQuadrant(x, y, a, a)
            d2 = scanQuadrant(x, y, 0, a)
            d3 = scanQuadrant(x, y, 0, 0)
            d4 = scanQuadrant(x, y, a, 0)

            # add a buffer, so bot doesn't run into wall
            a -= srvConf['botRadius']

            # pick safest corner
            if d1 == 0:
                cornerX = a
                cornerY = a
            elif d2 == 0:
                cornerX = srvConf['botRadius']
                cornerY = a
            elif d3 == 0:
                cornerX = srvConf['botRadius']
                cornerY = srvConf['botRadius']
            elif d4 == 0:
                cornerX = a
                cornerY = srvConf['botRadius']
            else:
                
                # if no safe corner,
                # find the closest corner:
                if x < srvConf['arenaSize'] / 2:
                    cornerX = srvConf['botRadius']
                else:
                    cornerX = a

                if y < srvConf['arenaSize'] / 2:
                    cornerY = srvConf['botRadius']
                else:
                    cornerY = a

        try:
                
            ##############################################
            # Movement
            ##############################################

            if not inCorner:
                getLocationReply = botSocket.sendRecvMessage({'type': 'getLocationRequest'})
                inCorner = nearCorner(getLocationReply['x'], getLocationReply['y'], srvConf['arenaSize'], 50)

                # get location data from server
                getLocationReply = botSocket.sendRecvMessage({'type': 'getLocationRequest'})
                
                # angle to corner
                reqAngle = nbmath.angle(getLocationReply['x'], getLocationReply['y'], cornerX, cornerY)
                reqSpeed = 100

                # try to face new direction
                botSocket.sendRecvMessage({'type': 'setDirectionRequest', 'requestedDirection': reqAngle})
                # try to accelerate
                botSocket.sendRecvMessage({'type': 'setSpeedRequest', 'requestedSpeed': reqSpeed})

            ################################
            # Check Mode
            ################################
            getCanonReply = botSocket.sendRecvMessage({'type': 'getCanonRequest'})

            """
            if mode == "wait":
                if not getCanonReply['shellInProgress']:
                    # ready to shoot
                    mode = "scan"
            """

            ###############################################
            # Firing
            ###############################################

            #print("--------------------")

            precision = getPrecision(lastKnownDist, srvConf['botRadius'])

            #print("targetFound: " + str(targetFound))
            

            if not targetFound:

                #print("target not found, SCAN")
                
                # scan
                scanSliceWidth = (math.pi * 2) / scanSlices
                scanEnd = nbmath.normalizeAngle(scanStart + scanSliceWidth)

                scanReply = botSocket.sendRecvMessage({'type': 'scanRequest', 'startRadians': scanStart, 'endRadians': scanEnd})

                # if bot found in scan is different to the original bot found
                if scanReply['distance'] > lastKnownDist + 100:
                    diffTarget = True
                else:
                    diffTarget = False
                
                #print("+100: " + str(lastKnownDist + 100))
                #print("diffTarget: " + str(diffTarget))
                #print("targetLocked: " + str(targetLocked))
                #print("scanSlices: " + str(scanSlices))
                #print("targetLocked: ------------------------------------" + str(targetLocked))

                # remember last found distance, so a distance is known if a bot is not found on the last scan
                if scanReply['distance'] != 0 and not diffTarget:
                    lastKnownDist = scanReply['distance']

                # if a target was found in previous scan
                if targetLocked:
                    if scanReply['distance'] == 0 or diffTarget: # we lost target
                        #print("Target Lost *********************************************************")
                        # reset scan to look for next target
                        scanSlices = 1 if inCorner else 0.5 # cuz *= 2 at the end
                        resetScan = True
                        
                        # set scanStart angle

                        if cornerX == srvConf['botRadius']:
                            if cornerY == srvConf['botRadius']:
                                scanStart = 0

                            elif cornerY == a:
                                scanStart = 3 * math.pi / 2

                        elif cornerX == a:
                            if cornerY == 0:
                                scanStart = math.pi / 2

                            elif cornerY == a:
                                scanStart = math.pi

                        scanStart = nbmath.normalizeAngle(scanStart - math.pi / 4) # widen range, so bots can't hide near walls
                        lastKnownDist = 1500

                    targetLocked = False

                if ((2 * math.pi) / scanSlices) <= precision:
                    targetFound = True
            
            if targetFound:
                #print("target found, SHOOT")
                #print("scanStart: " + str(scanStart / math.pi) + "pi")
                #print("scanEnd: " + str(scanEnd / math.pi) + "pi")
                #print("resetScan: " + str(resetScan))

                # Shoot
                if not getCanonReply['shellInProgress']:
                    
                    if scanReply['distance'] != 0 and not diffTarget:
                        fireDirection = scanStart + scanSliceWidth / 2
                    else:
                        fireDirection = scanEnd + scanSliceWidth / 2
                    
                    fireDirection = nbmath.normalizeAngle(fireDirection)

                    #print("fireDirection: " + str(fireDirection / math.pi) + "pi")
                    dist = lastKnownDist if lastKnownDist > minDist else minDist

                    # fire down the center of this slice, or the skipped slice
                    botSocket.sendRecvMessage({'type': 'fireCanonRequest', 'direction': fireDirection, 'distance': dist})

                    # specify target has been found
                    targetLocked = True

                    # focus on area target was found for next scan
                    scanStart = nbmath.normalizeAngle(fireDirection - scanSliceWidth)
                    scanSlices = scanSlices / 4 # scanSlices * 4 # *= 2

                    # wait for shell to explode
                    mode = "wait"
                    targetFound = False
                

            # if scan did not find bot (or found a different, further bot), and scan was not just reset
            if (scanReply['distance'] == 0 or diffTarget) and not resetScan and not targetFound:
                scanStart = scanEnd
                        
            # scan done resetting
            resetScan = False

            # narrow area of search
            if not targetFound: scanSlices *= 2

        except nbipc.NetBotSocketException as e:
            # Consider this a warning here. It may simply be that a request returned
            # an Error reply because our health == 0 since we last checked. We can
            # continue until the next game starts.
            log(str(e), "WARNING")
            continue

##################################################################
# Standard stuff below.
##################################################################


def quit(signal=None, frame=None):
    global botSocket
    log(botSocket.getStats())
    log("Quiting", "INFO")
    exit()


def main():
    global botSocket  # This is global so quit() can print stats in botSocket
    global robotName

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-ip', metavar='My IP', dest='myIP', type=nbipc.argParseCheckIPFormat, nargs='?',
                        default='127.0.0.1', help='My IP Address')
    parser.add_argument('-p', metavar='My Port', dest='myPort', type=int, nargs='?',
                        default=20010, help='My port number')
    parser.add_argument('-sip', metavar='Server IP', dest='serverIP', type=nbipc.argParseCheckIPFormat, nargs='?',
                        default='127.0.0.1', help='Server IP Address')
    parser.add_argument('-sp', metavar='Server Port', dest='serverPort', type=int, nargs='?',
                        default=20000, help='Server port number')
    parser.add_argument('-debug', dest='debug', action='store_true',
                        default=False, help='Print DEBUG level log messages.')
    parser.add_argument('-verbose', dest='verbose', action='store_true',
                        default=False, help='Print VERBOSE level log messages. Note, -debug includes -verbose.')
    args = parser.parse_args()
    setLogLevel(args.debug, args.verbose)

    try:
        botSocket = nbipc.NetBotSocket(args.myIP, args.myPort, args.serverIP, args.serverPort)
        joinReply = botSocket.sendRecvMessage({'type': 'joinRequest', 'name': robotName}, retries=300, delay=1, delayMultiplier=1)
    except nbipc.NetBotSocketException as e:
        log("Is netbot server running at" + args.serverIP + ":" + str(args.serverPort) + "?")
        log(str(e), "FAILURE")
        quit()

    log("Join server was successful. We are ready to play!")

    # the server configuration tells us all about how big the arena is and other useful stuff.
    srvConf = joinReply['conf']
    log(str(srvConf), "VERBOSE")

    # Now we can play, but we may have to wait for a game to start.
    play(botSocket, srvConf)


if __name__ == "__main__":
    # execute only if run as a script
    signal.signal(signal.SIGINT, quit)
    main()