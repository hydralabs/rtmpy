# -*- encoding: utf8 -*-
#
# Class for AMF and RTMP marker values constants

class Constants:
    # Size of initial handshake between client and server
    HANDSHAKE_SIZE = 1536

    # Default size of RTMP chunks
    DEFAULT_CHUNK_SIZE = 128

    # Max. time in milliseconds to wait for a valid handshake.
    maxHandshakeTimeout = 5000
    
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
    
