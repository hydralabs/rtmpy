# -*- encoding: utf8 -*-
#
# AMF parser
# sources:
#   http://www.vanrijkom.org/archives/2005/06/amf_format.html
#   http://osflash.org/documentation/amf/astypes

import struct
import datetime

try:
    import xml.etree.ElementTree as ET
except ImportError:
    try:
        import cElementTree as ET
    except ImportError:
        import elementtree.ElementTree as ET

import util
from util import ByteStream

class AMF0Types:
    NUMBER      = 0x00
    BOOL        = 0x01
    STRING      = 0x02
    OBJECT      = 0x03
    MOVIECLIP   = 0x04
    NULL        = 0x05
    UNDEFINED   = 0x06
    REFERENCE   = 0x07
    MIXEDARRAY  = 0x08
    OBJECTTERM  = 0x09
    ARRAY       = 0x0a
    DATE        = 0x0b
    LONGSTRING  = 0x0c
    UNSUPPORTED = 0x0e
    XML         = 0x0f
    TYPEDOBJECT = 0x10
    AMF3        = 0x11

class AMF0Parser:

    def __init__(self, data):
        self.obj_refs = list()
        self.input = ByteStream(data)

    def parse(self):
        # TODO: remove this?
        elements = []
        while self.input.peek() is not None:
            elements.append(self.readElement())
        return elements
    
    def readElement(self):
        type = self.input.read_uchar()
        if type == AMF0Types.NUMBER:
            return self.input.read_double()

        elif type == AMF0Types.BOOL:
            return bool(self.input.read_uchar())

        elif type == AMF0Types.STRING:
            return self.readString()

        elif type == AMF0Types.OBJECT:
            return self.readObject()

        elif type == AMF0Types.MOVIECLIP:
            raise NotImplementedError()

        elif type == AMF0Types.NULL:
            return None

        elif type == AMF0Types.UNDEFINED:
            # TODO: do we need a special value here?
            return None

        elif type == AMF0Types.REFERENCE:
            return self.readReference()

        elif type == AMF0Types.MIXEDARRAY:
            len = self.input.read_ulong()
            obj = self.readObject()
            for key in obj.keys():
                try:
                    ikey = int(key)
                    obj[ikey] = obj[key]
                    del obj[key]
                except ValueError:
                    pass
            return obj

        elif type == AMF0Types.ARRAY:
            len = self.input.read_ulong()
            obj = []
            self.obj_refs.append(obj)
            obj.extend(self.readElement() for i in xrange(len))
            return obj

        elif type == AMF0Types.DATE:
            return readDate()

        elif type == AMF0Types.LONGSTRING:
            return self.readLongString()

        elif type == AMF0Types.UNSUPPORTED:
            # TODO: do we need a special value?
            return None

        elif type == AMF0Types.XML:
            return self.readXML()

        elif type == AMF0Types.TYPEDOBJECT:
            classname = readString()
            obj = readObject()
            # TODO do some class mapping?
            return obj

        elif type == AMF0Types.AMF3:
            raise NotImplementedError()

        else:
            raise ValueError("Unknown AMF0 type 0x%02x at %d" % (type, self.input.tell()-1))

    def readString(self):
        len = self.input.read_ushort()
        return self.input.read_utf8_string(len)

    def readObject(self):
        obj = dict()
        self.obj_refs.append(obj)
        key = self.readString()
        while self.input.peek() != chr(AMF0Types.OBJECTTERM):
            obj[key] = self.readElement()
            key = self.readString()
        self.input.read(1) # discard the end marker (AMF0Types.OBJECTTERM = 0x09)
        return obj
    
    def readReference(self):
        idx = self.input.read_ushort()
        return self.obj_refs[idx]

    def readDate(self):
        ms = self.input.read_double()
        tz = self.input.read_short()
        class TZ(datetime.tzinfo):
            def utcoffset(self, dt):
                return datetime.timedelta(minutes=tz)
            def dst(self,dt):
                return None
            def tzname(self,dt):
                return None
        return datetime.datetime.fromtimestamp(ms/1000.0, TZ())
    
    def readLongString(self):
        len = self.input.read_ulong()
        return self.input.read_utf8_string(len)

    def readXML(self):
        data = readLongString()
        return ET.fromstring(data)

class AMF3Types:
    UNDEFINED       = 0x00
    NULL            = 0x01
    BOOL_FALSE      = 0x02
    BOOL_TRUE       = 0x03
    INTEGER         = 0x04
    NUMBER          = 0x05
    STRING          = 0x06
    XML             = 0x07
    DATE            = 0x08
    ARRAY           = 0x09
    OBJECT          = 0x0a
    XMLSTRING       = 0x0b
    BYTEARRAY       = 0x0c

class AMF3Parser:

    def __init__(self, data):
        self.obj_refs = list()
        self.str_refs = list()
        self.class_refs = list()
        self.input = ByteStream(data)

    def readElement(self):
        type = self.input.read_uchar()
        if type == AMF3Types.UNDEFINED:
            return None
        
        if type == AMF3Types.NULL:
            return None
        
        if type == AMF3Types.BOOL_FALSE:
            return False
        
        if type == AMF3Types.BOOL_TRUE:
            return True
        
        if type == AMF3Types.INTEGER:
            return self.readInteger()
        
        if type == AMF3Types.NUMBER:
            return self.input.read_double()
        
        if type == AMF3Types.STRING:
            return self.readString()
        
        if type == AMF3Types.XML:
            return self.readXML()
        
        if type == AMF3Types.DATE:
            return self.readDate()
        
        if type == AMF3Types.ARRAY:
            return self.readArray()
        
        if type == AMF3Types.OBJECT:
            raise NotImplementedError()
        
        if type == AMF3Types.XMLSTRING:
            raise NotImplementedError()
        
        if type == AMF3Types.BYTEARRAY:
            raise NotImplementedError()
        
        else:
            raise ValueError("Unknown AMF3 type 0x%02x at %d" % (type, self.input.tell()-1))
    
    def readInteger(self):
        n = 0
        b = self.input.read_uchar()
        result = 0
        
        while b & 0x80 and n < 3:
            result <<= 7
            result |= b & 0x7f
            n += 1
        if n < 3:
            result <<= 7
            result |= b
        else:
            result <<= 8
            result |= b
        if result & 0x10000000:
            result |= 0xe0000000
        
        return result
    
    def readString(self, use_references=True):
        length = self.input.read_ushort()
        if use_references and length & 0x01 == 0:
            return self.str_refs[length >> 1]
        
        length >>= 1
        buf = self.input.read(length)
        try:
            # Try decoding as regular utf8 first since that will
            # cover most cases and is more efficient.
            # XXX: I'm not sure if it's ok though.. will it always raise exception?
            result = unicode(buf, "utf8")
        except UnicodeDecodeError:
            result = util.decode_utf8_modified(buf)
        
        if use_references and len(result) != 0:
            self.str_refs.append(result)
        
        return result
    
    def readXML(self):
        data = self.readString(False)
        return ET.fromstring(data)
    
    def readDate(self):
        ref = self.input.read_ushort()
        if ref & 0x01 == 0:
            return self.obj_refs[ref >> 1]
        ms = self.input.read_double()
        result = datetime.datetime.fromtimestamp(ms/1000.0)
        self.obj_refs.append(result)
        return result
    
    def readArray(self):
        size = self.input.read_ushort()
        if size & 0x01 == 0:
            return self.obj_refs[size >> 1]
        size >>= 1
        key = self.readString()
        if key == "":
            # integer indexes only -> python list
            result = []
            self.obj_refs.append(result)
            for i in xrange(size):
                el = self.readElement()
                result.append(el)
        else:
            # key,value pairs -> python dict
            result = {}
            self.obj_refs.append(result)
            while key != "":
                el = self.readElement()
                result[key] = el
                key = self.readString()
            for i in xrange(size):
                el = self.readElement()
                result[i] = el
        
        return result
    
    def readObject(self):
        pass # TODO

class AMFMessageParser:
    
    def __init__(self, data):
        self.input = ByteStream(data)
    
    def parse(self):
        msg = AMFMessage()
        
        msg.amfVersion = self.input.read_uchar()
        if msg.amfVersion == 0:
            parser_class = AMF0Parser
        elif msg.amfVersion == 3:
            parser_class = AMF3Parser
        else:
            raise Exception("Invalid AMF version")
        
        msg.clientType = self.input.read_uchar()
        
        header_count = self.input.read_short()
        for i in range(header_count):
            header = AMFMessageHeader()
            name_len = self.input.read_ushort()
            header.name = self.input.read_utf8_string(name_len)
            header.required = bool(self.input.read_uchar())
            msg.length = self.input.read_ulong()
            header.data = parser_class(self.input.read(msg.length)).readElement()
            msg.headers.append(header)
        
        bodies_count = self.input.read_short()
        for i in range(bodies_count):
            body = AMFMessageBody()
            target_len = self.input.read_ushort()
            body.target = self.input.read_utf8_string(target_len)
            response_len = self.input.read_ushort()
            body.response = self.input.read_utf8_string(response_len)
            body.length = self.input.read_ulong()
            body.data = parser_class(self.input.read(body.length)).readElement()
            msg.bodies.append(body)
        
        return msg

class AMFMessage:
    def __init__(self):
        self.amfVersion = None
        self.clientType = None
        self.headers = []
        self.bodies = []
    
    def __repr__(self):
        r = "<AMFMessage\n"
        for h in self.headers:
            r += "   " + repr(h) + "\n"
        for b in self.bodies:
            r += "   " + repr(b) + "\n"
        r += ">"
        return r

class AMFMessageHeader:
    def __init__(self):
        self.name = None
        self.required = None
        self.length = None
        self.data = None
    
    def __repr__(self):
        return "<AMFMessageHeader %s = %r>" % (self.name, self.data)

class AMFMessageBody:
    def __init__(self):
        self.target = None
        self.response = None
        self.length = None
        self.data = None

    def __repr__(self):
        return "<AMFMessageBody %s = %r>" % (self.target, self.data)
    
if __name__ == "__main__":
    import sys, glob
    for arg in sys.argv[1:]:
        for fname in glob.glob(arg):
            f = file(fname, "r")
            data = f.read()
            f.close()
            p = AMFMessageParser(data)
            print "=" * 40
            print "Parsing", fname
            obj = p.parse()
            print repr(obj)
    