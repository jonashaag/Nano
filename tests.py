# coding: utf-8
try:
    from unittest2 import TestCase, main
except ImportError:
    from unittest import TestCase, main

from nano import NanoApplication, HttpError

class Test(TestCase):
    def setUp(self):
        self.app = NanoApplication()
        self.setup()

    def setup(self):
        pass

    def assertContains(self, haystack, *needles):
        for needle in needles:
            self.assertIn(needle, haystack)

    def assertResponse(self, *args, **attrs):
        response = self.call_app(*args)
        for attr, value in attrs.iteritems():
            self.assertEqual(getattr(response, attr), value)

    def route(self, callback):
        self.app.route('/')(callback)
        return self

    def call_app(self, url='/', environ=None):
        class result: pass
        def start_response(status, headers):
            result.status, result.headers = status, dict(headers)
        if environ is None:
            environ = {}
        environ['PATH_INFO'] = url
        result.body = self.app(environ, start_response)
        return result

class TestRouting(Test):
    def _mock(self, n, _cache={}):
        if n not in _cache:
            _cache[n] = type('c%d' % n, (), {})
        return _cache[n]

    def setup(self):
        self.app.route('/')(self._mock(1))
        self.app.route('/a/')(self._mock(2))
        self.app.route('/:a/')(self._mock(3))
        self.app.route('/:a:/')(self._mock(4))
        self.app.route('/:a1b2:/[0-9]+/')(self._mock(6))
        self.app.route('/:a:/(?P<b>[^\d]+)/')(self._mock(5))
        self.app.route('/(?P<a>.*)/')(self._mock(7))

    def test_dispatch(self):
        def dispatch(path): return self.app.dispatch({'PATH_INFO' : path})
        self.assertEqual(dispatch('/'), (self._mock(1), {}))
        self.assertEqual(dispatch('/a/'), (self._mock(2), {}))
        self.assertEqual(dispatch('/:a/'), (self._mock(3), {}))
        self.assertEqual(dispatch('/foo/'), (self._mock(4), {'a' : 'foo'}))
        self.assertEqual(dispatch('/foo/bar/'), (self._mock(5), {'a' : 'foo', 'b' : 'bar'}))
        self.assertEqual(dispatch('/foo/bar'), (None, None))
        self.assertEqual(dispatch('/foo/0123/'), (self._mock(6), {'a1b2' : 'foo'}))

    def test_build_url(self):
        self.assertEqual(self.app.build_url('c1'), '/')
        self.assertEqual(self.app.build_url('c2'), '/a/')
        self.assertEqual(self.app.build_url('c3'), '/:a/')
        self.assertEqual(self.app.build_url('c4', a='42'), '/42/')
        self.assertEqual(self.app.build_url('c5', a='foo', b='asd'), '/foo/asd/')

        # Substitutes should be escaped:
        self.assertEqual(self.app.build_url('c4', a=' äöß®'),
                       '/%20%C3%A4%C3%B6%C3%9F%C2%AE/')

        self.assertRaisesRegexp(
            TypeError, "Wildcard values must be strings \(got <type 'object'> object instead\)",
            self.app.build_url, 'c3', a=object()
        )

        for view_name, kwargs in [
            ('c1', {'a': 1}),
            ('c3', {'a': 1, 'b': 2}),
            ('c3', {'b': 2}),
            ('c5', {'a': 'foo', 'b': 123}),
            ('c7', {})
        ]:
            self.assertRaisesRegexp(ValueError, "Wildcard substitutions didn't",
                                    self.app.build_url, view_name, **kwargs)

    def test_build_url_with_SCRIPT_NAME(self):
        def callback(env):
            return self.app.build_url('c4', a='bla')
        self.app.route('/Gemüse')(callback)
        self.assertEqual(
            self.call_app('/Gemüse', {'SCRIPT_NAME': '/script-name'}).body[0],
            '/script-name/bla/'
        )

class Test404(Test):
    def assert_404(self):
        self.assertResponse(
            status='404 Not Found',
            body=[],
            headers={'Content-Length' : '0'}
        )

    def test_without_routes(self):
        self.assert_404()

    def test_with_routes(self):
        self.app.route('/a')(1)
        self.assert_404()

class TestExceptionInCallback(Test):
    def setup(self):
        def callback1(environ): raise HttpError('123 blabla')
        def callback2(environ): raise TypeError('Blabla')
        def callback3(environ): raise HttpError('42 foo', 'body 42')
        self.app.route('/HttpError')(callback1)
        self.app.route('/TypeError')(callback2)
        self.app.route('/withbody')(callback3)

    def _test_withbody(self):
        self.assertResponse('/withbody', status='42 foo', body=['body 42'],
            headers={'Content-Length' : '7', 'Content-Type' : 'text/plain'})

    def test_nodebug(self):
        for url, status in [('/HttpError', '123 blabla'), ('/TypeError', '500 Internal Server Error')]:
            self.assertResponse(url, status=status, body=[],
                                headers={'Content-Length' : '0'})
        self._test_withbody()

    def test_debug(self):
        self.app.debug = True
        self.assertContains(self.call_app('/HttpError').body[0],
                            'Traceback (most recent call last)',
                            'HttpError: 123 blabla')
        self.assertContains(self.call_app('/TypeError').body[0],
                            'Traceback (most recent call last)',
                            'TypeError: Blabla')
        self._test_withbody()

    def test_debug_with_custom_default_content_type(self):
        self.app.debug = True
        self.app.default_content_type = 'foo/bar'
        self.assertEqual(self.call_app('/HttpError').headers['Content-Type'],
                       'text/plain')

class TestReturnTypes(Test):
    tests = [
        'Hello World', {
            'body' : ['Hello World'],
            'headers' : {'Content-Length' : '11', 'Content-Type' : 'text/plain'},
            'status' : '200 OK'
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
            'status' : '200 OK'
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
            self.assertResponse(**_iter.next())

        self.app = NanoApplication(default_content_type='hello/world')
        self.route(callback)
        self.assertResponse(**self.tests[-1])
        callback.app_retval = 'Hello World'
        self.app.debug = True
        self.assertResponse(body=['Hello World'], status='200 OK',
            headers={'Content-Length' : '11', 'Content-Type' : 'hello/world'})

    def test_custom_iterator(self):
        iterator = iter(['foo', 'bar'])
        callback = lambda env: iterator
        self.route(callback)
        self.assertResponse(headers={}, status='200 OK')
        self.assert_(self.call_app().body is iterator)

    def test_file(self):
        CallableIterator = type(iter(lambda: x, 42))
        fname = '/tmp/nano.css'

        with open(fname, 'w') as fd:
            fd.write('body { color: #42 }')
        try:
            app = self.route(lambda env: open(fname)).call_app
            class MockFileWrapper(Exception):
                pass
            for env, tp in [
                ({'wsgi.file_wrapper' : MockFileWrapper}, MockFileWrapper),
                ({}, CallableIterator)
            ]:
                result = app(environ=env)
                self.assertIsInstance(result.body, tp)
                self.assertEqual(result.headers,
                               {'Content-Length' : '19',
                                'Content-Type' : 'text/css'})
        finally:
            from os import remove; remove(fname)

if __name__ == '__main__':
    main()
