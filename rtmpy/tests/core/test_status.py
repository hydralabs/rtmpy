"""
Tests for L{rtmpy.core.status}
"""

from twisted.trial import unittest

from rtmpy.core import status



class StatusHelperTestCase(unittest.TestCase):
    """
    Tests for L{status.status}
    """


    def test_interface(self):
        """
        Ensure that the returned status object implements the correct interface.
        """
        s = status.status(None, None)

        self.assertTrue(status.IStatus.providedBy(s))


    def test_return(self):
        """
        Check the attribute allocation.
        """
        s = status.status('foo', 'bar', spam='eggs', gak=[1, 2, 3])

        # core attributes
        self.assertEqual(s.level, 'status')
        self.assertEqual(s.code, 'foo')
        self.assertEqual(s.description, 'bar')

        # extra context
        self.assertEqual(s.spam, 'eggs')
        self.assertEqual(s.gak, [1, 2, 3])



class ErrorHelperTestCase(unittest.TestCase):
    """
    Tests for L{status.error}
    """

    def test_interface(self):
        """
        Ensure that the returned status object implements the correct interface.
        """
        s = status.error(None, None)

        self.assertTrue(status.IStatus.providedBy(s))


    def test_return(self):
        """
        Check the attribute allocation.
        """
        s = status.error('foo', 'bar', spam='eggs', gak=[1, 2, 3])

        # core attributes
        self.assertEqual(s.level, 'error')
        self.assertEqual(s.code, 'foo')
        self.assertEqual(s.description, 'bar')

        # extra context
        self.assertEqual(s.spam, 'eggs')
        self.assertEqual(s.gak, [1, 2, 3])



class StatusTestCase(unittest.TestCase):
    """
    Tests for L{status.Status}
    """


    def test_interface(self):
        """
        Ensure that the correct interface is implemented.
        """
        self.assertTrue(status.IStatus.implementedBy(status.Status))

        s = status.Status(None, None, None)

        self.assertTrue(status.IStatus.providedBy(s))


    def test_create(self):
        """
        Test attribute allocation.
        """
        s = status.Status('foo', 'bar', 'baz', spam='eggs')

        self.assertEqual(s.level, 'foo')
        self.assertEqual(s.code, 'bar')
        self.assertEqual(s.description, 'baz')

        self.assertEqual(s.spam, 'eggs')


    def test_unicode(self):
        """
        Ensure that unicode is handled correctly.
        """
        s = status.Status(None, 'bar', 'baz')

        self.assertEqual(unicode(s), 'bar: baz')

    def test_equality(self):
        """
        Its all in the name.
        """
        s = status.Status('foo', 'bar', 'baz')

        # simple scalar checks
        self.assertNotEqual(s, 1)
        self.assertNotEqual(s, None)
        self.assertNotEqual(s, 'foo')

        ref_dict = {
            'level': 'foo',
            'code': 'bar',
            'description': 'baz'
        }

        self.assertEqual(s, ref_dict)


class AMFEncodingTestCase(unittest.TestCase):
    """
    Tests to ensure that AMF encoding works smoothly.
    """


    def setUp(self):
        import pyamf

        try:
            pyamf.get_class_alias(status.Status)
        except pyamf.UnknownClassAlias:
            self._old_alias = None
        else:
            raise RuntimeError(
                'Unexpected status.Status class registered in PyAMF')

        self.alias = pyamf.register_class(status.Status)


    def tearDown(self):
        import pyamf

        pyamf.unregister_class(status.Status)

        if self._old_alias:
            pyamf.register_class(self._old_alias)


    def test_static_attributes(self):
        """
        Ensure that the core attributes will be encoded in order correctly.
        """
        self.alias.compile()

        self.assertEqual(
            self.alias.static_attrs, ['level', 'code', 'description'])


    def test_amf0(self):
        """
        Test encoding in AMF0.
        """
        import pyamf

        ref_dict = {
            'level': 'alevel',
            'code': 'Some.Code.Here',
            'description': 'Look mom, no hands!'
        }

        s = status.Status(
            ref_dict['level'],
            ref_dict['code'],
            ref_dict['description'])

        blob = pyamf.encode(s, encoding=pyamf.AMF0)

        decoded_status = pyamf.decode(blob, encoding=pyamf.AMF0).next()

        self.assertEqual(decoded_status, s)


    def test_amf3(self):
        """
        Test encoding in AMF3.
        """
        import pyamf

        ref_dict = {
            'level': 'alevel',
            'code': 'Some.Code.Here',
            'description': 'Look mom, no hands!'
        }

        s = status.Status(
            ref_dict['level'],
            ref_dict['code'],
            ref_dict['description'])

        blob = pyamf.encode(s, encoding=pyamf.AMF3)

        decoded_status = pyamf.decode(blob, encoding=pyamf.AMF3).next()

        self.assertEqual(decoded_status, s)



class TestRuntimeError(RuntimeError):
    """
    """

    code = 'Test.RuntimeError'



class FromFailureTestCase(unittest.TestCase):
    """
    Tests for L{status.fromFailure}
    """


    def buildFailure(self, exc_type, msg):
        try:
            raise exc_type(msg)
        except exc_type:
            from twisted.python import failure

            return failure.Failure()

        self.fail('Did not build failure instance correctly')


    def test_status(self):
        """
        Ensure that L{statust.fromFailure} works as expected
        """
        f = self.buildFailure(TestRuntimeError, 'foo bar')

        s = status.fromFailure(f)

        self.assertTrue(status.IStatus.providedBy(s))
        self.assertEqual(s.level, 'error')
        self.assertEqual(s.code, 'Test.RuntimeError')
        self.assertEqual(s.description, 'foo bar')


    def test_default_code(self):
        """
        L{status.fromFailure} looks for a C{code} attribute on the exception
        instance contained in the failure. If one is not present, supplying a
        default code is allowed.
        """
        f = self.buildFailure(RuntimeError, 'spam eggs')

        self.assertFalse(hasattr(f.value, 'code'))

        s = status.fromFailure(f, 'default code')

        self.assertTrue(status.IStatus.providedBy(s))
        self.assertEqual(s.level, 'error')
        self.assertEqual(s.code, 'default code')
        self.assertEqual(s.description, 'spam eggs')
