# -*- test-case-name: rtmpy.tests.test_dispatcher -*-

# Copyright the RTMPy Project
#
# RTMPy is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 2.1 of the License, or (at your option)
# any later version.
#
# RTMPy is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with RTMPy.  If not, see <http://www.gnu.org/licenses/>.
#
# A lot of this code is copied from the Twisted codebase but adapted to remove
# the XML stuff from it.

"""
Event Dispatching and Callback utilities.

@since: 0.1
"""

from zope.interface import Interface, implements
from twisted.internet import reactor
from twisted.python import log

class IEventDispatcher(Interface):
    """
    The IEventDispatcher interface defines methods for adding or removing
    event listeners, checks whether specific types of event listeners are
    registered, and dispatches events.
    """

    def addEventListener(event, listener, priority=0, *args, **kwargs):
        """
        Registers an event listener object with an EventDispatcher object so
        that the listener receives notification of an event.
        """

    def dispatchEvent(event, *args, **kwargs):
        """
        Dispatches an event into the event flow.
        """

    def hasEventListener(event):
        """
        Checks whether the EventDispatcher object has any listeners registered
        for a specific type of event.
        """

    def removeEventListener(event, listener):
        """
        Removes a listener from the IEventDispatcher object.
        """


class _MethodWrapper(object):
    """
    Internal class for tracking method calls.
    """

    def __init__(self, method, *args, **kwargs):
        self.method = method
        self.args = args
        self.kwargs = kwargs

    def __call__(self, *args, **kwargs):
        nargs = self.args + args
        nkwargs = self.kwargs.copy()
        nkwargs.update(kwargs)

        self.method(*nargs, **nkwargs)


class CallbackList(object):
    """
    Container for callbacks.

    Event queries are linked to lists of callables. When a matching event
    occurs, these callables are called in sequence.

    Arguments to callbacks are split spread across two sets. The first set,
    callback specific, is passed to C{addCallback} and is used for all
    subsequent event triggers.  The second set is passed to C{callback} and is
    event specific. Positional arguments in the second set come after the
    positional arguments of the first set. Keyword arguments in the second set
    override those in the first set.

    @ivar callbacks: The registered callbacks as mapping from the callable to
        a tuple of a wrapper for that callable that keeps the callback
        specific arguments and a boolean that signifies if it is to be called
        only once.
    @type callbacks: C{dict}
    """

    def __init__(self):
        self.callbacks = {}
        self.order = []

    def addCallback(self, method, *args, **kwargs):
        """
        Add callback.

        The arguments passed are used as callback specific arguments.

        @param method: The callback callable to be added.
        @param args: Positional arguments to the callable.
        @type args: C{list}
        @param kwargs: Keyword arguments to the callable.
        @type kwargs: C{dict}
        """
        if not method in self.callbacks:
            self.callbacks[method] = _MethodWrapper(method, *args, **kwargs)
            self.order.append(method)

    def removeCallback(self, method):
        """
        Remove callback.

        @param method: The callable to be removed.
        """
        if method in self.callbacks:
            del self.callbacks[method]
            self.order.remove(method)

    def callback(self, *args, **kwargs):
        """
        Call all registered callbacks.

        The passed arguments are event specific and augment and override
        the callback specific arguments as described above.

        @note: Exceptions raised by callbacks are trapped and logged. They
            will not propagate up to make sure other callbacks will still be
            called, and the event dispatching always succeeds.

        @param args: Positional arguments to the callable.
        @type args: C{list}
        @param kwargs: Keyword arguments to the callable.
        @type kwargs: C{dict}
        """
        for key in self.order:
            methodwrapper = self.callbacks[key]

            try:
                methodwrapper(*args, **kwargs)
            except:
                log.err()

    def isEmpty(self):
        """
        Return if list of registered callbacks is empty.

        @rtype: C{bool}
        """
        return len(self.callbacks) == 0


class EventDispatcher(object):
    """
    Event dispatching service.

    The C{EventDispatcher} allows observers to be registered for certain
    events that are dispatched.

    Every dispatch is triggered by calling L{dispatchEvent} with the name of
    the event. A named event will simply call each registered observer for
    that particular event name, with any supplied arguments.

    When registering observers, the event that is to be observed is specified
    using a string.

    Observers registered using L{addEventListener} are persistent: after the
    observer has been triggered by a dispatch, it remains registered for a
    possible next dispatch.

    Observers can also prioritized, by providing an optional C{priority}
    parameter to the L{addEventListener}. Higher priority observers are then
    called before lower priority observers.

    Finally, observers can be unregistered by using L{removeEventListener}.

    @ivar listeners: A collection of priority->event->observers
    @type listeners: C{dict}
    """

    implements(IEventDispatcher)

    def __init__(self):
        self.listeners = {}
        self._dispatchDepth = 0
        self._updateQueue = []

    def addEventListener(self, event, listener, priority=0, *args, **kwargs):
        """
        Adds a listener to this event dispatcher. If L{dispatchEvent} is
        called with the corresponding C{event} then listener will be called
        with the supplied C{*args} and C{**kwargs}.
        """
        if self._dispatchDepth > 0:
            self._updateQueue.append(
                lambda: self.addEventListener(
                    event, listener, priority, *args, **kwargs))

            return

        if priority not in self.listeners:
            cbl = CallbackList()
            self.listeners[priority] = {event: cbl}
        else:
            priorityObservers = self.listeners[priority]
            if event not in priorityObservers:
                cbl = CallbackList()
                self.listeners[priority][event] = cbl
            else:
                cbl = priorityObservers[event]

        cbl.addCallback(listener, *args, **kwargs)

    def removeEventListener(self, event, listener):
        """
        Removes a listener from this event dispatcher.
        """
        # If this is happening in the middle of the dispatch, queue it up for
        # processing after the dispatch completes
        if self._dispatchDepth > 0:
            self._updateQueue.append(
                lambda: self.removeEventListener(event, listener))

            return

        for priority in self.listeners.keys():
            if event in self.listeners[priority]:
                cbl = self.listeners[priority][event]

                cbl.removeCallback(listener)

    def hasEventListener(self, event):
        """
        Return if a listener is registered to an event.

        @rtype: C{bool}
        """
        for priority, listeners in self.listeners.iteritems():
            if listeners.has_key(event):
                return True

        return False

    def _callLater(self, *args, **kwargs):
        return reactor.callLater(*args, **kwargs)

    def _dispatchEvent(self, event, *args, **kwargs):
        self._dispatchDepth += 1

        priorities = self.listeners.keys()
        priorities.sort()
        priorities.reverse()

        emptyLists = []
        for priority in priorities:
            for query, callbacklist in self.listeners[priority].iteritems():
                if not query == event:
                    continue

                callbacklist.callback(*args, **kwargs)

                if callbacklist.isEmpty():
                    emptyLists.append((priority, query))

        for priority, query in emptyLists:
            del self.listeners[priority][query]

        self._dispatchDepth -= 1

        # If this is a dispatch within a dispatch, don't do anything with the
        # updateQueue -- it needs to wait until we've back all the way out of
        # the stack
        if self._dispatchDepth == 0:
            [f() for f in self._updateQueue]
            self._updateQueue = []

    def dispatchEvent(self, event, *args, **kwargs):
        """
        Dispatches an event into the event flow.
        """
        self._callLater(0, self._dispatchEvent, event, *args, **kwargs)
