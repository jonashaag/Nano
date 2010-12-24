# coding: utf-8
import unittest
from nano import NanoApplication, HttpError

class Test(unittest.TestCase):
    def setUp(self):
        self.app = NanoApplication()
        self.setup()

    def setup(self):
        pass

    def assert_eq(self, *args, **kwargs):
        return self.assertEqual(*args, **kwargs)

    def assert_contains(self, haystack, *needles):
        for needle in needles:
            self.assertIn(needle, haystack)

    def assert_obj_eq(self, obj, **attrs):
        for attr, value in attrs.iteritems():
            self.assert_eq(getattr(obj, attr), value)

    def route(self, callback):
        self.app.route('/')(callback)
        return self

    def call_app(self, url='/'):
        class result: pass
        def start_response(status, headers):
            result.status, result.headers = status, dict(headers)
        result.body = self.app({'PATH_INFO' : url}, start_response)
        return result

class TestRouting(Test):
    def setup(self):
        self.app.route('/')(1)
        self.app.route('/a/')(2)
        self.app.route('/:a/')(3)
        self.app.route('/:a:/')(4)
        self.app.route('/:a1b2:/[0-9]+/')(6)
        self.app.route('/:a:/(?P<b>[^\d]+)/')(5)

    def test_dispatch(self):
        def dispatch(path): return self.app.dispatch({'PATH_INFO' : path})
        self.assert_eq(dispatch('/'), (1, {}))
        self.assert_eq(dispatch('/a/'), (2, {}))
        self.assert_eq(dispatch('/:a/'), (3, {}))
        self.assert_eq(dispatch('/foo/'), (4, {'a' : 'foo'}))
        self.assert_eq(dispatch('/foo/bar/'), (5, {'a' : 'foo', 'b' : 'bar'}))
        self.assert_eq(dispatch('/foo/bar'), (None, None))
        self.assert_eq(dispatch('/foo/0123/'), (6, {'a1b2' : 'foo'}))

class Test404(Test):
    def assert_404(self):
        self.assert_obj_eq(self.call_app(), status='404 Go Away', body=[],
                           headers={'Content-Length' : 0})

    def test_without_routes(self):
        self.assert_404()

    def test_with_routes(self):
        self.app.route('/a')(1)
        self.assert_404()

class TestExceptionInCallback(Test):
    def setup(self):
        def callback1(environ): raise HttpError('123 blabla')
        def callback2(environ): raise TypeError('Blabla')
        self.app.route('/HttpError')(callback1)
        self.app.route('/TypeError')(callback2)

    def test_nodebug(self):
        for url, status in [('/HttpError', '123 blabla'), ('/TypeError', '500 OH NOEZ')]:
            self.assert_obj_eq(self.call_app(url), status=status, body=[],
                headers={'Content-Type' : 'text/plain', 'Content-Length' : '0'})

    def test_debug(self):
        self.app.debug = True
        self.assert_contains(self.call_app('/HttpError').body[0],
                             'Traceback (most recent call last)',
                             'HttpError: 123 blabla')
        self.assert_contains(self.call_app('/TypeError').body[0],
                             'Traceback (most recent call last)',
                             'TypeError: Blabla')

class TestReturnTypes(Test):
    tests = [
        'Hello World', {
            'body' : ['Hello World'],
            'headers' : {'Content-Length' : '11', 'Content-Type' : 'text/plain'},
            'status' : '200 Here You Go'
        },
        ('123 foo', {'a' : 1}, ['Hello World']), {
            'body' : ['Hello World'],
            'headers' : {'Content-Length' : '11', 'Content-Type' : 'text/plain',
                         'a' : 1},
            'status' : '123 foo'
        },
        (200, [('b', 2)], [u'Hellö ', 'World']), {
            'body' : ['Hellö World'],
            'headers' : {'Content-Length' : '12', 'Content-Type' : 'text/plain', 'b' : 2},
            'status' : '200 Here You Go'
        },
        (123, {'Content-Length' : '42'}, u'blööök'), {
            'body' : [u'blööök'.encode('utf-8')],
            'headers' : {'Content-Length' : '42', 'Content-Type' : 'text/plain'},
            'status' : '123 <reason>'
        },
        ('200 ok', {'Content-Type' : 'foo/bar'}, []), {
            'body' : [],
            'headers' : {'Content-Length' : '0', 'Content-Type' : 'foo/bar'}
        }
    ]

    def test_types(self):
        callback = lambda env: callback.app_retval
        self.route(callback)
        _iter = iter(self.tests)
        for i in xrange(len(self.tests)/2):
            callback.app_retval = _iter.next()
            self.assert_obj_eq(self.call_app(), **_iter.next())

    def test_custom_iterator(self):
        iterator = iter(['foo', 'bar'])
        callback = lambda env: iterator
        self.route(callback)
        self.assert_obj_eq(self.call_app(), headers={}, status='200 Here You Go')
        self.assert_(self.call_app().body is iterator)

    def test_file(self):
        fname = '/tmp/nano.css'
        with open(fname, 'w') as fd:
            fd.write('body { color: #42 }')
        try:
            fd = open(fname)
            callback = lambda env: fd
            self.assert_(self.route(callback).call_app().body is fd)
            self.assert_eq(self.call_app().headers,
                           {'Content-Length' : '19',
                            'Content-Type' : 'text/css'})
        finally:
            from os import remove; remove(fname)

if __name__ == '__main__':
    unittest.main()
