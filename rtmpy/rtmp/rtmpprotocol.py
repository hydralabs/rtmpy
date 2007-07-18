import struct
import logging, time, os
from logging import debug, info, warning
from twisted.internet import reactor, protocol

import util
from util import ByteStream, hexdump, Enum, uptime
from message.constants import Constants
from message.header import RTMPHeader
from message.packet import RTMPPacket
from event.notify import Notify
from status.statusobject import StatusObject
from status.statuscodes import StatusCodes
import amf

Modes = Enum('SERVER', 'CLIENT')
States = Enum('HANDSHAKE', 'HANDSHAKE_VERIFY', 'RTMP')

class RTMPProtocol(protocol.Protocol):

    def __init__(self):
        self.chunkSize = Constants.DEFAULT_CHUNK_SIZE
        self.handShake = Constants.HANDSHAKE_SIZE
        # initialize the uptime
        uptime()
                
    def connectionMade(self):
        self.input = None
        self.output = None
        self.bytesNeeded = 0
        self.lastReadHeader = dict() # indexed on channel name
        self.incompletePackets = dict() # indexed on channel name
        self.state = States.HANDSHAKE
        info("Client connecting to %s." % (self.transport.getPeer( ).host))
        if self.factory.mode == Modes.CLIENT:
            # begin handshake for client
            self.beginHandshake()

    def connectionLost(self, reason):
        info("Connection with %s closed." % self.transport.getPeer( ).host)
        
    def dataReceived(self, data):
        if self.factory.mode == Modes.SERVER:
            if self.state == States.HANDSHAKE:
                debug("Handshake 2nd phase")
                debug("Handshake size: %d", len(data))
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
                debug("Handshake size: %d", len(data))
                if not self._verifyHandshake(data[:self.handShake], self._my_hs_uptime):
                    raise Exception("Handshake verify failed")
                debug("Server finished handshake")
                self.state = States.RTMP
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
                debug("Handshake 3d phase")
                debug("Handshake size: %d", len(data))
                assert data[0] == "\x03"
                server_hs = data[1:self.handShake+1]
                my_hs_back = data[self.handShake+1:2*self.handShake+1]
                rest = data[2*self.handShake+1:]
                #if not self._verifyHandshake(server_hs):
                #    raise Exception("Server handshake packet was invalid")
                if not self._verifyHandshake(my_hs_back, self._my_hs_uptime):
                    raise Exception("Handshake verify failed")
                self.transport.write(server_hs)
                debug("Client finished handshake")
                self.state = States.RTMP
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
            debug("RTMP packet not complete (%d of %d received)", len(data), header.size + add)
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
            debug("Received RTMP packet: %r", packet)
            actionType = invoke.name
            debug(actionType)
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
        debug("Sending RTMP packet: %r", packet)
        
