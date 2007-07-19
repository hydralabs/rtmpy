import struct
import time, os
from twisted.internet import reactor, protocol
from twisted.python import log, logfile

import rtmpy.util
from rtmpy.util import ByteStream, hexdump, Enum, uptime
from rtmpy import amf
from statuscodes import StatusCodes

Modes = Enum('SERVER', 'CLIENT')
States = Enum('CONNECT', 'HANDSHAKE', 'HANDSHAKE_VERIFY', 'CONNECTED', 'ERROR', 'DISCONNECTED')

class Constants:
    """AMF and RTMP marker values constants"""
    maxHandshakeTimeout = 5000
    HANDSHAKE_SIZE = 1536
    DEFAULT_CHUNK_SIZE = 128
    
    CHUNK_SIZE  =               0x01
    # Unknown:                  0x02
    BYTES_READ  =               0x03
    PING        =               0x04
    SERVER_BW   =               0x05
    CLIENT_BW   =               0x06
    # Unknown:                  0x07
    AUDIO_DATA  =               0x08
    VIDEO_DATA  =               0x09
    # Unknown:                  0x0A ... 0x0F
    FLEX_SHARED_OBJECT =        0x10
    FLEX_MESSAGE =              0x11
    NOTIFY      =               0x12
    STREAM_METADATA =           0x12
    SO          =               0x13
    INVOKE      =               0x14
    HEADER_NEW =                0x00
    SAME_SOURCE =               0x01
    HEADER_TIMER_CHANGE =       0x02
    HEADER_CONTINUE =           0x03
    CLIENT_UPDATE_DATA =        0x04
    CLIENT_UPDATE_ATTRIBUTE =   0x05
    CLIENT_SEND_MESSAGE =       0x06
    CLIENT_STATUS =             0x07
    CLIENT_CLEAR_DATA =         0x08
    CLIENT_DELETE_DATA =        0x09
    CLIENT_INITIAL_DATA =       0x0B
    SO_CONNECT =                0x01
    SO_DISCONNECT =             0x02
    SET_ATTRIBUTE =             0x03
    SEND_MESSAGE =              0x06
    DELETE_ATTRIBUTE =          0x0A
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
    def __init__(self, channel, timer=0, size=None, type=None, streamId=0):
        self.channel = channel
        self.timer = timer
        self.size = size
        self.type = type
        self.streamId = streamId
    
    def __repr__(self):
        return ("<RTMPHeader channel=%r timer=%r size=%r type=%r (0x%02x) streamId=%r>"
                % (self.channel, self.timer, self.size, self.type, self.type or 0, self.streamId))

class RTMPPacket:
    """ RTMP packet. Consists of packet header, data and event context."""
    def __init__(self, header, data, message=None):
        self.header = header
        self.data = data
        self.message = message
    
    def __repr__(self):
        return ("<RTMPPacket message=%r header=%r>"
                % (self.message, self.header))
    
class RTMPProtocol(protocol.Protocol):

    def __init__(self):
        self.chunkSize = Constants.DEFAULT_CHUNK_SIZE
        self.handShake = Constants.HANDSHAKE_SIZE
        self.mode = Modes.SERVER
        self.state = States.CONNECT
        # initialize the uptime
        uptime()
                
    def connectionMade(self):
        self.input = None
        self.output = None
        self.bytesNeeded = 0
        self.lastReadHeader = dict() # indexed on channel name
        self.incompletePackets = dict() # indexed on channel name
        self.state = States.HANDSHAKE
        self.mode = self.factory.mode
        log.msg("Client connecting: %s" % (self.transport.getPeer()))
        if self.mode == Modes.CLIENT:
            # begin handshake for client
            self.beginHandshake()

    def connectionLost(self, reason):
        log.msg("Connection with client %s closed." % self.transport.getPeer())
        
    def dataReceived(self, data):
        if self.mode == Modes.SERVER:
            if self.state == States.HANDSHAKE:
                print "Handshake 2nd phase..."
                print "Handshake size: %d" % len(data)
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
                print "Handshake verify..."
                print "Handshake size: %d" % len(data)
                if not self._verifyHandshake(data[:self.handShake], self._my_hs_uptime):
                    raise Exception("Handshake verify failed")
                print "Server finished handshake."
                self.state = States.CONNECTED
                if len(data) > self.handShake:
                    self.dataReceived(data[self.handShake:]) # put any extra data back through
            else:
                # TODO: start waiting for a valid handshake during maxHandshakeTimeout
                # milliseconds.
                if self.input is None:
                    self.input = ByteStream(data)
                else:
                    self.input.write(data)
                while self.input and self.bytesNeeded < self.input.len:
                    self._parseRTMPPacket()
        else:
            if self.state == States.HANDSHAKE_VERIFY:
                print "Handshake 3d phase..."
                print "Handshake size: %d" % len(data)
                assert data[0] == "\x03"
                server_hs = data[1:self.handShake+1]
                my_hs_back = data[self.handShake+1:2*self.handShake+1]
                rest = data[2*self.handShake+1:]
                #if not self._verifyHandshake(server_hs):
                #    raise Exception("Server handshake packet was invalid")
                if not self._verifyHandshake(my_hs_back, self._my_hs_uptime):
                    raise Exception("Handshake verify failed")
                self.transport.write(server_hs)
                print "Client finished handshake."
                self.state = States.CONNECTED
                assert len(rest) == 0
                #if len(rest):
                #    self.dataReceived(data) # put the remaining data back through here
            else:
                if self.input is None:
                    self.input = ByteStream(data)
                else:
                    self.input.write(data)
                while self.input and self.bytesNeeded < self.input.len:
                    self._parseRTMPPacket()
                    
    def beginHandshake(self):
        print "Handshake 1st phase..."
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
        for i in xrange(0, (self.handShake - 8)/2):
            x = (x * 0xb8cd75 + 1) & 0xff
            handshake += struct.pack("!H", x << 8)
        return handshake

    def _verifyHandshake(self, handshake, expected_uptime=None):
        """Check if the handshake reply received from a client contains valid data."""
        data = struct.unpack("!LL%dH" % ((self.handShake - 8)/2), handshake)
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
        print "Wait for handshake..."
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
        if self.input is None or self.bytesNeeded > self.input.len:
            raise Exception("_parseRTMPPacket called without enough data in buffer")
        
        buf = self.input
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
            self.input = ByteStream(buf.read())
            self.input.seek(self.input.len)
        else:
            self.input = None
        
        # Are we done yet?
        if len(data) < header.size + add:
            print "RTMP packet not complete (%d of %d received)" % (len(data), header.size + add)
            self.incompletePackets[channel] = data
            return
        
        packet = RTMPPacket(header, data)
        
        # We're done - i.e. we have a whole packet. Decode and dispatch it.
        self._decodeAndDispatchPacket(packet)
        if channel in self.incompletePackets:
            del self.incompletePackets[channel]
        
    def _decodeAndDispatchPacket(self, packet):
        """Decodes RTMP message event"""
        packetData = packet.data
        packetHeader = packet.header
        headerDataType = packetHeader.type
        
        if packetHeader.timer == 0xffffff:
            # TODO: Skip first four bytes
            unknown = packetData
            
        if headerDataType == Constants.INVOKE:
            input = ByteStream(packetData)
            invoke = Notify()
            amfreader = amf.AMF0Parser(input)
            invoke.name = amfreader.readElement()
            invoke.id = amfreader.readElement()
            invoke.argv = []
            while input.peek() != None:
                invoke.argv.append(amfreader.readElement())
            packet.message = invoke
            log.msg("Received RTMP packet: %r" % packet.header)
            actionType = invoke.name

            if actionType == Constants.ACTION_CONNECT:
                # Connect client
                response = Notify()
                response.id = invoke.id
                response.name = "_result"
                response.argv = [None,
                    StatusObject("status",
                                 StatusCodes.NC_CONNECT_SUCCESS,
                                 "Connection succeeded.")]
  
                self._writeRTMPPacket(packetHeader.channel, response)
                        
            elif headerDataType == Constants.PING:
                raise NotImplementedError

            else:
                raise Exception ("Unknown action type: %s" % actionType)
            
        else:
            raise Exception ("Unknown header type: %s" % headerDataType)
        
        """     
        elif headerDataType == Constants.CHUNK_SIZE:
               
        elif headerDataType == Constants.NOTIFY:
            if packetHeader.streamId == 0:
                
            else:
               
        
        elif headerDataType == Constants.AUDIO_DATA:
            #
        elif headerDataType == Constants.VIDEO_DATA:
            #
        elif headerDataType == Constants.FLEX_SHARED_OBJECT:
            #
        elif headerDataType == Constants.SO:
            #  
        elif headerDataType == Constants.SERVER_BW:
            #
        elif headerDataType == Constants.CLIENT_BW:
            #
        elif headerDataType == Constants.FLEX_MESSAGE:
            #
        
        """

    def _writeRTMPPacket(self, channel, notify, streamId=0):
        stream = ByteStream()
        # stream.writeElement(notify.name)
        # stream.writeElement(notify.id)
        # for arg in notify.argv:
            # stream.writeElement(arg)
        header = RTMPHeader(channel, 0, stream.len, Constants.INVOKE, 0)
        packet = RTMPPacket(header, stream, notify)
        log.msg("Sending RTMP packet: %r" % packet.header)
        
class StatusObject:
    """ Status object that is sent to client with every status event."""
    def __init__(self, code, level, description=None):
        self.code = code
        self.level = level
        self.description = description
    
    def __repr__(self):
        return ("<StatusObject code=%r level=%r description=%r>"
                % (self.code, self.level, self.description))

class Notify:
    """ Stream notification event."""
    def __init__(self):
        self.name = None
        self.id = None
        self.argv = None
    
    def __repr__(self):
        return ("<Notify name=%r id=%r argv=%r>"
                % (self.name, self.id, self.argv))

class Ping:
    """ Ping event, actually combination of different events"""
    def __init__(self):
        self.value1 = None
        self.value2 = None
        self.value3 = None
        self.value4 = None
    
    def __repr__(self):
        return ("<Ping value1=%r value2=%r value3=%r value4=%r>"
                % (self.value1, self.value2, self.value3, self.value4))
    
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
