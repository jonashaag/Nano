"""
Nano -- Web Framework in less than 100 LOC

Copyright 2010, Jonas Haag <jonas@lophus.org>
License: 2-clause BSD
"""
import os
import sys
import re
import mimetypes
import traceback

HTTP_REASONS = {200: 'Here You Go', 404: 'Go Away', 500: 'OH NOEZ'}

def format_status(status):
    if not isinstance(status, str):
        status = '%d %s' % (status, HTTP_REASONS.get(status, '<reason>'))
    return status

def isetdefault(dct, key, value):
    dct.setdefault(key.title(), str(value))

class HttpError(Exception):
    def __init__(self, status, *args):
        Exception.__init__(self, status, *args)

class NanoApplication(object):
    charset = 'utf-8'

    def __init__(self, debug=False):
        self.routes = []
        self.debug = debug

    def route(self, pattern):
        pattern = re.sub(':([a-z0-9_]+):', '(?P<\g<1>>[^/]+)', pattern)
        pattern = re.compile('^%s$' % pattern)
        def decorator(callback):
            self.routes.append((pattern, callback))
            return callback
        return decorator

    def __call__(self, environ, start_response):
        callback, kwargs = self.dispatch(environ)

        if callback is None:
            start_response(format_status(404), [('Content-Length', 0)])
            return []

        try:
            try:
                retval = callback(environ, **kwargs)
            except Exception, e:
                if isinstance(e, HttpError):
                    raise
                raise HttpError, HttpError(500, sys.exc_info())
        except HttpError, e:
            status = e.args[0]
            headers = {}
            exc_info = e.args[1] if len(e.args) > 1 else sys.exc_info()
            body = traceback.format_exception(*exc_info) if self.debug else ''
            traceback.print_exception(*exc_info)
        else:
            if isinstance(retval, tuple) and len(retval) == 3:
                status, headers, body = retval
                headers = dict(headers)
            else:
                status, headers, body = 200, {}, retval

        if isinstance(body, (list, tuple)):
            if not body:
                body = ''
            else:
                assert isinstance(body[0], (bytes, unicode))
                body = body[0][0:0].join(body)

        if isinstance(body, (bytes, unicode)):
            if isinstance(body, unicode):
                body = body.encode(self.charset)
            isetdefault(headers, 'Content-Length', len(body))
            isetdefault(headers, 'Content-Type', 'text/plain')
            body = [body] if body else []
        elif isinstance(body, file):
            isetdefault(headers, 'Content-Length', os.path.getsize(body.name))
            mime, _ = mimetypes.guess_type(body.name)
            if mime is not None:
                isetdefault(headers, 'Content-Type', mime)

        if isinstance(status, int):
            status = format_status(status)
        start_response(status, headers.items())
        return body

    def dispatch(self, environ):
        request_path = environ['PATH_INFO'] or '/'
        for route, callback in self.routes:
            match = route.match(request_path)
            if match is not None:
                return callback, match.groupdict()
        return None, None
