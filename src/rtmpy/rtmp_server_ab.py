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

server_start_time = None

def uptime():
    """Returns uptime in milliseconds, starting at first call"""
    if not hasattr(uptime, "t0") is None:
        uptime.t0 = time.time()
    return int((time.time() - uptime.t0)*1000)

Modes = Enum('SERVER', 'CLIENT')
States = Enum('HANDSHAKE', 'HANDSHAKE_VERIFY', 'RTMP')

class RTMPTypes:
    CHUNK_SIZE  = 0x01
    BYTES_READ  = 0x03
    PING        = 0x04
    SERVER_BW   = 0x05
    CLIENT_BW   = 0x06
    AUDIO_DATA  = 0x08
    VIDEO_DATA  = 0x09
    NOTIFY      = 0x12
    SO          = 0x13
    INVOKE      = 0x14

class RTMPHeader:
    def __init__(self, channel):
        self.channel = channel
        self.timer = None
        self.size = None
        self.type = None
        self.streamId = None
    
    def __repr__(self):
        return ("<RTMPHeader channel=%r timer=%r size=%r type=%r (0x%02x) streamId=%r>"
                % (self.channel, self.timer, self.size, self.type, self.type or 0, self.streamId))

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
        self.transport.write("\x03")
        self._my_hs_uptime = uptime()
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
            if buf.remaining() < 2:
                self.bytesNeeded = 2
                buf.seek(buf.len)
                return
            buf.seek(0)
            hdr = buf.read_ushort()
            hdrSizeSel = hdr >> 14
            channel = 64 + hdr & 0xff
        elif hdr & 0x3f == 1:
            if buf.remaining() < 3:
                self.bytesNeeded = 3
                buf.seek(buf.len)
                return
            buf.seek(0)
            hdr = struct.unpack("!L", "\x00" + buf.read(3))[0]
            hdrSizeSel = hdr >> 22
            channel = 64 + ((hdr >> 8) & 0xff) + ((hdr & 0xff) << 8)
        else:
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
            debug("packet not complete (%d of %d received)", len(data), header.size + add)
            self.incompletePackets[channel] = data
            return
        
        # We're done - i.e. we have a whole packet. Decode and dispatch it.
        self._decodeAndDispatchPacket(header, data)
        if channel in self.incompletePackets:
            del self.incompletePackets[channel]
    
    def _decodeAndDispatchPacket(self, header, data):
        # TODO
        debug("received RTMP packet: %r", header)
        debug("packet data:\n%s", hexdump(data))


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
