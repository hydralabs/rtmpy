import logging
from logging import debug, info, warning
import struct
import time

from twisted.internet.protocol import Protocol
from twisted.internet import reactor, protocol

from util import ByteStream, hexdump, Enum

# Size of initial handshake between client and server
HANDSHAKE_SIZE = 1536

# Default size of RTMP chunks
DEFAULT_CHUNK_SIZE = 128

# Max. time in milliseconds to wait for a valid handshake.
maxHandshakeTimeout = 5000

server_start_time = None

def uptime():
    """Returns uptime in milliseconds, starting at first call"""
    if not hasattr(uptime, "t0") is None:
        uptime.t0 = time.time()
    return int((time.time() - uptime.t0)*1000)

Modes = Enum('SERVER', 'CLIENT')
States = Enum('HANDSHAKE', 'HANDSHAKE_VERIFY', 'RTMP')

class RTMPTypes:
    """Class for AMF and RTMP marker values constants."""
    # RTMP chunk size constant
    CHUNK_SIZE  =               0x01
    # Unknown:                  0x02
    # Send every x bytes read by both sides
    BYTES_READ  =               0x03
    # Ping is a stream control message, has subtypes
    PING        =               0x04
    # Server (downstream) bandwidth marker
    SERVER_BW   =               0x05
    # Client (upstream) bandwidth marker
    CLIENT_BW   =               0x06
    # Unknown:                  0x07
    # Audio data marker
    AUDIO_DATA  =               0x08
    # Video data marker
    VIDEO_DATA  =               0x09
    # Unknown:                  0x0A ... 0x0F
    # AMF3 shared object
    FLEX_SHARED_OBJECT =        0x10
    # AMF3 message
    FLEX_MESSAGE =              0x11
    # Notification is invocation without response
    NOTIFY      =               0x12
    # Stream metadata
    STREAM_METADATA =           0x12
    # Shared Object marker
    SO          =               0x13
    # Invoke operation (remoting call but also used
    # for streaming) marker
    INVOKE      =               0x14
    # New header marker
    HEADER_NEW =                0x00
    # Same source marker
    SAME_SOURCE =               0x01
    # Timer change marker
    HEADER_TIMER_CHANGE =       0x02
    # There's more to encode
    HEADER_CONTINUE =           0x03
    # Client Shared Object data update
    CLIENT_UPDATE_DATA =        0x04
    # Client Shared Object attribute update
    CLIENT_UPDATE_ATTRIBUTE =   0x05
    # Send Shared Object message flag
    CLIENT_SEND_MESSAGE =       0x06
    # Shared Object status marker
    CLIENT_STATUS =             0x07
    # Shared Object status marker
    CLIENT_CLEAR_DATA =         0x08
    # Delete data for Shared Object
    CLIENT_DELETE_DATA =        0x09
    # Initial Shared Object data flag
    CLIENT_INITIAL_DATA =       0x0B
    # Shared Object connection
    SO_CONNECT =                0x01
    # Shared Object disconnect
    SO_DISCONNECT =             0x02
    # Set Shared Object attribute flag
    SET_ATTRIBUTE =             0x03
    # Send message flag
    SEND_MESSAGE =              0x06
    # Shared Object attribute deletion flag
    DELETE_ATTRIBUTE =          0x0A
    #
    ACTION_CONNECT =            "connect"
    ACTION_DISCONNECT =         "disconnect"
    ACTION_CREATE_STREAM =      "createStream"
    ACTION_DELETE_STREAM =      "deleteStream"
    ACTION_CLOSE_STREAM =       "closeStream"
    ACTION_RELEASE_STREAM =     "releaseStream"
    ACTION_PUBLISH =            "publish"
    ACTION_PAUSE =              "pause"
    ACTION_SEEK =               "seek"
    ACTION_PLAY =               "play"
    ACTION_STOP =               "disconnect"
    ACTION_RECEIVE_VIDEO =      "receiveVideo"
    ACTION_RECEIVE_AUDIO =      "receiveAudio"
    
class RTMPHeader:
    def __init__(self, channel):
        # Channel
        self.channel = channel
        # Timer
        self.timer = None
        # Header size
        self.size = None
        # Type of data
        self.type = None
        # Stream id
        self.streamId = None
    
    def __repr__(self):
        return ("<RTMPHeader channel=%r timer=%r size=%r type=%r (0x%02x) streamId=%r>"
                % (self.channel, self.timer, self.size, self.type, self.type or 0, self.streamId))

class SharedObjectTypeMapping:
    """Shared Object event types mapping"""
    def __init__(self):
        # Types map
        self.typeMap = ["SERVER_CONNECT"]
        
    def toType(self, rtmpType):
        """Convert byte value of RTMP marker to event type"""
        # Return corresponding Shared Object event type
        return self.typeMap[rtmpType]

    def toByte(self, type):
        """Convert SO event type to byte representation that RTMP uses"""
        # Return byte representation of given event type
        return 0x01
    
    def __repr__(self, type):
        """String representation of type"""
        return ("<SharedObjectTypeMapping type=%r>"
                % ("server connect"))

### RTMP Protocol Implementation

class RTMPProtocol(Protocol):
    
    def connectionMade(self):
        self.chunkSize = DEFAULT_CHUNK_SIZE
        self.buffer = None
        self.bytesNeeded = 0
        self.lastReadHeader = dict() # indexed on channel name
        self.incompletePackets = dict() # indexed on channel name
        self.state = States.HANDSHAKE
        if self.factory.mode == Modes.CLIENT:
            # begin handshake for client
            self.beginHandshake()

    def dataReceived(self, data):
        if self.factory.mode == Modes.SERVER:
            if self.state == States.HANDSHAKE:
                debug("Handshake 2nd phase")
                debug("handshake size: %d", len(data))
                assert data[0] == "\x03"
                client_hs = data[1:]
                #if not self._verifyHandshake(client_hs):
                #    raise Exception("Client handshake packet was invalid")
                self.transport.write("\x03")
                self._my_hs_uptime = uptime()
                self.transport.write(self._generateHandshake(self._my_hs_uptime))
                self.transport.write(client_hs)
                self.state = States.HANDSHAKE_VERIFY
            elif self.state == States.HANDSHAKE_VERIFY:
                debug("Handshake verify")
                debug("handshake size: %d", len(data))
                if not self._verifyHandshake(data[:HANDSHAKE_SIZE], self._my_hs_uptime):
                    raise Exception("Handshake verify failed")
                debug("server finished handshake")
                self.state = States.RTMP
                if len(data) > HANDSHAKE_SIZE:
                    self.dataReceived(data[HANDSHAKE_SIZE:]) # put any extra data back through
            else:
                # TODO: start waiting for a valid handshake during maxHandshakeTimeout
                # milliseconds.
                if self.buffer is None:
                    self.buffer = ByteStream(data)
                else:
                    self.buffer.write(data)
                while self.buffer and self.bytesNeeded < self.buffer.len:
                    self._parseRTMPPacket()
        else:
            if self.state == States.HANDSHAKE_VERIFY:
                debug("Handshake 3d phase")
                debug("handshake size: %d", len(data))
                assert data[0] == "\x03"
                server_hs = data[1:HANDSHAKE_SIZE+1]
                my_hs_back = data[HANDSHAKE_SIZE+1:2*HANDSHAKE_SIZE+1]
                rest = data[2*HANDSHAKE_SIZE+1:]
                #if not self._verifyHandshake(server_hs):
                #    raise Exception("Server handshake packet was invalid")
                if not self._verifyHandshake(my_hs_back, self._my_hs_uptime):
                    raise Exception("Handshake verify failed")
                self.transport.write(server_hs)
                debug("client finished handshake")
                self.state = States.RTMP
                assert len(rest) == 0
                #if len(rest):
                #    self.dataReceived(data) # put the remaining data back through here
            else:
                if self.buffer is None:
                    self.buffer = ByteStream(data)
                else:
                    self.buffer.write(data)
                while self.buffer and self.bytesNeeded < self.buffer.len:
                    self._parseRTMPPacket()


    def beginHandshake(self):
        debug("Handshake 1st phase")
        # the first part of the handshake is a 0x03 byte,
        self.transport.write("\x03")
        self._my_hs_uptime = uptime()
        # followed by 1536 bytes (uptime)
        self.transport.write(self._generateHandshake(self._my_hs_uptime))
        self.state = States.HANDSHAKE_VERIFY

    def _generateHandshake(self, uptime):
        # This is according to
        # http://www.mail-archive.com/red5@osflash.org/msg04906.html
        # However, Adobe Flash Player is doing things differently since
        # version 9,0,28,0 at least.
        x = uptime
        handshake = struct.pack("!LL", x, 0)
        for i in xrange(0, (HANDSHAKE_SIZE - 8)/2):
            x = (x * 0xb8cd75 + 1) & 0xff
            handshake += struct.pack("!H", x << 8)
        return handshake

    def _verifyHandshake(self, handshake, expected_uptime=None):
        """Check if the handshake reply received from a client contains valid data."""
        data = struct.unpack("!LL%dH" % ((HANDSHAKE_SIZE - 8)/2), handshake)
        if expected_uptime is not None and expected_uptime != data[0]:
            return False
        if data[1] != 0:
            return False
        x = data[0]
        for y in data[2:]:
            x = (x * 0xb8cd75 + 1) & 0xff
            if x != (y >> 8):
                return False
        return True

    def waitForHandshake(self):
        """Wait for a valid handshake and disconnect the client if none is received."""
        debug("waitForHandshake")
        # Client didn't send a valid handshake, disconnect.
        # onInactive()
        
    def _parseRTMPPacket(self):
        """Decodes next RTMP packet from self.buffer and dispatches it
        to the appropriate handler method. Replaces the buffer
        with a new one without the bytes that were parsed. If not enough
        bytes are available it sets self.bytesNeeded appropriately.
        
        This method will always exit ensuring that self.buffer is either None
        or positioned at the end.
        """
        if self.buffer is None or self.bytesNeeded > self.buffer.len:
            raise Exception("_parseRTMPPacket called without enough data in buffer")
        
        buf = self.buffer
        buf.seek(0)
        
        try:
            hdr = buf.read_uchar()
        except EOFError:
            self.bytesNeeded = 1
            # Buffer is empty so we don't need to seek
            return
        
        if hdr & 0x3f == 0:
            # Two byte header
            if buf.remaining() < 2:
                self.bytesNeeded = 2
                buf.seek(buf.len)
                return
            buf.seek(0)
            hdr = buf.read_ushort()
            hdrSizeSel = hdr >> 14
            channel = 64 + hdr & 0xff
        elif hdr & 0x3f == 1:
            # Three byte header
            if buf.remaining() < 3:
                self.bytesNeeded = 3
                buf.seek(buf.len)
                return
            buf.seek(0)
            hdr = struct.unpack("!L", "\x00" + buf.read(3))[0]
            hdrSizeSel = hdr >> 22
            channel = 64 + ((hdr >> 8) & 0xff) + ((hdr & 0xff) << 8)
        else:
            # Single byte header
            hdrSizeSel = hdr >> 6
            channel = hdr & 0x3f
        
        if hdrSizeSel == 0 and buf.remaining() < 12:
                self.bytesNeeded = 12
                buf.seek(buf.len)
                return
        elif hdrSizeSel == 1 and buf.remaining() < 8:
                self.bytesNeeded = 8
                buf.seek(buf.len)
                return
        elif hdrSizeSel == 2 and buf.remaining() < 4:
                self.bytesNeeded = 4
                buf.seek(buf.len)
                return
        
        header = RTMPHeader(channel)
        
        if hdrSizeSel != 0:
            lastHeader = self.lastReadHeader[channel]

        if hdrSizeSel < 3:
            header.timer = struct.unpack("!L", "\x00" + buf.read(3))[0]
        else:
            header.timer = lastHeader.timer
        
        if hdrSizeSel < 2:
            header.size = struct.unpack("!L", "\x00" + buf.read(3))[0]
            header.type = buf.read_uchar()
        else:
            header.size = lastHeader.size
            header.type = lastHeader.type
        
        if hdrSizeSel < 1:
            header.streamId = buf.read_ulong()
        else:
            header.streamId = lastHeader.streamId
        
        # see if we are continuing an incomplete packet and get the contents
        data = self.incompletePackets.get(channel, "")
        
        # see if we have enough data
        add = header.timer == 0xffffff and 4 or 0
        readAmount = min(header.size - (len(data) + add), self.chunkSize)
        if buf.remaining() < readAmount:
            self.bytesNeeded = buf.tell() + readAmount
            buf.seek(buf.len)
            return
        
        # Here we have made sure we have enough data. Go ahead and
        # read the packet, but first save the header for following packets.
        self.lastReadHeader[channel] = header
        
        data += buf.read(readAmount)
        
        # If there is still data left in the buffer, make a new one
        # with it
        if not buf.at_eof():
            self.buffer = ByteStream(buf.read())
            self.buffer.seek(self.buffer.len)
        else:
            self.buffer = None
        
        # Are we done yet?
        if len(data) < header.size + add:
            debug("RTMP packet not complete (%d of %d received)", len(data), header.size + add)
            self.incompletePackets[channel] = data
            return
        
        # We're done - i.e. we have a whole packet. Decode and dispatch it.
        self._decodeAndDispatchPacket(header, data)
        if channel in self.incompletePackets:
            del self.incompletePackets[channel]
    
    def _decodeAndDispatchPacket(self, header, data):
        """Decodes RTMP message event"""
        debug("received RTMP packet: %r", header)
        debug("packet data:\n%s", hexdump(data))
        if header.timer == 0xffffff:
            # TODO: Skip first four bytes
            unknown = data;
        headerDataType = header.type
        if headerDataType == RTMPTypes.CHUNK_SIZE:
            message = self.decodeChunkSize(data)
        elif headerDataType == RTMPTypes.INVOKE:
            message = self.decodeInvoke(data, self.state)
        elif headerDataType == RTMPTypes.NOTIFY:
            if header.streamId == 0:
                message = self.decodeNotify(data, header, self.state)
            else:
                message = self.decodeStreamMetadata(data)
        elif headerDataType == RTMPTypes.PING:
            message = decodeBytesRead(data)
        elif headerDataType == RTMPTypes.AUDIO_DATA:
            message = decodeAudioData(data)
        elif headerDataType == RTMPTypes.VIDEO_DATA:
            message = decodeVideoData(data)
        elif headerDataType == RTMPTypes.FLEX_SHARED_OBJECT:
            message = decodeFlexSharedObject(data, self.state)
        elif headerDataType == RTMPTypes.SO:
            message = decodeSharedObject(data, self.state)
        elif headerDataType == RTMPTypes.SERVER_BW:
            message = decodeServerBW(data)
        elif headerDataType == RTMPTypes.CLIENT_BW:
            message = decodeClientBW(data)
        elif headerDataType == RTMPTypes.FLEX_MESSAGE:
            message = decodeFlexMessage(data, self.state)
        else:
	    message = decodeUnknown(header.type, data)
        # message.setHeader(header)
        # message.setTimestamp(header.timer)
        # return message;
        
    def decodeChunkSize(self, data):
        # TODO
        return data;

    def decodeInvoke(self, data, state):
        # TODO
        return state;

    def decodeNotify(self, data, header, state):
        # TODO
        return data;
    
    def decodeStreamMetadata(self, data):
        # TODO
        return data;

    def decodeBytesRead(self, data):
        # TODO
        return data;

    def decodeAudioData(self, data):
        # TODO
        return data;

    def decodeVideoData(self, data):
        # TODO
        return data;

    def decodeFlexSharedObject(self, data, state):
        # TODO
        return data;

    def decodeSharedObject(self, data, state):
        # TODO
        return data;

    def decodeServerBW(self, data):
        # TODO
        return data;
    
    def decodeClientBW(self, data):
        # TODO
        return data;

    def decodeFlexMessage(self, data, state):
        # TODO
        return data;

    def decodeUnknown(self, headerType, data):
        # TODO
        warning("Unknown object type: %s", headerType)
        return data;
    
class RTMPServerFactory(protocol.ServerFactory):
    protocol = RTMPProtocol
    mode = Modes.SERVER

class RTMPClientFactory(protocol.ClientFactory):
    protocol = RTMPProtocol
    mode = Modes.CLIENT
     
def main(mode, server='localhost'):

    # initialize the uptime
    uptime()

    logging.basicConfig(level=logging.DEBUG,
            format="%(asctime)s %(levelname)s %(message)s")
    port = 1935
    if mode == "server":
        reactor.listenTCP(port, RTMPServerFactory())
        print 'Twisted RTMP server started on port %s.' % port
        print 60 * '='
        reactor.run()
        print 'Twisted RTMP server stopped.'
        return 0
    elif mode == "client":
        f = RTMPClientFactory()
        reactor.connectTCP(server, port, f)
        reactor.run()
        return 0

if __name__ == '__main__':
    import sys
    sys.exit(main(*(sys.argv[1:])))
