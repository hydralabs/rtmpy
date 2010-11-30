RTMPy_ is a Twisted_ protocol implementing the Real Time Messaging Protocol
(RTMP_), used for streaming audio, video and data between the
`Adobe Flash Player`_ and a server.

As of 0.1, RTMPy provides a simple server architecture, something that will be
expanded on over the next coming releases.

Probably the simplest Python script to up and running:

.. code-block:: python

  import sys

  from twisted.internet import reactor
  from twisted.python import log

  from rtmpy import server

  app = server.Application()

  reactor.listenTCP(1935, server.ServerFactory({
      'live': app
  }))

  log.startLogging(sys.stdout)

  reactor.run()


The server framework is loosely based on the same design as the `FMS Server Side
ActionScript Language Reference`_. Specifically the `Application class`_,
`Client class`_ and `Stream class`_.


.. _RTMPy:			        http://rtmpy.org
.. _Twisted:			    http://twistedmatrix.com
.. _RTMP:			        http://en.wikipedia.org/wiki/Real_Time_Messaging_Protocol
.. _Adobe Flash Player:		http://en.wikipedia.org/wiki/Adobe_Flash_Player
.. _FMS Server Side ActionScript Language Reference: http://www.adobe.com/livedocs/flashmediaserver/3.0/hpdocs/help.html?content=Book_Part_34_ss_asd_1.html
.. _Application class:      http://www.adobe.com/livedocs/flashmediaserver/3.0/hpdocs/help.html?content=00000229.html#151509
.. _Client class:           http://www.adobe.com/livedocs/flashmediaserver/3.0/hpdocs/00000257.html#72218
.. _Stream class:           http://www.adobe.com/livedocs/flashmediaserver/3.0/hpdocs/00000386.html#230476
