"""
Nano -- Web Framework in less than 100 LOC

Copyright 2010, Jonas Haag <jonas@lophus.org>
License: 2-clause BSD
"""
import os
import sys
import re
import traceback
import mimetypes
import httplib

def format_status(status):
    if isinstance(status, int):
        status = '%d %s' % (status, httplib.responses.get(status, '<reason>'))
    return status

def isetdefault(dct, key, value):
    dct.setdefault(key.title(), str(value))

class HttpError(Exception):
    """
    Exception to immediately jump out of any view and respond with the status
    code passed as argument.

    If the status code is `500` and debug mode is
    turned on in the Nano application, the exception traceback will be printed.
    The full traceback will be sent to the browser if debug mode is turned on
    (independent of the status code).

    Parameters:
        `status`
            The HTTP status code to respond with. Either a number or a
            `code reason` string, e.g. `404` or `404 Not Found`.
        `exc_info` (optional)
            A triple `(exc_type, exc_value, exc_traceback)` (as returned from
            :func:`sys.exc_info`).
        `body` (optional)
            The body to be sent to the client.

    Example::

        @app.route('/download/:name:/')
        def download(name):
            if not os.path.exists(name):
                raise HttpError(404, 'File Not Found')
            return open(name)
    """
    def __init__(self, status, body=None, exc_info=None):
        Exception.__init__(self, status)
        self.status = status
        self.body = body
        self.exc_info = exc_info

    def get_exc_info(self):
        return self.exc_info or sys.exc_info()

    def get_body(self, full_traceback):
        if self.body is not None:
            return self.body
        if full_traceback:
            assert self.get_exc_info() != (None, None, None)
            return traceback.format_exception(*self.get_exc_info())
        return ''

class NanoApplication(object):
    """
    Central Nano object that functions as WSGI application passed to the WSGI
    server, e.g.::

        import bjoern
        import nano

        app = nano.NanoApplication()
        # ... loads of code ...

        if __name__ == '__main__':
            bjoern.run(app, '127.0.0.1', 8080)

    Parameters:
        `debug`
            If a Python exception gets raised in your code, this flag decides
            whether a full traceback shall be shown in the browser
        `charset`
            Sets the charset used to encode unicode strings returned by a view
        `chunksize`
            When using the built-in file wrapper, sets how much data should be
            read and sent per iteration.
        `default_content_type`
            Sets what should be used as default `Content-Type` HTTP header
    """
    def __init__(self, debug=False, charset='utf-8', chunksize=8*1024,
                       default_content_type='text/plain'):
        self.routes = []
        self.debug = debug
        self.charset = charset
        self.chunksize = chunksize
        self.default_content_type = default_content_type

    def route(self, pattern):
        """
        Decorator to map a URL pattern to a view function.

        The pattern is interpreted as regular expression; named group matches
        will be passed to the view function as keyword arguments.

        ``:foo:`` may be used as shortcut to ``(?P<foo>[^/]+)``, i.e. a named
        wildcard matching any characters except a slash.

        Keep in mind that arguments passed to the decorated view function are
        *always strings*, i.e. *no type conversions* are done at any time.

        Example::

            @app.route('/post/:slug:/')
            def view_page(environ, slug):
                return get_post_by_slug(slug)
        """
        pattern = re.sub(':([a-z0-9_]+):', '(?P<\g<1>>[^/]+)', pattern)
        pattern = re.compile('^%s$' % pattern)
        def decorator(callback):
            self.routes.append((pattern, callback))
            return callback
        return decorator

    def build_url(self, callback_name, **wildcards):
        """
        The routing counterpart: Returns a URL matching a pattern using the
        wildcards substitutions passed as keyword arguments.

        `callback_name` is the name of the route target whose route should be
        used to generate the URL. Substitution values must be strings. Example::

            @app.route('/:foo:/:bar:/')
            def foobar(foo, bar):
                ...

            app.build_url('foobar', foo='hello', bar='world')

        The following assumptions are made about your routing configuration:

        1. Routes contain nothing but Nano-style wildcards (``:foo:``) and
           named regular expression groups (``(?P<name>pattern)``).
        2. Route targets must be function-like, more precisely, they must have a
          ``__name__`` attribute that is unique within all route targets.

        :raises ValueError:
            If the given wildcard substitutions didn't match the route pattern's
            wildcards, i.e. too few, too many or invalid substitutions were passed
        """
        for pattern, callback in self.routes:
            if callback.__name__ != callback_name:
                continue
            url = pattern.pattern[1:-1]
            for name, value in wildcards.items():
                if not isinstance(value, basestring):
                    raise TypeError("Wildcard values must be strings")
                url, nsubs = re.subn('\(\?P<%s>.*?\)' % name, value, url)
                if nsubs:
                    del wildcards[name]
            if wildcards or not pattern.match(url):
                raise ValueError("Wildcard substitutions didn't match pattern")
            return url

    def __call__(self, environ, start_response):
        callback, kwargs = self.dispatch(environ)

        if callback is None:
            # No route matched the requested URL. HTTP 404.
            start_response(format_status(404), [('Content-Length', '0')])
            return []

        try:
            try:
                retval = callback(environ, **kwargs)
            except Exception, e:
                if isinstance(e, HttpError):
                    raise
                raise HttpError, HttpError(500, exc_info=sys.exc_info())
        except HttpError, http_err:
            status = http_err.status
            headers = {}
            body = http_err.get_body(self.debug)
            if status == 500:
                traceback.print_exception(*http_err.get_exc_info())
        else:
            if isinstance(retval, tuple) and len(retval) == 3:
                status, headers, body = retval
                headers = dict(headers)
            else:
                status, headers, body = 200, {}, retval

        if not body and isinstance(body, (list, tuple, bytes, unicode)):
            # Empty body, return early.
            headers['Content-Length'] = '0'
            start_response(format_status(status), headers.items())
            return []

        if isinstance(body, (list, tuple)):
            # Join a list of strings into one fat string - probably less
            # effort to handle on server site and does not use more space
            # anyway (in fact it saves some bytes).
            body = body[0][0:0].join(body)

        if isinstance(body, (bytes, unicode)):
            assert body
            if isinstance(body, unicode):
                body = body.encode(self.charset)
            isetdefault(headers, 'Content-Length', len(body))
            isetdefault(headers, 'Content-Type',
                        'text/plain' if self.debug else self.default_content_type)
            body = [body]
        elif isinstance(body, file):
            isetdefault(headers, 'Content-Length', os.path.getsize(body.name))
            mime, _ = mimetypes.guess_type(body.name)
            if mime is not None:
                isetdefault(headers, 'Content-Type', mime)
            body = self.get_filewrapper(environ)(body)

        start_response(format_status(status), headers.items())
        return body

    def dispatch(self, environ):
        request_path = environ['PATH_INFO'] or '/'
        for route, callback in self.routes:
            match = route.match(request_path)
            if match is not None:
                return callback, match.groupdict()
        return None, None

    def get_filewrapper(self, environ):
        return environ.get('wsgi.file_wrapper',
                           (lambda f: iter(lambda: f.read(self.chunksize), '')))
