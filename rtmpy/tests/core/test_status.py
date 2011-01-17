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

