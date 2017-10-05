import time
import threading
from matrix_bot_api.mcommand_handler import MCommandHandler
from matrix_bot_api.mregex_handler import MRegexHandler

HELP_DESC = ("!votekick <user> [<reason>]\t"
             "-\tStart a vote to kick the specified user")
VOTE_TIME = 15              # Amount seconds a vote takes
VOTE_IN_PROGRESS = False    # Mutex to prevent multiple parallel votes
VOTE_COUNT = 0              # Amount of unique vote participants
VOTE_BALANCE = 0            # Sum of votes (+1/-1)
KICK_MIN_COUNT = 4          # Minimum amount of votes required for votekick eval
VOTER_LIST = []             # UserIDs that already voted in the current vote

def register_to(bot):

    # acquire the reason argument and return as string
    def get_reason(room, event):
        args = event['content']['body'].split()
        if (len(args) > 2):
            args.pop(0)
            args.pop(0)
            return ' '.join(args)
        else:
            return None

    # acquire the target user and check if he is present in the room
    def get_target_user(room, event):
        # check if the specified user exists
        args = event['content']['body'].split()

        try:
            target_user = args[1]
        except IndexError:
            room.send_text("Incorrect votekick syntax. Aborting.")
            return None

        room_users = room.get_joined_members()

        for u in room_users:
            if (room_users[u]['displayname'] == target_user
                or u == target_user):
                return u

        room.send_text("No matching user \'{}\' ".format(target_user) +
                       "has been found. Aborting")
        return None

    # executed by a new thread. Wait for the vote to end and print results
    def vote_wait(room, event, user, reason):
        global VOTE_TIME
        global VOTE_IN_PROGRESS
        global VOTE_COUNT
        global VOTE_BALANCE
        global KICK_MIN_COUNT

        time.sleep(VOTE_TIME)

        # evaluate results
        message = "Time is up. {} people voted".format(VOTE_COUNT)

        # check if enough people voted
        if (VOTE_COUNT < KICK_MIN_COUNT):
            message += ", this is not enough to evaluate the result.\n"
            message += "Votekick aborted."
        else:
            message += ". Vote balance for kicking {}: ".format(user)
            message += str(VOTE_BALANCE) + '.\n'

            # check the vote balance
            if (VOTE_BALANCE <= 0):
                message += user + " will not be kicked."
            else:
                message += "Kicking {}.".format(user)

                if (not room.kick_user(user,reason)):
                    print("Kicking failed, not enough power.")

        room.send_text(message)

        # reset vars
        VOTE_COUNT = 0
        VOTE_BALANCE = 0
        VOTER_LIST = []
        VOTE_IN_PROGRESS = False

    # executed upon !votekick command
    def kick_callback(room, event):
        global VOTE_TIME
        global VOTE_IN_PROGRESS
        global VOTE_COUNT
        global VOTE_BALANCE
        global KICK_MIN_COUNT

        if (VOTE_IN_PROGRESS):
            room.send_text("There's already a vote in progress. Aborting")
            return

        VOTE_IN_PROGRESS = True
        VOTE_COUNT = 0
        VOTE_BALANCE = 0
        VOTER_LIST = []

        user = get_target_user(room, event)

        if (user == None):
            VOTE_IN_PROGRESS = False
            return

        reason = get_reason(room, event)
        message = "Starting a votekick for \'{}\'. ".format(user)

        if (reason == None):
            reason = "Votekick"
        else:
            message += "Reason: {}.\n".format(reason)

        message += "The vote will run for {} seconds. ".format(VOTE_TIME)
        message += "A minimum of {} votes ".format(KICK_MIN_COUNT)
        message += "is required to evaluate the results. "
        message += "Vote with \'+1\' or \'-1\'."
        room.send_text(message)

        # start a timer thread to wait for the vote to end
        t = threading.Thread(target=vote_wait, args = (room,event,user,reason))
        t.start()

    # called upon +1/-1 commands
    def vote_callback(room, event):
        global VOTE_IN_PROGRESS
        global VOTE_COUNT
        global VOTE_BALANCE
        global VOTER_LIST

        if (not VOTE_IN_PROGRESS):
            return

        # check if the current voter already voted
        if (event['sender'] in VOTER_LIST):
            return
        else:
            VOTER_LIST.append(event['sender'])

        vote = event['content']['body']
        VOTE_COUNT += 1
        VOTE_BALANCE += int(vote)

    kick_handler = MCommandHandler("votekick", kick_callback)
    bot.add_handler(kick_handler)
    vote_handler = MRegexHandler("^(\+|-)1$", vote_callback)
    bot.add_handler(vote_handler)
