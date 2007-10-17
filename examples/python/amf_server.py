# -*- encoding: utf8 -*-
#
# Copyright (c) 2007 The RTMPy Project. All rights reserved.
# 
# Arnar Birgisson
# Thijs Triemstra
# 
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

from twisted.web import http
from rtmpy.amf import Server, GeneralTypes

# Server port.
port = 8080
# Remoting gateway location.
gatewayLocation = '/gateway'

def renderHomePage(request):
    request.write("""
    <html>
    <head>
      <title>AMF Server Example</title>
    </head>
    <body>
        <h2>AMF Server Example</h2>
        <p>
          Simple AMF server example with <a href='http://dev.collab.com/rtmpy'>RTMPy</a>.<br/><br/>
          Gateway address: <a href='""" + gatewayLocation + "'>" + gatewayLocation + """</a>
        </p>
    </body>
    </html>""")

def remotingGateway(request):
    # Get header content type.
    contentType = request.getHeader('Content-Type')
    # Respond to AMF calls.
    if contentType == GeneralTypes.AMF_MIMETYPE:
        # Request data from the client.
        data = request.content.getvalue()
        # Init AMF server.
        amfServer = Server(data)
        # Loop through requests.
        for req in amfServer.getRequests():
            print "Request:", req
            # Send a new response.
            amfServer.setResponse(
                               # Connect the request to the response.
                               req.response, 
                               # Either REMOTING_RESULT or REMOTING_STATUS.
                               GeneralTypes.REMOTING_RESULT, 
                               # Any data structure, in this case we are echoing back the original data.
                               req.data) 
        # Add AMF header content type.
        request.setHeader('Content-Type', GeneralTypes.AMF_MIMETYPE)
        # Returns serialized AMF in a StringIO.
        response = amfServer.getResponse()
        # Write response data back to the client.
        request.write(response.getvalue())
    else:
        # Return blank HTML page for non-AMF calls.
        request.setHeader('Content-Type', 'text/html')
        
class handleHTTPRequest(http.Request):
    pageHandlers = {
        '/': renderHomePage,
        gatewayLocation: remotingGateway,
    }
    
    def process(self):
        # Use the path property to find out which path is being requested.
        if self.pageHandlers.has_key(self.path):
            handler = self.pageHandlers[self.path]
            # Respond to page requests.  
            handler(self)
        else:
            # HTTP404 - Page not found.
            self.setResponseCode(http.NOT_FOUND)
            self.write("""<html><head><title>Page Not Found</title></head>
                    <h1>404</h1><p>Page not found</p></html>""")
        self.finish()

class MyHttp(http.HTTPChannel):
    requestFactory = handleHTTPRequest

class MyHttpFactory(http.HTTPFactory):
    protocol = MyHttp

if __name__ == "__main__":
    from twisted.internet import reactor
    # Start AMF server.
    reactor.listenTCP(port, MyHttpFactory())
    print "Started RTMPy AMF server on port " + str(port) + "."
    reactor.run()
    print "\nServer stopped."
