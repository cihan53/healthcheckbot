#    Healthcheck Bot
#    Copyright (C) 2018 Dmitry Berezovsky
#
#    HealthcheckBot is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    HealthcheckBot is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import collections
import time
import json
import logging
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import asyncio
import concurrent.futures
executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

from healthcheckbot.common import validators
from healthcheckbot.common.error import ConfigValidationError
from healthcheckbot.common.model import (
    OutputModule,
    WatcherModule,
    WatcherResult,
    ParameterDef,
)


logger1 = logging.getLogger("App")

class CustomHttpHandler(logging.Handler):
    def __init__(self, url: str, token: str, silent: bool = True,ContentType = "application/json"):
        '''
        Initializes the custom http handler
        Parameters:
            url (str): The URL that the logs will be sent to
            token (str): The Authorization token being used
            silent (bool): If False the http response and logs will be sent 
                           to STDOUT for debug
        '''
        self.url = url
        self.token = token
        self.silent = silent
        self.ContentType = ContentType

        # sets up a session with the server
        self.MAX_POOLSIZE = 100
        self.session = session = requests.Session()
        session.headers.update({
            'Host': 'machinemonitor.io',
            'Content-Type': self.ContentType,
            'Authorization': 'Bearer %s' % (self.token)
        })
    
        self.session.mount('https://', HTTPAdapter(
            max_retries=Retry(
                total=5,
                backoff_factor=0.5,
                status_forcelist=[403, 500]
            ),
            pool_connections=self.MAX_POOLSIZE,
            pool_maxsize=self.MAX_POOLSIZE
        ))
        
        super().__init__()

    def emit(self, record):
        '''
        This function gets called when a log event gets emitted. It recieves a
        record, formats it and sends it to the url
        Parameters:
            record: a log record
        '''
        
        executor.submit(actual_emit, self, record)

def actual_emit(self, record):
    
    logEntry = self.format(record)
    response = self.session.post(self.url, data=logEntry)
 
    if not self.silent:
        print(logEntry)
        print(response.content)
      
 
class RestOutput(OutputModule):
    def __init__(self, application):
        super().__init__(application)
        self.rest_logger = None  # type: logging.Logger
        self.rest_host = None  # type: str
        self.rest_token = None  # type: str
        self.facility = "healthcheck"
        self.contentType = "application/json"
        self.silent = True
        self.extra_fields = {}

    def __flatten(self, dictionary, parent_key="", sep="__"):
        items = []
        for k, v in dictionary.items():
            new_key = parent_key + sep + k if parent_key else k
            if isinstance(v, collections.MutableMapping):
                items.extend(self.__flatten(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)

    def on_configured(self):
        self.rest_logger = logging.getLogger("Rest")
        self.rest_logger.setLevel(logging.DEBUG)
        self.rest_logger.propagate = False
        
        handler = CustomHttpHandler(
            url=self.rest_host,
            token=self.rest_token,
            silent=True,
            contentType="application/json"
        )

        handler.level = logging.DEBUG
        self.rest_logger.addHandler(handler)

       

    def output(self, watcher_instance: WatcherModule, watcher_result: WatcherResult):
        data = watcher_result.to_dict()
      
        data = self.__flatten(watcher_result.to_dict())
        data.update(dict(tags="healthcheck", watcher_name=watcher_instance.name))
        
 
            
        if len(watcher_result.extra.keys()) > 0 and "extra" in data:
            data.update(self.__flatten(watcher_result.extra))
            del data["extra"]
        data.update(self.extra_fields)
        self.rest_logger.info(
            "HealthcheckBot {}: Watcher {} - checks {}".format(
                self.get_application_manager().get_instance_settings().id,
                watcher_instance.name,
                "passed" if watcher_result.checks_passed else "failed",
            ),
            extra=data,
        )

    PARAMS = (
        ParameterDef("rest_host", is_required=True),
        ParameterDef("rest_token", is_required=True),
        ParameterDef("facility", validators=(validators.string,)),
        ParameterDef("silent", validators=(validators.boolean,)),
        ParameterDef("contentType", validators=(validators.string,)),
        ParameterDef("extra_fields", validators=(validators.dict_of_strings,)),
    )

