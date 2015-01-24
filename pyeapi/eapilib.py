#
# Copyright (c) 2014, Arista Networks, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#   Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
#
#   Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in the
#   documentation and/or other materials provided with the distribution.
#
#   Neither the name of Arista Networks nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL ARISTA NETWORKS
# BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
# BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN
# IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
"""Provides wrapper for eAPI calls

This module provides a connection to eAPI by wrapping eAPI calls in an
instance of Connection.  The connection module provides an easy implementation
for sending and receiving calls over eAPI using a HTTP/S transport.
"""

import json
import socket
import base64

from httplib import HTTPConnection, HTTPSConnection

from pyeapi.utils import debug

DEFAULT_HTTP_PORT = 80
DEFAULT_HTTPS_PORT = 443
DEFAULT_HTTP_LOCAL_PORT = 8080
DEFAULT_HTTP_PATH = '/command-api'
DEFAULT_UNIX_SOCKET = '/var/run/command-api.sock'

class EapiError(Exception):
    """Base exception class for all exceptions generated by eapilib

    This is the bsae exception class for all exceptiions generated by
    eapilib.  It is provided as a catch all for exceptions and should
    not be directly raised by an methods or functions

    Args:
        commands (array): The list of commands there were sent to the
            node that when the exception was raised
        message (string): The exception error message
    """
    def __init__(self, message, commands=None):
        self.message = message
        self.commands = commands
        super(EapiError, self).__init__(message)

class CommandError(EapiError):
    """Base exception raised for command errors

    The CommandError instance provides a custom exception that can be used
    if the eAPI command(s) fail.  It provides some additional information
    that can be used to understand what caused the exception.

    Args:
        error_code (int): The error code returned from the eAPI call.
        error_text (string): The error text message that coincides with the
            error_code
        commands (array): The list of commands that were sent to the node
            that generated the error
        message (string): The exception error message which is a concatentation
            of the error_code and error_text
    """
    def __init__(self, code, message, commands=None):
        self.error_code = code
        self.error_text = message
        self.commands = commands
        self.message = 'Error [{}]: {}'.format(code, message)
        super(CommandError, self).__init__(message)

class ConnectionError(EapiError):
    """Base exception rasied for connection errors

    Connection errors are raised when a connection object is unable to
    connect to the node.  Typically these errors can result from using
    the wrong transport type or not providing valid credentials.

    Args:
        commands (array): The list of commands there were sent to the
            node that when the exception was raised
        connection_type (string): The string identifer for the connection
            object that generate the error
        message (string): The exception error message
        response (string): The message generate from the response packet

    """
    def __init__(self, connection_type, message, commands=None):
        self.message = message
        self.connection_type = connection_type
        self.commands = commands
        super(ConnectionError, self).__init__(message)



class SocketConnection(HTTPConnection):

    def __init__(self, path):
        HTTPConnection.__init__(self, 'localhost')
        self.path = path

    def __str__(self):
        return 'unix:%s' % self.path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.path)

class HttpConnection(HTTPConnection):

    def __init__(self, path, *args, **kwargs):
        HTTPConnection.__init__(self, *args, **kwargs)
        self.path = path

    def __str__(self):
        return 'http://%s:%s/%s' % (self.host, self.port, self.path)

class HttpsConnection(HTTPSConnection):

    def __init__(self, path, *args, **kwargs):
        HTTPSConnection.__init__(self, *args, **kwargs)
        self.path = path

    def __str__(self):
        return 'https://%s:%s/command-api' % (self.host, self.port)

class EapiConnection(object):
    """Creates a connection to eAPI for sending and receiving eAPI requests

    The EapiConnection object provides an implementation for sending and
    receiving eAPI requests and responses.  This class should not need to
    be instantiated directly.
    """

    def __init__(self):
        self.transport = None
        self.error = None
        self._auth = None

    def __str__(self):
        return 'EapiConnection(transport=%s)' % self.transport

    def authentication(self, username, password):
        """Configures the user authentication for eAPI

        This method configures the username and password combination to use
        for authenticating to eAPI.

        Args:
            username (str): The username to use to authenticate the eAPI
                connection with
            password (str): The password in clear text to use to authenticate
                the eAPI connection with

        """
        _auth = base64.encodestring('{}:{}'.format(username, password))
        self._auth = str(_auth).replace('\n', '')

    def request(self, commands, encoding=None, reqid=None):
        """Generates an eAPI request object

        This method will take a list of EOS commands and generate a valid
        eAPI request object form them.  The eAPI request object is then
        JSON encoding and returned to the caller.

        eAPI Request Object

        .. code-block:: json

            {
                "jsonrpc": "2.0",
                "method": "runCmds",
                "params": {
                    "version": 1,
                    "cmds": [
                        <commands>
                    ],
                    "format": [json, text],
                }
                "id": <reqid>
            }

        Args:
            commands (list): A list of commands to include in the eAPI
                request object
            encoding (string): The encoding method passed as the `format`
                parameter in the eAPI request
            reqid (string): A custom value to assign to the request ID
                field.  This value is automatically generated if not passed

        Returns:
            A JSON encoding request struture that can be send over eAPI

        """

        reqid = id(self) if reqid is None else reqid
        params = {"version": 1, "cmds": commands, "format": encoding}
        return json.dumps({"jsonrpc": "2.0", "method": "runCmds",
                           "params": params, "id": str(reqid)})

    def send(self, data):
        """Sends the eAPI request to the destination node

        This method is responsible for sending an eAPI request to the
        destination node and returning a response based on the eAPI response
        object.  eAPI responds to request messages with either a success
        message or failure message.

        eAPI Response - success

        .. code-block:: json

            {
                "jsonrpc": "2.0",
                "result": [
                    {},
                    {}
                    {
                        "warnings": [
                            <message>
                        ]
                    },
                ],
                "id": <reqid>
            }

        eAPI Response - failure

        .. code-block:: json

            {
                "jsonrpc": "2.0",
                "error": {
                    "code": <int>,
                    "message": <string>
                    "data": [
                        {},
                        {},
                        {
                            "errors": [
                                <message>
                            ]
                        }
                    ]
                }
                "id": <reqid>
            }

        Args:
            data (string): The data to be included in the body of the eAPI
                request object

        Returns:
            A decoded response.  The response object is deserialized from
                JSON and returned as a standard Python dictionary object

        Raises:
            CommandError if an eAPI failure response object is returned from
                the node.   The CommandError exception includes the error
                code and error message from the eAPI response.
        """
        try:
            debug('eapi_request: %s' % data)

            self.transport.putrequest('POST', '/command-api')

            self.transport.putheader('Content-type', 'application/json-rpc')
            self.transport.putheader('Content-length', '%d' % len(data))

            if self._auth:
                self.transport.putheader('Authorization',
                                         'Basic %s' % (self._auth))

            self.transport.endheaders()
            self.transport.send(data)

            response = self.transport.getresponse().read()
            decoded = json.loads(response)
            debug('eapi_response: %s' % decoded)

            if 'error' in decoded:
                _message = decoded['error']['message']
                _code = decoded['error']['code']
                raise CommandError(_code, _message)

            return decoded

        except (socket.error, ValueError) as exc:
            self.error = exc
            raise ConnectionError(str(self), 'unable to connect to eAPI')

        finally:
            self.transport.close()


    def execute(self, commands, encoding='json', **kwargs):
        """Executes the list of commands on the destination node

        This method takes a list of commands and sends them to the
        destination node, returning the results.  The execute method handles
        putting the destination node in enable mode and will pass the
        enable password, if required.

        Args:
            commands (list): A list of commands to execute on the remote node
            encoding (string): The encoding to send along with the request
                message to the destination node.  Valid values include 'json'
                or 'text'.  This argument will influence the response object
                encoding
            **kwargs: Arbitrary keyword arguments

        Returns:
            A decoded response message as a native Python dictionary object
            that has been deserialized from JSON.

        Raises:
            CommandError:  A CommandError is raised that includes the error
                code, error message along wit the list of commands that were
                sent to the node.  The exception instance is also stored in
                the error property and is availble until the next request is
                sent
        """
        if encoding not in ['json', 'text']:
            raise TypeError('encoding must be one of [json, text]')

        try:
            self.error = None
            request = self.request(commands, encoding=encoding, **kwargs)
            response = self.send(request)
            return response

        except ConnectionError as exc:
            exc.commands = commands
            self.error = exc
            raise

        except CommandError as exc:
            exc.commands = commands
            self.error = exc
            raise

class SocketEapiConnection(EapiConnection):
    def __init__(self, path=None, **kwargs):
        super(SocketEapiConnection, self).__init__()
        path = path or DEFAULT_UNIX_SOCKET
        self.transport = SocketConnection(path)

class HttpLocalEapiConnection(EapiConnection):
    def __init__(self, port=None, path=None, **kwargs):
        super(HttpLocalEapiConnection, self).__init__()
        port = port or DEFAULT_HTTP_LOCAL_PORT
        path = path or DEFAULT_HTTP_PATH
        self.transport = HttpConnection(path, 'localhost', port)

class HttpEapiConnection(EapiConnection):
    def __init__(self, host, port=None, path=None, username=None,
                 password=None, **kwargs):
        super(HttpEapiConnection, self).__init__()
        port = port or DEFAULT_HTTP_PORT
        path = path or DEFAULT_HTTP_PATH
        self.transport = HttpConnection(path, host, port)
        self.authentication(username, password)

class HttpsEapiConnection(EapiConnection):
    def __init__(self, host, port=None, path=None, username=None,
                 password=None, **kwargs):
        super(HttpsEapiConnection, self).__init__()
        port = port or DEFAULT_HTTPS_PORT
        path = path or DEFAULT_HTTP_PATH
        self.transport = HttpsConnection(path, host, port)
        self.authentication(username, password)



