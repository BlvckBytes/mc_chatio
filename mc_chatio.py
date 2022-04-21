from threading import Thread
from termcolor import colored
from random import randrange
from keyboard import Keyboard

import sys
import subprocess
import time
import re
import os

# Constants
F_PATH = '/Applications/MultiMC.app/Data/instances/1.18.2/.minecraft/logs/latest.log'
S_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'contestants.txt')
RE_CHATMSG = r'^\[[^\]]+\] \[[^\]]+\]: \[CHAT\] (.*)$'
RE_PRIVMSG = r'\[Nachrichten\] +\[([^ ]+) -> Dir\] (.*)$'
TERM_APP = 'iterm2'
AMOUNT_PER_WINNER = 150000
KEYBOARD = Keyboard('de')

# Whether or not the log poller is active
poll_log_active = False

# List of usernames of all the contestants
contestants = []

'''
Save all contestants to the local file
'''
def save_contestants():
  with open(S_PATH, 'w') as f:
    for contestant in contestants:
      f.write(f'{contestant}\n')

'''
Load all contestants from the local file
'''
def load_contestants():
  global contestants

  # No save file existing yet
  if not os.path.exists(S_PATH):
    return

  with open(S_PATH, 'r') as f:
    for line in f.readlines():
      # Strip names
      name = line.strip()

      # Skip empty lines
      if name == '':
        continue
      
      # Load contestant
      contestants.append(name)

'''
Called with a new line of the log as soon as the new line
has been detected by the poller loop, using the following format:

[HH:MM:SS] [<Thread-Details>]: <LOG>

<LOG> itself starts with [CHAT] for chat messages
'''
def on_log(line):
  # Search for a match within the log line
  match = re.search(RE_CHATMSG, line)

  # No match found, line not of interest
  if match == None:
    return

  # Relay chat message
  on_chat(match.group(1))

'''
Chat handler, invoked with trimmed chat messages
'''
def on_chat(line):
  # Search for a match within the chat line
  match = re.search(RE_PRIVMSG, line)

  # No match found, line not of interest
  if match == None:
    return

  # Relay private message
  on_prv(match.group(1), match.group(2).strip())

'''
Private chat message handler, invoked with sender and trimmed message
'''
def on_prv(sender, message):
  if sender not in contestants:
    contestants.append(sender)
    save_contestants()
    print(colored('[ADDED]', 'green'), colored(f'{sender}', 'blue'), 'has been added to the list of contestants!')

'''
Log polling target function, used with Thread()

Opens the log file at F_PATH, seeks it's end and polls for
new lines that have been written to this file (1ms intervals)
'''
def poll_log_target():
  # Open the log file in read-only mode
  with open (F_PATH, 'r') as f:
    # Seek it's end (past content is not of interest)
    f.seek(0, 2)

    # Poll in a loop
    while poll_log_active:
      l = f.readline()

      # Nothing there, sleep for a millisecond and try again
      while (len(l)) == 0:
        
        # Poller has been terminated
        if not poll_log_active:
          return

        time.sleep(1 / 1000)
        l = f.readline()

      # New line available
      on_log(l.strip())

'''
Stop polling the log file
'''
def stop_log_poll():
  global poll_log_active
  poll_log_active = False

'''
Start polling the log file
'''
def start_log_poll():
  global poll_log_active
  poll_log_active = True
  Thread(target=poll_log_target).start()

'''
Print an info-styled message to the screen
'''
def print_info(msg):
  print(colored('[INFO]', 'yellow'), msg)

'''
Draw the next player and persistently remove the entry from the list
'''
def draw_player() -> str:
  # Pop off from the list and save persistently
  name = contestants.pop(randrange(len(contestants)))
  save_contestants()
  return name

'''
Start the draw-loop, which basically draws another player
on ENTER and quits on 'exit', while removing drawn players
from the list and keeping a count of draws per session
'''
def draw_loop():
  drawn_count = 0

  while 1:
    # Nothing to choose from anymore
    if len(contestants) == 0:
      print_info('No more contestants left')
      return

    # Prompt for the next action
    print_info('Hit ENTER to draw another player, type "exit" to quit')
    ui = input().strip()

    # Exit the draw-loop
    if ui.lower() == 'exit':
      print_info('Exiting the draw-loop')
      return

    # Draw another player
    winner = draw_player()
    drawn_count += 1

    # Log event
    print(colored('[DRAWN]', 'green'), colored(f'{winner}', 'blue'), 'has been drawn as', colored(f'winner #{drawn_count}', 'blue'))

    # Dispatch chat message and pay command
    dispatch_chat([
      f'&2[DRAWN] &9{winner} &7hat als &9#{drawn_count} &7gewonnen!',
      f'/pay {winner} {AMOUNT_PER_WINNER}'
    ])

'''
Using applescript, sets the focus + foreground on a window by its title in conjunction with it's parent process
If the title is none, all windows of that process will be looped, this only makes sense if just one window is available
@author Aurelien Scoubeau <aurelien.scoubeau@gmail.com>
'''
def focus_window(process, title):
  # find the app or window back and activate it
  apple = """
  set the_title to "%s"
  set the_process to "%s"
  tell application "System Events"
      repeat with p in every process whose background only is false
          if (name of p) is the_process then
              repeat with w in every window of p
                  if (name of w) is the_title then
                      tell p
                          set frontmost to true
                          perform action "AXRaise" of w
                      end tell
                  end if
              end repeat
          end if
      end repeat
  end tell
  """ % (title, process)

  if title == None:
    apple = """
    set the_process to "%s"
    tell application "System Events"
        repeat with p in every process whose background only is false
            if (name of p) is the_process then
                repeat with w in every window of p
                    tell p
                        set frontmost to true
                        perform action "AXRaise" of w
                    end tell
                end repeat
            end if
        end repeat
    end tell
    """ % (process)

  p = subprocess.Popen(
    'osascript',
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT
  )

  p.communicate(apple.encode('utf8'))[0]

'''
Using AppleScript, lists the title of every window.
Returns a list of [APP_NAME, WINDOW_NAME] tuples, where hint is contained in WINDOW_NAME
@author Aurelien Scoubeau <aurelien.scoubeau@gmail.com>
'''
def find_windows(hint):
  possibilities = []
  # app name + window title farming
  # it allows listing windows by just typing the app name
  apple = """
  set window_titles to {}
  tell application "System Events"
      repeat with p in every process whose background only is false
          repeat with w in every window of p
              set end of window_titles to (name of p) & "|>" & (name of w)
          end repeat
      end repeat
  end tell
  set AppleScript's text item delimiters to "\n"
  window_titles as text
  """

  p = subprocess.Popen(
    'osascript',
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT
  )

  # Parse windows from output, one window per line
  # Format: APP_NAME|>WINDOW_NAME
  windows = p.communicate(apple.encode('utf8'))[0].decode('utf8').split('\n')

  return list(
    # Filter out items that are not of interest
    filter(
      lambda x: len(x) == 2 and (
        # Hint is in the process name
        hint.lower() in x[0].lower() or
        # Hint is in the window name
        hint.lower() in x[1].lower()
      ),
      # Split on the name/window delimiter
      map(lambda c: c.split('|>'), windows)
    )
  )

'''
Dispatch chat messages (or commands with a leading slash)
'''
def dispatch_chat(msgs):
  # Always receive lists
  if not isinstance(msgs, list):
    msgs = [msgs]

  # Go to the minecraft window
  focus_minecraft()
  time.sleep(1 / 10)

  # Remove escape overlay
  KEYBOARD.key_press('esc')

  # Open the chat
  KEYBOARD.key_press('t')

  # Loop over all messages
  for cmd in msgs:
    # Write the message
    KEYBOARD.write(cmd)

    # Send the message
    KEYBOARD.key_press('enter')
    time.sleep(1 / 10)

  # Re-activate escape overlay
  KEYBOARD.key_press('esc')

  # Go back to the terminal
  time.sleep(1 / 10)
  focus_terminal()

'''
Focus back on the terminal window
'''
def focus_terminal():
  focus_window(TERM_APP, None)

focus_minecraft_res = None

'''
Focus the minecraft window
'''
def focus_minecraft():
  # Cache the window result for faster access
  global focus_minecraft_res
  if focus_minecraft_res == None:
    focus_minecraft_res = find_windows('minecraft')

  # Minecraft doesn't seem to be open
  if (len(focus_minecraft_res) == 0):
    print_info('Could not locate an open Minecraft window')
    sys.exit()
    return

  # Extract the window's name from the tuple
  [proc_name, win_name] = focus_minecraft_res[0]
  focus_window(proc_name, win_name)

'''
Main entry-point of this program
'''
def main():
  print_info('Chat utility started')

  # Load known contestants (in case of a crash)
  load_contestants()
  print_info(f'Loaded {len(contestants)} contestants from the save-file')

  # Start polling
  start_log_poll()
  print_info('Now polling latest.log and listening for private messages')
  print_info('Hit ENTER to stop and go into drawing mode')

  # End polling on ENTER
  input()
  stop_log_poll()
  print_info('Stopped polling')

  # Start drawing players
  print_info('Starting draw-loop')
  draw_loop()
  print_info('Done, goodbye')

if __name__ == '__main__':
  main()