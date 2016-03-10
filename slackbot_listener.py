import calendar
import ConfigParser
import importlib
import json
import socket
import time
import unicodedata
from slackutil.my_slackclient import my_slackclient
from slackutil.slackbot_handler import slackbot_handler

if __name__ == '__main__' and __package__ is None:
    from os import sys, path
    sys.path.append(path.dirname(path.abspath(__file__)))

class slackbot_listener(object):

    def __init__(self, ini_file):
        self.config = ConfigParser.ConfigParser()       
        self.config.read(ini_file)

    def _get_lock(self):
        global lock_socket
        lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            lock_socket.bind('\0' + self.config.get('Configuration', 'daemon_name'))
        except socket.error:
            sys.exit()

    def run(self):
        self._get_lock()

        modules_location = self.config.get('Configuration', 'modules_location')
        handlers = []
        for handler_name in self.config.get('Configuration', 'handler_list').split():
            this_class = getattr(importlib.import_module(modules_location + '.' + handler_name), handler_name)
            handlers.append(this_class(self.config))

        slackclient = my_slackclient(self.config.get('Configuration', 'token'))

        myself = None
        json_data = json.loads(slackclient.api_call('auth.test'))
        if 'ok' in json_data and 'user_id' in json_data:
            myself = json_data['user_id']
        if myself:
            print "myself: " + myself
        else:
            print "error getting user_id of bot"

        keywords = self.config.get('Configuration', 'keywords').split()
        while True:
            time_now = calendar.timegm(time.gmtime())
            print "connecting at time " + str(time_now)
            if slackclient.rtm_connect():
                print "connected"
                while True:
                    data = slackclient.rtm_read()
                    if data:
                        for item in data:
                            channel = None
                            text = None
                            user = None
                            edited = False
                            if ('type' in item and item['type'] == 'message') and ('channel' in item):
                                channel = item['channel']
                                if ('subtype' in item and item['subtype'] == 'message_changed') and ('message' in item and 'text' in item['message'] and 'type' in item['message'] and item['message']['type'] == 'message' and 'user' in item['message']):
                                    text = item['message']['text']
                                    user = item['message']['user']
                                    edited = True
                                elif 'text' in item and 'user' in item:
                                    text = item['text']
                                    user = item['user']
                                if text:
                                    found = False if keywords else True
                                    for keyword in keywords:
                                        if text.startswith(keyword) or text.startswith(keyword + ' '):
                                            found = True
                                            break

                                    if found:
                                        user = slackclient.get_user(user)
                                    else:
                                        text = None

                            if channel and text and user:
                                text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore')
                                if int(float(item['ts'])) >= time_now:
                                    handled = False
                                    error = False
                                    tokens = text.split()
                                    for handler in handlers:
                                        if handler.can_handle(text, tokens, edited):
                                            slackclient.show_is_typing(channel)
                                            handled = True
                                            try:
                                                error = handler.handle(text, tokens, slackclient, channel, user)
                                            except Exception as e:
                                                error = True
                                            break
                                    if error:
                                        slackclient.post_message(channel, 'Sorry, I encountered an error handling your request!')
                    time.sleep(0.5)
            else:
                print 'connection failed, invalid token?'
                break
            print 'exited loop, sleeping 5 seconds'
            time.sleep(5)