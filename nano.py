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

class HeaderDict(dict):
    def __setitem__(self, key, value):
        dict.__setitem__(self, key.title(), str(value))

    def setdefault(self, key, value):
        return dict.setdefault(self, key.title(), str(value))

class HttpError(Exception):
    def __init__(self, status, *args):
        Exception.__init__(self, format_status(status), *args)

class Http500(HttpError):
    def __init__(self, *args):
        HttpError.__init__(self, *((500,)+args))

class NanoApplication(object):
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
            start_response(format_status(404), [])
            return []

        response = None
        body = None
        status = format_status(200)
        headers = HeaderDict()

        try:
            try:
                response = callback(environ, **kwargs)
            except HttpError:
                raise
            except Exception, e:
                raise HttpError, HttpError('500 OH NOEZ', str(e)), sys.exc_info()[2]
        except HttpError, e:
            status = e.args[0]
            if app.debug:
                traceback.print_exc()
                body = traceback.format_exc()
            else:
                body = ''

        if response is not None:
            if isinstance(response, tuple) and len(response) == 3:
                status, body, headers = response
            elif isinstance(response, list) and len(response) == 1:
                body = response[0]
            else:
                body = response

        headers = HeaderDict(headers)

        if isinstance(body, (bytes, str)):
            headers.setdefault('Content-Length', len(body))
            headers.setdefault('Content-Type', 'text/plain')
        elif hasattr(body, 'read') and hasattr(body, 'name'):
            try:
                headers.setdefault('Content-Length', os.path.getsize(body.name))
                mime, _ = mimetypes.guess_type(body.name)
                if mime is not None:
                    headers.setdefault('Content-Type', mime)
            except TypeError:
                pass

        start_response(status, headers.items())
        return body

    def dispatch(self, environ):
        request_path = environ['PATH_INFO'] or '/'
        if 'QUERY_STRING' in environ:
            request_path += '?' + environ['QUERY_STRING']

        for route, callback in self.routes:
            match = route.match(request_path)
            if match is not None:
                return callback, match.groupdict()
        return None, None
