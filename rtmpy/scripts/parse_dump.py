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

"""
Parses RTMP dumps from Wireshark - converted to c array format.

@since: 0.1.1
"""

from pyamf.util import BufferedByteStream
from rtmpy.protocol.rtmp import codec, message


__all__ = ['parse_dump', 'XMLObserver']


def parse_dump(f, observer):
    """
    Reads a pre-recorded RTMP stream (in c array format) from C{f} and sends
    the messages to C{observer}.

    C{observer} must implement C{messageStart}, C{messageReceived} and
    C{messageComplete}. See L{XMLObserver} as an example.
    """
    recv = RTMPEndpoint('server', observer)
    send = RTMPEndpoint('client', observer)

    for label, data in read_dump(f):
        endpoint = None

        if label == 'recv':
            endpoint = recv
        elif label == 'send':
            endpoint = send

        if not endpoint:
            continue

        endpoint.dataReceived(data)

        [y for y in endpoint]



def read_dump(f):
    """
    Takes an open file object that reads c array formatted text and returns a
    generator that will return tuples containing the label for the endpoint
    (we assume the first block is from the sender, but the labelling is
    arbitrary) and the bytes sent.
    """
    to = 'send'
    buf = ''

    while True:
        line = f.readline()

        if not line:
            raise StopIteration

        line = clean_line(line)

        if line == '':
            continue

        if line.endswith('{'):
            # parse a "char peer1_188[] = {" line
            ch = line[9]
            if ch == '0':
                to = 'send'
            else:
                to = 'recv'

            buf = ''
        elif line.endswith('};'):
            buf += line[:-2]

            yield (to, parse_bytes(buf.strip()))
        else:
            buf += line



def clean_line(l):
    l = l.replace('\r\n', '')
    l = l.replace('\n', '')
    l = l.strip()

    return l



def parse_bytes(buf):
    # this could be *a lot* faster ..
    buf = buf.replace(', ', '')
    buf = buf.replace(',', '')
    buf = buf.replace('0x', 'x')

    s = ''

    for x in buf[1:].split('x'):
        s += chr(int(x, 16))

    return s



class Message(object):
    """
    An RTMP message that has a type and context.
    """

    def __init__(self, __type, **kwargs):
        self.type = __type
        self.context = kwargs



# A packet is the raw form of a Message
Packet = Message



class Stream(object):
    """
    An RTMP stream that recieves messages. Pushes all messages to the observer
    """

    def __init__(self, observer):
        self.observer = observer

    def onInvoke(self, name, id_, args, timestamp):
        m = Message('invoke', name=name, id=id_, args=args)

        self.observer.messageReceived(m)

    def onNotify(self, name, args, timestamp):
        m = Message('notify', name=name, args=args)

        self.observer.messageReceived(m)

    def onAudioData(self, data, timestamp):
        m = Message('audio', length=len(data), timestamp=timestamp)

        self.observer.messageReceived(m)

    def onVideoData(self, data, timestamp):
        m = Message('video', length=len(data), timestamp=timestamp)

        self.observer.messageReceived(m)

    def onControlMessage(self, msg, timestamp):
        m = Message('control', **msg.__dict__)

        self.observer.messageReceived(m)

    def onDownstreamBandwidth(self, bw, timestamp):
        m = Message('down_bandwidth', value=bw)

        self.observer.messageReceived(m)

    def onUpstreamBandwidth(self, bw, extra, timestamp):
        m = Message('up_bandwidth', value=bw, extra=extra)

        self.observer.messageReceived(m)

    def onBytesRead(self, value, timestamp):
        m = Message('bytes_read', value=value)

        self.observer.messageReceived(m)


class ControlStream(Stream):
    """
    A specialised stream that handles the most basic RTMP command message/s.

    In this case all we need to look out for is the frame size.
    """

    def __init__(self, observer, decoder):
        Stream.__init__(self, observer)

        self.decoder = decoder

    def onFrameSize(self, size, timestamp):
        m = Message('frame_size', size=size)

        self.observer.messageReceived(m)

        self.decoder.setFrameSize(size)



class StreamFactory(object):
    """
    Builds and manages individual RTMP streams and dispatches decoded messages
    to the stream accordingly.
    """

    def __init__(self, type, observer):
        self.streams = {}
        self.type = type
        self.observer = observer

    def getStream(self, streamId):
        s = self.streams.get(streamId, None)

        if s is not None:
            return s

        if streamId == 0:
            s = ControlStream(self.observer, self.decoder)
        else:
            s = Stream(self.observer)

        s.streamId = streamId

        self.streams[streamId] = s

        return s

    def dispatchMessage(self, stream, datatype, timestamp, data):
        p = Packet(self.type,
            streamId=stream.streamId, datatype=datatype, timestamp=timestamp)

        self.observer.messageStart(p)

        e = message.get_type_class(datatype)()

        e.decode(BufferedByteStream(data))

        e.dispatch(stream, timestamp)

        self.observer.messageComplete(p)

    def bytesInterval(self, bytes):
        pass



class RTMPEndpoint(object):
    """
    Represents one side of the TCP transmission. Handles the handshake and
    pushes all data to the RTMP decoder.
    """

    handshake_size = 1536 * 2 + 1

    def __init__(self, label, observer):
        self.label = label
        self.observer = observer

        self.factory = StreamFactory(self.label, self.observer)
        self.decoder = codec.Decoder(self.factory, self.factory)

        self.factory.decoder = self.decoder

        self.handshake = False
        self.buffer = ''

    def dataReceived(self, data):
        """
        """
        if not self.handshake:
            self.buffer += data

            if len(self.buffer) >= self.handshake_size:
                self.handshake = True

                data = self.buffer[self.handshake_size:]
                del self.buffer

        if self.handshake:
            self.decoder.send(data)

    def __iter__(self):
        return self.decoder



class XMLObserver(object):
    """
    An RTMP observer that spits out an XML stream to a file object.
    """

    tag_types = (basestring, int, long)
    noisy = False

    def __init__(self, file):
        self.file = file

    def _to_xml(self, dict, shorten=False):
        s = ''

        as_tags = []

        for k, n in dict.iteritems():
            if not isinstance(n, self.tag_types):
                as_tags.append([k, n])

                continue

            s += ' %s="%s"' % (k, str(n))

        if not as_tags:
            if shorten:
                s += '/>'
            else:
                s += '>'
        else:
            s += '>\n'

            for k, v in as_tags:
                s += '  <%s>%r</%s>\n' % (k, v, k)

        return s

    def messageStart(self, packet):
        xml = '<message from="%s"%s' % (
            packet.type, self._to_xml(packet.context))

        self.file.write(xml + '\n')

    def messageReceived(self, message):
        xml = ' <%s%s' % (message.type, self._to_xml(message.context, True))

        if not xml.endswith('/>'):
            xml += ' </%s>' % (message.type,)

        xml += '\n'

        self.file.write(xml)

    def messageComplete(self, packet):
        self.file.write('</message>\n')


def run():
    import sys

    observer = XMLObserver(sys.stdout)

    f = open(sys.argv[1], 'rb')

    try:
        parse_dump(f, observer)
    finally:
        f.close()
