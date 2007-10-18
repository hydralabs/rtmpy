package com.collab.twisted.samples.vo
{
	[RemoteClass(alias="com.collab.twisted.samples.UserVO")]
	
   	[Bindable]
	public class UserVO
	{
		public var id:Number;
		public var username:String;
		public var emailaddress:String;
	}
}
