# Overview #

TODO

# Terms #

* Day: a day in a Pennant Chase season, not a real calendar day unless
  explicitly specified.
* Season, Year: the number of a Pennant Chase season.

# Design #

TODO: Lots missing here.

  * Firestore database.

## Updates ##
The update process uses Google Cloud Functions, driven by triggers.

  1. new-games-to-db scrapes pennantchase.com. It adds game documents
     holding metadata for recent games to a Firestore database, keyed
     by the pennantchase game id.
  2. store-in-gcs is triggered when game documents are added to
     Firestore. It copies the box score from Pennant Chase to Google
     Cloud Storage.
  3. process-box-score is triggered when objects are added to Google
     Cloud Storage. It looks for interesting events like no-hitters,
     and posts a message to the league chat box for each game with
     interesting events.

## Avoiding duplicate chat notifications ##

### Summary ###

Before writing a message to the chat, process-box-score
retrieves the chat log and searches for the message, and only posts to
the chat if it is not present.

To differentiate the same event occurring on different days, the
message includes the day number, and has (year modulo 5) trailing NBSP
characters. This is a choice of aesthetics over perfection: for a
human reader, the year in the message when it is clear from context is
just clutter. In leagues with doubleheaders, and if the chat history
extends back more than 5 seasons, messages could be incorrectly
suppressed. A nicer solution for avoid suppressing identical events
from games in different seasons would be to only read N real days of
chat history when checking for a prior copy of the message.

### Details ###

Since Cloud Pub/Sub provides "at least once" delivery,
process-box-score might run twice for the same game, resulting in
duplicate chat messages. This could happen as a result of duplicate
Pub/Sub messages for either the Firestore document creation events or
the Cloud Storage object creation events.

As stated above, to make it less likely that this results in spurious
duplicates, the code retrieves the chat log and searches for the
message, and only posts to the chat if it is not present.

This implementation is subject to a race condition. Duplicate messages
can result in two instances of process-box-score processing the same
box score running simultaneously, and both could observe that the
message is not in the league chat, and therefore both would post chat
message.

A future improvement would be to use locking with timeouts, along the
following lines. Given the low likelihood of the race condition and
the low cost of a duplicate chat post (it isn't like accidentally
dispensing $100 from an ATM twice intead of once), this would be
overkill, though still potentially fun.

  1. Add two fields in the Firestore document, chat\_lock and
     chat\_success.
  2. Modfiy the 'write\_chat\_message' method to:
     1. Transactionally check chat\_success and obtain the lock. Do
        nothing if chat\_success is true or the lock cannot be
        obtained.
     2. Check whether the chat was already posted, and if not post the
        chat message.
     3. Set chat\_success.
  3. To handle crashes after obtaining the lock but before posting,
     the "obtain the lock" step steals the lock if it is older than
     the maximum execution time of the Cloud Function.
  4. Crashes after posting the chat message but before setting
     chat\_success are handled by the check for the message already
     being in the chat.

## Reconciliation (unimplemented) ##

### Overview ###

Under perfect conditions updates will be never be dropped, but in
practice scripts may be buggy or crash without completion, resulting
in data not be written to Cloud Storage and messages not being written to the
chat.

To handle this the system periodically checks that the documents in
Firestore and the objects in Cloud Storage include all the games in
Pennant Chase, and whether all of those games have been successfully
processed. The checks are (more or less) hop-by-hop, not literally
end-to-end: all the games in Pennant Chase should be in Firestore; all
the games in Firestore should be in Cloud Storage; all the games in
Cloud Storage should be have been successfull processed.

If started mid-season this design will, I think, result in a complete
backfill, including posting to the league chat. Let's assume that's
desirable.

### Open questions ###

What if a reconciliation error persists, i.e. how do we raise an
exception if no matter how hard we try the numbers don't add up?

How far back do we look, and is it in terms of real time or in Pennant
Chase time? Seems like it should be in terms of real time, but with
some minimum (2 Pennant Chase days?)

### Pennant Chase ###

Reconciliation maintains some Firestore collections.

#### game\_count ####

game\_count contains a document for each day reflecting the number of
games played according to the Pennant Chase scoreboard.

* season
* day
* number of games
* timestamp when the number of games was observed
* latest day simulated when the number of games was observed. note
  that this day might have been in progress when the observation was
  made, i.e. the number of games might be too low.
* complete: this is set to the timestamp when the system became
  confident that the number of games will not change.
  
'complete' for day N can be set when either there are results for day
N+1, or when sufficient real time has elapsed since the observation
was made (the second case is necessary only for the last day of the
season).

A future optimization might be to use the Pennant Chase schedule page
to determine the game counts. Using the schedule page alone isn't
sufficient because it only shows future games, not past games. The
system needs to work even if it is first used in the middle of a
season.

### Firestore ###

For each day that is in scope, i.e. recent complete\_timestamp or
recent day, compare the count of games in game\_count and in mydb. Add
any missing games to mydb. Raise an exception if the counts still do
not match.

### Cloud Storage ###

For each day that is in scope, check that every game in mydb has
corresponding objects in Cloud Storage.

Re-scrape and upload any missing objects (with retry and
backoff). Raise an exception on failure if the day is close to falling
out of the reconciliation window.

### Chat Messages ###

The "invariant" reconciliation restores is for every game in Pennant
Chase for the last N days, there was a successful run of process-box-score.

After process-box-score succeeds, it populates a
'process\_box\_score\_success' field in the Firestore document for the
game containing the the current time in epoch seconds.

For each day that is in scope, check for rows in mydb missing
process\_box\_score\_success. Re-run process-box-score. Raise an
exception if process\_box\_score\_success is still unset if the day is
close to falling out of the reconciliation window.

Note

  * We don't use the presence of the message in the chat as a signal,
    because we would get false positives if we change the format of
    the message.
	
### Alternative ###

An alternative approach would be to deploy the trigger functions with
[retries](https://cloud.google.com/functions/docs/bestpractices/retries
"Retrying Event-Driven Functions") enabled, but that could result in
many undesirable retries in some scenarios: for example, if the cause
of the failure was a bug in our code, or an extended Pennant Chase
outage for the functions that interact with pennantchase.com.

# Testing #

No tests yet.

Thoughts:

  * Start with end-to-end tests to the extent possible.
  * Use them to drive continuous deployment via [Cloud Build](https://cloud.google.com/functions/docs/testing/test-cicd "Cloud Functions CI/CD").

# Unplanned work #

  * Separate process-box-score from post-chat-message, with Pub/Sub in between.

# Assumptions #
  * Pennant Chase game ids are unique.
  * Pennant Chase score and schedule pages could be incomplete when a
    day is in the middle of being simulated, but are complete for all
    other days.

# Limitations and quirks #

## Doubleheaders ##

Identical events that occur in two games in a doubleheader,
tripleheader, etc. will be incorrectly deduplicated.
tripleheaders, etc.). (E.g. if a player hits for the cycle in both
games of a doubleheader, only one message will be sent to the
chat.)

* A simple and robust fix would be to include the game id in the
  message, but that would be very ugly.
* A poor solution would be to append (hash(game\_id) mod N) NBSP
  characters to the message. The problem with this is that to a
  human audience it would appear to just be a repeated message,
  not two different events.
* A nice but complicated solution would be to include the game
  number in the message. For example, "Something happened [day
  17]" and "Something happenend [day 17, game 2]".
  * Setting the game number for a new game could consist of
	transactionally counting the number of existing games with the
	same (year, day, home, away) -- call that n -- and writing the
	new game to Firestore with game number = n+1. There might be a
	better way -- or at least optimizations such as checking the
	schedule ahead of time for future doubleheaders. Also I don't
	know whether Firestore allows arbitrary queries within
	transactions, though the
	[documentation](https://firebase.google.com/docs/firestore/transaction-data-contention
	"Transaction serializability and isolation") doesn't say that
	they don't.
	
## Format changes ##

Changing the format of the chat message could lead to duplicate chat
posts. The race condition is: 

* post-chat-message writes the message with format version N, and
  crashes before recording success in the database.
* post-chat-message is updated to use new format.
* the reconciliation system runs and post-chat-message writing the
  message with format version N+1.
  
A simple, ugly, and robust solution would be to include a unique
message id in the message.

A complicated, less robust, and less ugly solution would be to give
each message a sequence number, and append (sequence number mod N)
NBSP characters to the chat message. This would work as long as:

* There are never more than N events in the portion of the chat
  post-chat-message chat scans when checking whether the message has
  already been posted.
* The only posts with trailing NBSP characters are the ones written by
  this system.
