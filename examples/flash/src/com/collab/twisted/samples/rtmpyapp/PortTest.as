package com.collab.twisted.samples.rtmpyapp
{
	import flash.events.NetStatusEvent;
	import flash.net.NetConnection;
	import flash.net.ObjectEncoding;
	
	[Bindable]
	/**
	 * Test RTMP port.
	 * 
	 * @author Thijs Triemstra
	 */	
	public class PortTest 
	{
		/**
		* Protocol name.
		*/		
		private var protocol : String;
		
		/**
		* Protocol name (uppercase).
		*/		
		public var protocolName : String;
		
		/**
		* RTMP hostname.
		*/		
		private var hostname : String;
		
		/**
		* RTMP port.
		*/		
		public var port : String;
		
		/**
		* RTMP port.
		*/		
		public var portName : String = "Default";
		
		/**
		* RTMP application.
		*/		
		private var application : String;

		/**
		* Base RTMP URI.
		*/		
		private var baseURI : String;
		
		/**
		* RTMP connection.
		*/		
		public var nc : NetConnection;
		
		/**
		* Connection status.
		*/		
		public var status : String;
		
		/**
		* Set default encoding to AMF0 so FMS also understands.
		*/		
		NetConnection.defaultObjectEncoding = ObjectEncoding.AMF0;
		
		/**
		 * Create new port test and connect to the RTMP server.
		 * 
		 * @param protocol
		 * @param hostname
		 * @param port
		 * @param application
		 */			
		public function PortTest( protocol : String = "",
								  hostname : String = "",
								  port : String = "",
								  application : String = "" ) 
		{
			this.protocol = protocol;
			this.protocolName = protocol.toUpperCase();
			this.hostname = hostname;
			this.application = application;
			if ( port.length > 0 )
			{
				this.portName = port;
				this.port = ":" + port;
			}
			else 
			{
				this.port = port;
			}
			// Construct URI.
			this.baseURI = this.protocol + "://" + this.hostname + this.port + "/" + this.application;
			//
			connect();
		}
		
		/**
		 * Start connection.
		 */		
		private function connect() : void
		{
			this.nc = new NetConnection();
			this.nc.client = this;
			this.nc.addEventListener( NetStatusEvent.NET_STATUS, netStatus );
			// connect to server
			try 
			{
				// Create connection with the server.
				this.nc.connect( this.baseURI );
				status = "Connecting...";
			}
			catch( e : ArgumentError ) 
			{
				// Invalid parameters.
				status = "ERROR: " + e.message;
			}	
		}
		
		/**
		 * Close connection.
		 */		
		public function close() : void
		{	
			// Remove listener.
			this.nc.removeEventListener( NetStatusEvent.NET_STATUS, netStatus );
			// Close the NetConnection.
			this.nc.close();
		}
			
		/**
		 * Catch NetStatusEvents.
		 * 
		 * @param event
		 */		
		protected function netStatus( event : NetStatusEvent ) : void 
		{
			var info : Object = event.info;
			var statusCode : String = info.code;
			//
			if ( statusCode == "NetConnection.Connect.Success" )
			{
				status = "SUCCESS";
			}
			else if ( statusCode == "NetConnection.Connect.Rejected" ||
				 	  statusCode == "NetConnection.Connect.Failed" || 
				 	  statusCode == "NetConnection.Connect.Closed" ) 
			{
				status = "FAILED";
			}
			// Close NetConnection.
			close();
		}
		
	}
}
