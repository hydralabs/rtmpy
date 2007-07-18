from twisted.web import http

"""
The http.Request class parses an incoming HTTP request and provides an
interface for working with the request and generating a response.
"""
class FlashRemotingGateway(http.Request):
    pages = {
        '/': '<h1>RTMPy Server</h1>Welcome!',
        '/test': '<h1>Test</h1>Test HTML page',
        '/gateway': '',
        }
    
    """
    The process method will be called after the request has been completely
    received. It is responsible for generating a response and then calling
    self.finish() to indicate that the response is complete.
    """
    def process(self):
        # Use the path property to find out which path is being requested.
        if self.pages.has_key(self.path):
            # Handle remoting.
            contentType = self.getHeader('Content-Type')
            if self.path == '/gateway' and contentType == 'application/x-amf':
                # Add AMF headers to the response.
                self.setHeader('Content-Type', contentType)
                # TODO: read and process AMF
            else:
                # Add text/html content-type header to the response.
                self.setHeader('Content-Type', 'text/html')
                # Use the write method to send back the response.
                self.write(self.pages[self.path])
        # Page not found.
        else:
            # Change the HTTP status code.
            self.setResponseCode(http.NOT_FOUND)
            self.write("<h1>Not Found</h1>Sorry, no such page.")
        #
        self.finish()
