package com.collab.twisted.samples.rtmpyapp
{
	import flash.system.Capabilities;
	
	import mx.collections.ArrayCollection;
	import mx.controls.TextInput;
	import mx.core.WindowedApplication;
	
	/**
	 * Runs 8 RTMP port tests.
	 * 
	 * @author Thijs Triemstra
	*/	
	public class Main extends WindowedApplication
	{
		private static const  rtmp : String = "rtmp";
		private static const rtmpt : String = "rtmpt";
		
		[Bindable]
		public var flashVersion : String;
		
		[Bindable]
		public var testResults : ArrayCollection;
		
		public var hostname : String;
		
		public var application : String;
		
		public var host_txt : TextInput;
		
		public var app_txt : TextInput;
		
		/**
		 * 
		 */				
		public function Main() : void
		{
			var platformVersion : String = Capabilities.version.substr( String( Capabilities.version ).lastIndexOf(" ") + 1 );
			var manufacturer : String = Capabilities.manufacturer;
			// Get Flash Player version info.
			flashVersion = "FP " + platformVersion;
			//
			if ( Capabilities.isDebugger ) 
			{
				// Add debugger info.
				flashVersion += " (debug)";
			}
		}
		
		/**
		 * Start the RTMP port tests.
		 */		
		public function runTests() : void
		{
			hostname = host_txt.text;
			application = app_txt.text;
			// Create 8 tests that automatically connect and disconnect with the RTMP server.
			testResults = new ArrayCollection( [ new PortTest( rtmp, 	hostname, 	"", 		application ),
												 new PortTest( rtmp, 	hostname, 	"80", 		application ),
												 new PortTest( rtmp, 	hostname, 	"443", 		application ),
												 new PortTest( rtmp, 	hostname, 	"1935", 	application ),
												 new PortTest( rtmpt, 	hostname, 	"",			application ),
												 new PortTest( rtmpt, 	hostname, 	"80", 		application ),
												 new PortTest( rtmpt, 	hostname, 	"443", 		application ),
												 new PortTest( rtmpt, 	hostname, 	"1935", 	application ) ] );
		}
	}
}
