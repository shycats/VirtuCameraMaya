#The MIT License (MIT)
#
#Copyright (c) 2019 Pablo J. Garcia Gonzalez
#
#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:
#
#The above copyright notice and this permission notice shall be included in all
#copies or substantial portions of the Software.
#
#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#SOFTWARE.

#------------------------------------------------------------------------------
# Acknowledgements:
#------------------------------------------------------------------------------
# * FFmpeg (https://www.ffmpeg.org):
#   This program optionally relies on FFmpeg's command line tool to do video 
#   streaming (although it can work without this feature).
#   License should be included along with this program. You can download 
#   FFmpeg's source code and build configuration from virtucamera.com
#   License: GPL
#
# * python-zeroconf 0.16 (https://github.com/jstasiak/python-zeroconf/tree/0.16):
#   This program relies on python-zeroconf for service announcement. 
#   Source code and license should be included along with this program.
#   License: LGPL
#
# * python-qrcode (https://github.com/lincolnloop/python-qrcode):
#   This program relies on python-qrcode for QR code generation.
#   Source code and license should be included along with this program.
#   License: MIT
#------------------------------------------------------------------------------

import thread, ctypes, socket, struct, subprocess, time, timeit, os, sys
import maya.api.OpenMaya as api
import maya.api.OpenMayaUI as apiUI
from maya import OpenMayaUI as v1apiUI
import maya.cmds as cmds
import maya.utils as utils

try:
    from PySide2 import QtGui, QtCore, QtWidgets
except ImportError:
    from PySide import QtGui, QtCore
    QtWidgets = QtGui

try:
    from shiboken2 import wrapInstance
except ImportError:
    from shiboken import wrapInstance

# Add vendor to sys.path, to correctly import third party modules
parent_dir = os.path.abspath(os.path.dirname(__file__))
vendor_dir = os.path.join(parent_dir, 'vendor')
if vendor_dir not in sys.path:
    sys.path.append(vendor_dir)

import zeroconf
import qrcode


class QtImageFactory(qrcode.image.base.BaseImage):
    def __init__(self, border, width, box_size):
        self.border = border
        self.width = width
        self.box_size = box_size
        size = (width + border * 2) * box_size
        self._image = QtGui.QImage(
            size, size, QtGui.QImage.Format_RGB16)
        self._image.fill(QtCore.Qt.white)

    def pixmap(self):
        return QtGui.QPixmap.fromImage(self._image)

    def drawrect(self, row, col):
        painter = QtGui.QPainter(self._image)
        painter.fillRect(
            (col + self.border) * self.box_size,
            (row + self.border) * self.box_size,
            self.box_size, self.box_size,
            QtCore.Qt.black)

    def save(self, stream, kind=None):
        pass

class VirtuCameraMaya(object):
    # Constants
    _SERVER_VERSION = (1,0,1)
    _SERVER_PLATFORM = 'Maya'   # Please, don't exceed 10 characters (for readability purposes)
    _ALPHA_BITRATE_RATIO = 0.2  # Factor of total bitrate used for Alpha
    _STREAM_WIDTH = 640         # Must be an even integer
    _STREAM_HEIGHT = 360        # Must be an even integer
    _DEFAULT_PORT = 23354       # TCP port used by default
    _ANNOUNCEMENT_INTERVAL = 10 # re-announce every 10 seconds
    _ZEROCONF_TYPE = '_virtucamera._tcp.local.'
    _CAMERA_KEY_ATTRS = ['.tx','.ty','.tz','.rx','.ry','.rz','.focalLength']

    def _command(tag):
        # UInt8 commands
        return struct.pack('<B', tag)

    # Communication Commands
    # ASK commands spect an answer from the server, but doesn't modify any server parameter.
    _CMD_ASK_SERVER_INFO            = _command(0)
    _CMD_ASK_SCENE_STATUS           = _command(1)
    _CMD_ASK_SCENE_CAMERAS          = _command(2)
    _CMD_ASK_CAMERA_MATRIX          = _command(3)
    _CMD_ASK_VIEWPORT_IMG           = _command(4)
    _CMD_ASK_PLAY_FPS               = _command(5)
    _CMD_ASK_CAMERA_HAS_KEYS        = _command(6)
    # SET commands acknowledge data read and sets parameters on the server.
    _CMD_SET_PLAYBACK_RANGE         = _command(50)
    _CMD_SET_CURRENT_TIME           = _command(51)
    _CMD_SET_CURRENT_CAMERA         = _command(52)
    _CMD_SET_CAMERA_MATRIX          = _command(53)
    _CMD_SET_CAMERA_MATRIX_AT_TIME  = _command(54)
    _CMD_SET_FOCAL_LENGTH           = _command(55)
    _CMD_SET_FOCAL_LENGTH_AT_TIME   = _command(56)
    _CMD_SET_CAMERA_ALL             = _command(57)
    _CMD_SET_CAMERA_ALL_AT_TIME     = _command(58)
    _CMD_SET_CAMERA_MATRIX_KEYS     = _command(59)
    _CMD_SET_CAMERA_FLEN_KEYS       = _command(60)
    # DO commands acknowledge data read and call actions.
    _CMD_DO_START_STREAMING         = _command(150)
    _CMD_DO_STOP_STREAMING          = _command(151)
    _CMD_DO_START_PLAYBACK          = _command(152)
    _CMD_DO_STOP_PLAYBACK           = _command(153)
    _CMD_DO_SWITCH_PLAYBACK         = _command(154)
    _CMD_DO_REMOVE_CAMERA_KEYS      = _command(155)
    _CMD_DO_CREATE_NEW_CAMERA       = _command(156)
    # ERR commands are sent to the client if something went wrong
    _CMD_ERR_MISSING_CAMERA         = _command(200)
    _CMD_ERR_NOT_STREAMING          = _command(201)
    _CMD_ERR_FFMPEG                 = _command(202)

    _MAYA_FPS_PRESETS = {
        'game': 15.0, 
        'film': 24.0,
        'pal': 25.0,
        'ntsc': 30.0,
        'show': 48.0,
        'palf': 50.0,
        'ntscf': 60.0,
        'millisec': 1000.0,
        'sec': 1.0,
        'min': 1.0/60.0,
        'hour': 1.0/3600.0
    }

    # https://github.com/abstractfactory/maya-capture ##################
    def _in_standalone(self):
        return not hasattr(cmds, "about") or cmds.about(batch=True)

    def _get_screen_size(self):
        """Return available screen size without space occupied by taskbar"""
        if self._in_standalone():
            return [0, 0]

        rect = QtWidgets.QDesktopWidget().screenGeometry(-1)
        return [rect.width(), rect.height()]
    ####################################################################

    def _update_ui_layout(self):
        cmds.formLayout(self._ui_layout, edit=True,
            attachForm=[(self._ui_tx_port, 'top', 10), (self._ui_tx_port, 'left', 5), (self._ui_int_port, 'top', 6), (self._ui_bt_serve, 'top', 5), (self._ui_tx_help, 'top', 10), (self._ui_tx_help, 'right', 5), (self._ui_view, 'left', 0)],
            attachControl=[(self._ui_int_port, 'left', 1, self._ui_tx_port), (self._ui_bt_serve, 'left', 5, self._ui_int_port), (self._ui_tx_help, 'left', 5, self._ui_bt_serve), (self._ui_view, 'top', 5, self._ui_bt_serve)],
            attachNone=[(self._ui_int_port, 'bottom'), (self._ui_int_port, 'right'), (self._ui_bt_serve, 'bottom'), (self._ui_bt_serve, 'right'), (self._ui_tx_help, 'bottom'), (self._ui_view, 'right'), (self._ui_view, 'bottom')])

    def _start_serving(self, caller=None):
        port = cmds.intField(self._ui_int_port, q=True, value=True)
        self._serve(port)

    def _stop_serving(self, caller=None):
        self._stop()

    def _close_ui(self, caller=None):
        self._is_closing = True
        self._stop()

    def _start_ui(self):
        self._window_width = self._STREAM_WIDTH + 2
        self._window_height = self._STREAM_HEIGHT + 50
        screen_width, screen_height = self._get_screen_size()
        topLeft = [int((screen_height-self._window_height)/2.0),
                   int((screen_width-self._window_width)/2.0)]
        self._ui_window = cmds.window('VirtuCameraMayaWindow',
            width=self._window_width,
            height=self._window_height,
            menuBarVisible=False,
            titleBar=True,
            visible=True,
            sizeable=False,
            closeCommand=self._close_ui,
            title='VirtuCamera For Maya %s.%s.%s'%self._SERVER_VERSION)
        self._ui_layout = cmds.formLayout(numberOfDivisions=100)
        self._ui_tx_port = cmds.text(label='Port')
        self._ui_int_port = cmds.intField(minValue=0,
            maxValue=65535,
            value=self._DEFAULT_PORT,
            width=45)
        self._ui_bt_serve = cmds.button(label='Start Serving',
            width=100,
            command=self._start_serving)
        self._ui_tx_help = cmds.text(label='')
        self._ui_view = cmds.text(label='Click on Start Serving and connect through the App',
            backgroundColor=[0.2,0.2,0.2],
            width=self._window_width,
            height=self._STREAM_HEIGHT)
        self._update_ui_layout()

    def _serving_ui(self, qr_str):
        if not self._is_closing:
            cmds.button(self._ui_bt_serve, e=True, enable=True, label='Stop Serving', command=self._stop_serving)
            cmds.text(self._ui_tx_help, e=True, label='Server ready, connect through the App')
            qw = v1apiUI.MQtUtil.findControl(self._ui_view)
            widget = wrapInstance(long(qw), QtWidgets.QWidget)
            widget.setPixmap(qrcode.make(qr_str, image_factory=QtImageFactory, box_size=6).pixmap())
            cmds.intField(self._ui_int_port, e=True, enable=False)

    def _stopped_ui(self):
        if not self._is_closing:
            cmds.button(self._ui_bt_serve, e=True, enable=True, label='Start Serving', command=self._start_serving)
            cmds.text(self._ui_tx_help, e=True, label='')
            cmds.text(self._ui_view, e=True, label='Click on Start Serving and connect through the App')
            cmds.intField(self._ui_int_port, e=True, enable=True)

    def _connected_ui(self):
        cmds.text(self._ui_tx_help, e=True, label='')
        cmds.text(self._ui_view, e=True, label='Client App connected')

    def _hide_inactive_views(self):
        model_panels = cmds.getPanel(type="modelPanel")
        for pan in model_panels:
            if not cmds.modelEditor(pan, q=True, activeView=True):
                view_control = cmds.modelPanel(pan, q=True, control=True)
                if view_control:
                    cmds.control(view_control, edit=True, manage=False)
                    self._hidden_views.append(view_control)

    def _unhide_views(self):
        for view in self._hidden_views:
            if cmds.control(view, q=True, exists=True):
                cmds.control(view, edit=True, manage=True)
        self._hidden_views = []

    def _get_active_view(self):
        model_panels = cmds.getPanel(type="modelPanel")
        for pan in model_panels:
            if cmds.modelEditor(pan, q=True, activeView=True):
                return pan

    def _look_through_current_camera(self):
        cmds.modelPanel(self._ui_view, e=True, camera=self.current_camera)

    def _start_streaming_ui(self):
        self._orig_active_view = self._get_active_view()
        cmds.deleteUI(self._ui_view, control=True)
        self._ui_view = cmds.modelPanel(copy=self._orig_active_view, menuBarVisible=False, parent=self._ui_layout)
        bar_layout = cmds.modelPanel(self._ui_view, q=True, barLayout=True)
        cmds.frameLayout(bar_layout, edit=True, collapse=True)
        self._update_ui_layout()
        cmds.control(self._ui_view, edit=True, width=self._STREAM_WIDTH, height=self._STREAM_HEIGHT)
        cmds.text(self._ui_tx_help, edit=True, label='Client App connected  |  Streaming viewport...')
        cmds.modelEditor(self._ui_view, e=True, activeView=True)
        self._hide_inactive_views()
        self._look_through_current_camera()

    def _activate_orig_active_view(self):
        cmds.modelEditor(self._orig_active_view, e=True, activeView=True)

    def _stop_streaming_ui(self):
        self._unhide_views()
        if not self._is_closing:
            cmds.text(self._ui_tx_help, edit=True, label='')
            cmds.deleteUI(self._ui_view, panel=True)
            self._ui_view = cmds.text(label='Client App connected',
                backgroundColor=[0.2,0.2,0.2],
                width=self._window_width,
                height=self._STREAM_HEIGHT,
                parent=self._ui_layout)
            self._update_ui_layout()

    def _set_ffmpeg_bin(self, ffmpeg_bin):
        if ffmpeg_bin != None:
            self.ffmpeg_bin = ffmpeg_bin
        else:
            base_dir_path = os.path.dirname(os.path.abspath(__file__))
            ffmpeg_dir_path = os.path.join(base_dir_path, 'vendor', 'ffmpeg', 'bin')
            if os.name == 'nt':
                ffmpeg_bin = os.path.join(ffmpeg_dir_path, 'ffmpeg.exe')
            else:
                ffmpeg_bin = os.path.join(ffmpeg_dir_path, 'ffmpeg')

            if os.path.isfile(ffmpeg_bin):
                self.ffmpeg_bin = ffmpeg_bin
            else:
                self.ffmpeg_bin = 'ffmpeg'

    # Show existing UI if exists
    def __new__(cls, *args, **kwargs):
        window = 'VirtuCameraMayaWindow'
        if cmds.window(window, q=True, exists=True):
            cmds.showWindow(window)
            return None
        else:
            return super(VirtuCameraMaya, cls).__new__(cls, *args, **kwargs)

    def __init__(self, ffmpeg_bin=None):
        self._set_ffmpeg_bin(ffmpeg_bin)
        self.is_serving = False
        self.is_connected = False
        self._is_announcing = False
        self.is_streaming = False
        self.is_autosend = False
        self._is_closing = False
        self.current_camera = ''
        self._hidden_views = []
        self._maya_lock = thread.allocate_lock()
        self._fout_lock = thread.allocate_lock()
        self._zconf_lock = thread.allocate_lock()
        self._tcp_lock = thread.allocate_lock()
        self._start_ui()

    def _tcp_send(self, cmd, data=''):
        with self._tcp_lock:
            if self.is_serving and self.is_connected:
                self._tcp_clt_socket.send(cmd+data)

    def _tcp_send_with_len(self, cmd, data):
        data_length = struct.pack('<I', len(data))
        self._tcp_send(cmd, data_length+data)

    def _tcp_recv(self, exact_len):
        with self._tcp_lock:
            if self.is_serving and self.is_connected:
                data = str()
                data_len = 0
                while data_len < exact_len:
                    read_len = exact_len - data_len
                    data += self._tcp_clt_socket.recv(read_len)
                    data_len = len(data)
                return data

    def _maya_exec(self, func, *args):
        with self._maya_lock:
            result = utils.executeInMainThreadWithResult(func, *args)
        return result

    def _print(self, txt):
        print(txt)

    def _maya_print(self, txt):
        self._maya_exec(self._print, 'VirtuCamera: '+txt)

    def _get_ffmpeg_cmd(self, fps, bitrate, port, opaque):
        ffmpeg_cmd = [
            self.ffmpeg_bin,
            '-y',
            '-f:v', 'rawvideo',
            '-c:v', 'rawvideo',
            '-s', '%dx%d'%(self._STREAM_WIDTH, self._STREAM_HEIGHT), # frame dimensions
            '-pix_fmt', 'bgra',
            '-r', '%.3f'%fps,                        # frames per second
            '-an',                                   # Tells FFMPEG not to expect any audio
            '-i', '-',                               # The input comes from a pipe
        ]
        if opaque:
            ffmpeg_cmd += [
                '-vf', 'vflip',
                '-b:v', '%.3fM'%bitrate,            # RGB Bitrate
            ]
        else:
            bitrate_rgb = bitrate * (1-self._ALPHA_BITRATE_RATIO)
            bitrate_alpha = bitrate * self._ALPHA_BITRATE_RATIO
            ffmpeg_cmd += [
                '-filter_complex', '[0:v]vflip,split=2[rgbout][alphain];[alphain]alphaextract[alphaout]',
                '-map', '[rgbout]',
                '-map', '[alphaout]',
                '-b:v:0', '%.3fM'%bitrate_rgb,      # RGB Bitrate
                '-b:v:1', '%.3fM'%bitrate_alpha,    # Alpha Bitrate
            ]
        ffmpeg_cmd += [
            '-pix_fmt', 'yuv420p',
            '-c:v', 'libx264',
            '-tune', 'zerolatency',
            '-preset', 'fast',
            '-refs', '1',                            # number of reference frames for P-Frames
            '-intra-refresh', '1',                   # distribute I-Blocks along multiple frames
            #'-g', '%.0f'%fps,                        # intra-refresh interval (frames) 1/s
            '-profile:v', 'high',
            '-level', '4.1',
            '-f', 'avi',
            'tcp://%s:%d'%(self._tcp_clt_addr[0],port)
        ]
        return ffmpeg_cmd

    def _autosend_loop(self, autosend_interval):
        sleep_until = timeit.default_timer() + autosend_interval
        prev_time = 0
        while self.is_streaming:
            self._send_viewport_img()
            now = timeit.default_timer()
            if sleep_until > now and now > prev_time:
                time.sleep(sleep_until - now)
                sleep_until += autosend_interval
            else:
                sleep_until = now + autosend_interval
            prev_time = now

    def _start_autosend(self, fps):
        autosend_interval = (1.0/fps)
        thread.start_new_thread(self._autosend_loop, (autosend_interval,))

    def _start_streaming(self):
        if self.is_streaming:
            return

        if not self._maya_exec(cmds.objExists, self.current_camera):
            self._tcp_send(self._CMD_ERR_MISSING_CAMERA)
            return
            
        self.is_streaming = True
        # Read streaming parameters from TCP:
        # fps, 4 bytes (Float)
        # bitrate (Mbits/s), 4 bytes (Float)
        # port, 2 bytes (UInt16)
        # opaque, 1 byte (Bool)
        # autosend, 1 byte (Bool)
        data = self._tcp_recv(12)
        if not data:
            return
        fps, bitrate, port, opaque, self.is_autosend = struct.unpack('<ffH??', data)
        self._maya_print("Starting Viewport Streaming. %.2f fps, %.2f Mbits/s, Opaque: %d, Autosend: %d"%(fps, bitrate, opaque, self.is_autosend))
        self._ffmpeg_cmd = self._get_ffmpeg_cmd(fps, bitrate, port, opaque)
        #self._maya_print(self._ffmpeg_cmd)
        try:
            if hasattr(subprocess, 'STARTUPINFO'):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self._proc = subprocess.Popen(self._ffmpeg_cmd, stdin=subprocess.PIPE, startupinfo=startupinfo)
            else:
                self._proc = subprocess.Popen(self._ffmpeg_cmd, stdin=subprocess.PIPE)
        except:
            self._tcp_send(self._CMD_ERR_FFMPEG)
            self.is_streaming = False
            return
        self._fout = self._proc.stdin
        self._maya_exec(self._start_streaming_ui)
        self._view = apiUI.M3dView.active3dView()
        self._img = api.MImage()
        self._img_len = self._STREAM_WIDTH * self._STREAM_HEIGHT * 4
        if self.is_autosend:
            self._start_autosend(fps)

    def _stop_streaming(self, err=False):
        if not self.is_streaming:
            return
        self.is_streaming = False
        with self._fout_lock:
            self._fout.close()
        self._proc.wait()
        self._maya_exec(self._stop_streaming_ui)
        # Workaround to wait for Maya to start managing views again before seting active view
        time.sleep(0.1)
        self._maya_exec(self._activate_orig_active_view)
        self.is_autosend = False
        if err and self._proc.returncode !=0: raise subprocess.CalledProcessError(self._proc.returncode, self._ffmpeg_cmd)
        
    def _capture_viewport_img(self):
        self._view.readColorBuffer(self._img)
        img_ptr = self._img.pixels().__long__()
        img_bytes = ctypes.string_at(img_ptr, self._img_len)
        return img_bytes
    
    def _send_viewport_img(self):
        if not self.is_streaming:
            if not self.is_autosend:
                self._tcp_send(self._CMD_ERR_NOT_STREAMING)
            return
        img_bytes = self._maya_exec(self._capture_viewport_img)
        try:
            with self._fout_lock:
                self._fout.write(img_bytes)
        except:
            self._stop_streaming(err=True)
            if not self.is_autosend:
                self._tcp_send(self._CMD_ERR_NOT_STREAMING)

    def _transform_current_camera(self, tr_matrix):
        if cmds.objExists(self.current_camera):
            cmds.xform(self.current_camera, matrix = tr_matrix)
            return True
        return False

    def _set_camera_transform(self):
        # read transform matrix from TCP, 128 bytes (16 Double)
        data = self._tcp_recv(128)
        if not data:
            return
        tr_matrix = struct.unpack('<16d', data)
        status = self._maya_exec(self._transform_current_camera, tr_matrix)
        if not status:
            self._tcp_send(self._CMD_ERR_MISSING_CAMERA)

    def _transform_current_camera_at_time(self, tr_matrix, time):
        if cmds.objExists(self.current_camera):
            cmds.xform(self.current_camera, matrix = tr_matrix)
            self._maya_set_current_time(time)
            return True
        return False

    def _set_camera_transform_at_time(self):
        # read matrix-frame pair from TCP, 136 bytes (17 Double)
        data = self._tcp_recv(136)
        if not data:
            return
        decoded = struct.unpack('<17d', data)
        status = self._maya_exec(self._transform_current_camera_at_time, decoded[:16], decoded[-1])
        if not status:
            self._tcp_send(self._CMD_ERR_MISSING_CAMERA)

    def _get_current_camera_transform(self):
        if cmds.objExists(self.current_camera):
            return cmds.xform(self.current_camera, q=True, matrix=True)
        return None

    def _send_camera_transform(self, cmd):
        tr_matrix = self._maya_exec(self._get_current_camera_transform)
        if tr_matrix:
            data = struct.pack('<16d', *tr_matrix)
            self._tcp_send(cmd, data)
        else:
            self._tcp_send(self._CMD_ERR_MISSING_CAMERA)

    def _send_server_info(self, cmd):
        data = struct.pack('<3H', *self._SERVER_VERSION)
        self._tcp_send_with_len(cmd, data+self._SERVER_PLATFORM+'_'+self._get_server_name())

    def _get_scene_cameras(self):
        return cmds.listCameras(perspective=True)

    def _send_scene_cameras(self, cmd):
        self._scene_cameras = self._maya_exec(self._get_scene_cameras)
        try:
            current_camera_idx = self._scene_cameras.index(self.current_camera)
        except:
            current_camera_idx = 65535 # UInt16 max represents no current camera
        idx_data = struct.pack('<H', current_camera_idx)
        data = idx_data + str('$'.join(self._scene_cameras))
        self._tcp_send_with_len(cmd, data)

    def _set_current_camera(self):
        if self._scene_cameras:
            # read camera index from TCP, 2 bytes (UInt16)
            data = self._tcp_recv(2)
            if not data:
                return
            camera_idx = struct.unpack('<H', data)[0]
            camera = self._scene_cameras[camera_idx]
            if self._maya_exec(cmds.objExists, camera):
                self.current_camera = camera
                if self.is_streaming:
                    self._maya_exec(self._look_through_current_camera)
            else:
                self._tcp_send(self._CMD_ERR_MISSING_CAMERA)

    def _maya_set_current_time(self, time):
        # if maya is playing, stop it
        if cmds.play(q=True, state=True):
            cmds.play(state=False)
        cmds.currentTime(time, update=True)

    def _set_current_time(self):
        # read frame number from TCP, 8 bytes (1 Double)
        data = self._tcp_recv(8)
        if not data:
            return
        time = struct.unpack('<d', data)[0]
        self._maya_exec(self._maya_set_current_time, time)

    def _maya_set_focal_length(self, flen):
        cmds.setAttr(self.current_camera+'.focalLength', flen)

    def _set_focal_length(self):
        # read focal length from TCP, 8 bytes (1 Double)
        data = self._tcp_recv(8)
        if not data:
            return
        if self._maya_exec(cmds.objExists, self.current_camera):
            flen = struct.unpack('<d', data)[0]
            self._maya_exec(self._maya_set_focal_length, flen)
        else:
            self._tcp_send(self._CMD_ERR_MISSING_CAMERA)

    def _maya_playback(self, state=None, forward=True):
        if state == None:
            state = not cmds.play(q=True, state=True)
        if state:
            cmds.play(forward=forward)
        else:
            cmds.play(state=state)

    def _start_playback(self):
        # read 'forward' from TCP, 1 bytes (1 Bool)
        data = self._tcp_recv(1)
        if not data:
            return
        forward = struct.unpack('<?', data)[0]
        self._maya_exec(self._maya_playback, True, forward)

    def _stop_playback(self):
        self._maya_exec(self._maya_playback, False)

    def _switch_playback(self):
        self._maya_exec(self._maya_playback)

    def _get_scene_status(self):
        if cmds.objExists(self.current_camera):
            focal_len = cmds.getAttr(self.current_camera+'.focalLength')
            start = cmds.playbackOptions(q=True, min=True)
            end = cmds.playbackOptions(q=True, max=True)
            current = cmds.currentTime(q=True)
            return (current, start, end, focal_len)
        return None

    def _send_scene_status(self, cmd):
        scene_status = self._maya_exec(self._get_scene_status)
        if scene_status != None:
            data = struct.pack('<4d', *scene_status)
            self._tcp_send(cmd, data)
        else:
            self._tcp_send(self._CMD_ERR_MISSING_CAMERA)

    def _get_play_fps(self):
        maya_fps = cmds.currentUnit(query=True, time=True)
        if maya_fps[-3:] == 'fps':
            play_fps = float(maya_fps[:-3])
        elif maya_fps[-2:] == 'df':
            play_fps = float(maya_fps[:-2])
        else:
            play_fps = self._MAYA_FPS_PRESETS[maya_fps]
        return play_fps

    def _send_play_fps(self, cmd):
        play_fps = self._maya_exec(self._get_play_fps)
        data = struct.pack('<d', play_fps)
        self._tcp_send(cmd, data)

    def _get_camera_has_keys(self):
        if cmds.objExists(self.current_camera):
            cam_has_keys = False
            for attr in self._CAMERA_KEY_ATTRS:
                if cmds.connectionInfo(self.current_camera+attr, isDestination=True):
                    cam_has_keys = True
                    break
            return cam_has_keys
        return None

    def _send_camera_has_keys(self, cmd):
        cam_has_keys = self._maya_exec(self._get_camera_has_keys)
        if cam_has_keys != None:
            data = struct.pack('<?', cam_has_keys)
            self._tcp_send(cmd, data)
        else:
            self._tcp_send(self._CMD_ERR_MISSING_CAMERA)

    def _maya_set_playback_range(self, start, end):
        cmds.playbackOptions(min=start, max=end)

    def _set_playback_range(self):
        # read frame start and end from TCP, 16 bytes (2 Double)
        data = self._tcp_recv(16)
        if not data:
            return
        start, end = struct.unpack('<2d', data)
        self._maya_exec(self._maya_set_playback_range, start, end)

    def _maya_set_camera_flen_keys(self, keys):
        if cmds.objExists(self.current_camera):
            for start in xrange(0, len(keys), 2):
                end = start+1
                flen = keys[start]
                frame_num = keys[end]
                cmds.setAttr(self.current_camera+'.focalLength', flen)
                cmds.setKeyframe(self.current_camera, attribute='focalLength', t=frame_num)
            return True
        return False

    def _set_camera_flen_keys(self):
        # read key count, 2 bytes (UInt16)
        data = self._tcp_recv(2)
        if not data:
            return
        key_count = struct.unpack('<H', data)[0]
        # each key has a flen-frame pair of 16 bytes (2 Double)
        data_len = key_count * 16
        elem_len = key_count * 2
        data = self._tcp_recv(data_len)
        if not data:
            return
        keys = struct.unpack('<%id'%elem_len, data)
        status = self._maya_exec(self._maya_set_camera_flen_keys, keys)
        if not status:
            self._tcp_send(self._CMD_ERR_MISSING_CAMERA)

    def _maya_set_camera_matrix_keys(self, keys):
        if cmds.objExists(self.current_camera):
            for start in xrange(0, len(keys), 17):
                end = start+16
                tr_matrix = keys[start:end]
                frame_num = keys[end]
                cmds.xform(self.current_camera, matrix = tr_matrix)
                cmds.setKeyframe(self.current_camera, attribute=['t','r'], t=frame_num)
            anim_curves = cmds.listConnections((self.current_camera+'.rotateX', self.current_camera+'.rotateY', self.current_camera+'.rotateZ'), type='animCurve', skipConversionNodes=True)
            cmds.filterCurve(anim_curves)
            return True
        return False

    def _set_camera_matrix_keys(self):
        # read key count, 2 bytes (UInt16)
        data = self._tcp_recv(2)
        if not data:
            return
        key_count = struct.unpack('<H', data)[0]
        # each key has a matrix-frame pair of 136 bytes (17 Double)
        data_len = key_count * 136
        elem_len = key_count * 17
        data = self._tcp_recv(data_len)
        if not data:
            return
        keys = struct.unpack('<%id'%elem_len, data)
        status = self._maya_exec(self._maya_set_camera_matrix_keys, keys)
        if not status:
            self._tcp_send(self._CMD_ERR_MISSING_CAMERA)

    def _set_current_camera_all_at_time(self, tr_matrix, flen, time):
        if cmds.objExists(self.current_camera):
            cmds.setAttr(self.current_camera+'.focalLength', flen)
            cmds.xform(self.current_camera, matrix = tr_matrix)
            self._maya_set_current_time(time)
            return True
        return False

    def _set_camera_all_at_time(self):
        # read matrix-flen-frame from TCP, 144 bytes (18 Double)
        data = self._tcp_recv(144)
        if not data:
            return
        decoded = struct.unpack('<18d', data)
        status = self._maya_exec(self._set_current_camera_all_at_time, decoded[:16], decoded[-2], decoded[-1])
        if not status:
            self._tcp_send(self._CMD_ERR_MISSING_CAMERA)

    def _set_current_camera_all(self, tr_matrix, flen):
        if cmds.objExists(self.current_camera):
            cmds.setAttr(self.current_camera+'.focalLength', flen)
            cmds.xform(self.current_camera, matrix = tr_matrix)
            return True
        return False

    def _set_camera_all(self):
        # read matrix-flen pair from TCP, 136 bytes (17 Double)
        data = self._tcp_recv(136)
        if not data:
            return
        decoded = struct.unpack('<17d', data)
        status = self._maya_exec(self._set_current_camera_all, decoded[:16], decoded[-1])
        if not status:
            self._tcp_send(self._CMD_ERR_MISSING_CAMERA)

    def _maya_set_focal_length_at_time(self, flen, time):
        if cmds.objExists(self.current_camera):
            cmds.setAttr(self.current_camera+'.focalLength', flen)
            self._maya_set_current_time(time)
            return True
        return False

    def _set_focal_length_at_time(self):
        # read matrix-flen-frame from TCP, 16 bytes (2 Double)
        data = self._tcp_recv(16)
        if not data:
            return
        decoded = struct.unpack('<2d', data)
        status = self._maya_exec(self._maya_set_focal_length_at_time, decoded[0], decoded[1])
        if not status:
            self._tcp_send(self._CMD_ERR_MISSING_CAMERA)

    def _maya_remove_camera_keys(self):
        if cmds.objExists(self.current_camera):
            for attr in self._CAMERA_KEY_ATTRS:
                attr_path = self.current_camera + attr
                if cmds.connectionInfo(attr_path, isDestination=True):
                    source_attr = cmds.connectionInfo(attr_path, sourceFromDestination=True)
                    source = source_attr.split('.')[0]
                    cmds.delete(source)
            return True
        return False

    def _remove_camera_keys(self):
        done = self._maya_exec(self._maya_remove_camera_keys)
        if not done:
            self._tcp_send(self._CMD_ERR_MISSING_CAMERA)

    def _maya_create_new_camera(self):
        new_cam = cmds.camera()[0]
        if cmds.objExists(self.current_camera):
            for attr in self._CAMERA_KEY_ATTRS:
                old_val = cmds.getAttr(self.current_camera+attr)
                cmds.setAttr(new_cam+attr, old_val)
        return new_cam

    def _create_new_camera(self):
        self.current_camera = self._maya_exec(self._maya_create_new_camera)
        if self.is_streaming:
            self._maya_exec(self._look_through_current_camera)

    def _proccess_command(self, cmd):
        # Commands ordered by priority
        if cmd == self._CMD_SET_CAMERA_MATRIX_AT_TIME:
            self._tcp_send(cmd)
            self._set_camera_transform_at_time()
            return

        elif cmd == self._CMD_SET_CAMERA_MATRIX:
            self._tcp_send(cmd)
            self._set_camera_transform()
            return

        elif cmd == self._CMD_SET_CAMERA_ALL_AT_TIME:
            self._tcp_send(cmd)
            self._set_camera_all_at_time()
            return

        elif cmd == self._CMD_SET_CAMERA_ALL:
            self._tcp_send(cmd)
            self._set_camera_all()
            return

        elif cmd == self._CMD_SET_FOCAL_LENGTH_AT_TIME:
            self._tcp_send(cmd)
            self._set_focal_length_at_time()
            return

        elif cmd == self._CMD_SET_FOCAL_LENGTH:
            self._tcp_send(cmd)
            self._set_focal_length()
            return

        elif cmd == self._CMD_SET_CURRENT_TIME:
            self._tcp_send(cmd)
            self._set_current_time()
            return

        elif cmd == self._CMD_ASK_VIEWPORT_IMG:
            self._send_viewport_img()
            return

        elif cmd == self._CMD_ASK_SCENE_STATUS:
            self._send_scene_status(cmd)
            return

        elif cmd == self._CMD_ASK_CAMERA_MATRIX:
            self._send_camera_transform(cmd)
            return

        elif cmd == self._CMD_ASK_CAMERA_HAS_KEYS:
            self._send_camera_has_keys(cmd)
            return

        elif cmd == self._CMD_ASK_PLAY_FPS:
            self._send_play_fps(cmd)
            return

        elif cmd == self._CMD_DO_SWITCH_PLAYBACK:
            self._tcp_send(cmd)
            self._switch_playback()
            return

        elif cmd == self._CMD_DO_START_PLAYBACK:
            self._tcp_send(cmd)
            self._start_playback()
            return

        elif cmd == self._CMD_DO_STOP_PLAYBACK:
            self._tcp_send(cmd)
            self._stop_playback()
            return

        elif cmd == self._CMD_ASK_SCENE_CAMERAS:
            self._send_scene_cameras(cmd)
            return

        elif cmd == self._CMD_SET_CURRENT_CAMERA:
            self._tcp_send(cmd)
            self._set_current_camera()
            return

        elif cmd == self._CMD_SET_PLAYBACK_RANGE:
            self._tcp_send(cmd)
            self._set_playback_range()
            return

        elif cmd == self._CMD_DO_REMOVE_CAMERA_KEYS:
            self._tcp_send(cmd)
            self._remove_camera_keys()
            return

        elif cmd == self._CMD_DO_CREATE_NEW_CAMERA:
            self._tcp_send(cmd)
            self._create_new_camera()
            return

        elif cmd == self._CMD_SET_CAMERA_MATRIX_KEYS:
            self._tcp_send(cmd)
            self._set_camera_matrix_keys()
            return

        elif cmd == self._CMD_SET_CAMERA_FLEN_KEYS:
            self._tcp_send(cmd)
            self._set_camera_flen_keys()
            return

        elif cmd == self._CMD_DO_START_STREAMING:
            self._tcp_send(cmd)
            self._start_streaming()
            return

        elif cmd == self._CMD_DO_STOP_STREAMING:
            self._tcp_send(cmd)
            self._stop_streaming()
            return

        elif cmd == self._CMD_ASK_SERVER_INFO:
            self._send_server_info(cmd)
            return

    def _get_server_name(self):
        compname = socket.gethostname()
        if sys.platform == 'darwin':
            try:
                compname = subprocess.check_output(["scutil", "--get", "ComputerName"])[:-1]
            except:
                pass
        compname = compname.replace('.','-').replace('_','-')
        compname += ' - %s'%self._SERVER_PLATFORM
        return compname

    def _get_net_addresses(self):
        hostname = socket.gethostname()
        ip_addresses = socket.gethostbyname_ex(hostname)[-1]
        return ip_addresses


    def _server_register(self):
        with self._zconf_lock:
            hostname = socket.gethostname()
            ips = self._get_net_addresses()
            if ips:
                compname = self._get_server_name().decode('utf-8')
                hostaddr = ips[0]
                desc = {'platform': self._SERVER_PLATFORM, 'version': '%s.%s.%s'%self._SERVER_VERSION}
                info = zeroconf.ServiceInfo(self._ZEROCONF_TYPE, '%s.'%compname + self._ZEROCONF_TYPE, socket.inet_aton(hostaddr), self._tcp_srv_port, 0, 0, desc, '%s.'%hostname)
                self._zconf = zeroconf.Zeroconf(bindaddress=hostaddr)
                self._zconf.register_service(info)
            else:
                self._zconf = zeroconf.Zeroconf()

    def _server_unregister(self):
        with self._zconf_lock:
            self._zconf.close()

    def _handle_server_announcement(self):
        self._is_announcing = True
        while self.is_serving and not self.is_connected:
            time.sleep(self._ANNOUNCEMENT_INTERVAL)
            with self._zconf_lock:
                if self.is_serving and not self.is_connected:
                    self._zconf.re_register_all_services()
        self._is_announcing = False

    def _qr_string(self):
        ip_addresses = self._get_net_addresses()[:10] # limit to 10 ip addresses
        result = str(self._tcp_srv_port)
        for address in ip_addresses:
            result += '_' + address
        return result

    def _handle_tcp_socket(self):
        while self.is_serving:
            if not self._is_announcing:
                thread.start_new_thread(self._handle_server_announcement, ())
            self._maya_print('Listening on TCP port %d'%self._tcp_srv_port)
            self._tcp_clt_socket, self._tcp_clt_addr = self._tcp_srv_socket.accept()
            if self.is_serving:
                self.is_connected = True
                self._maya_exec(self._connected_ui)
                self._maya_print('Accepted connection from: %s:%d'%self._tcp_clt_addr)
                while self.is_serving:
                    try:
                        cmd = self._tcp_clt_socket.recv(1)
                    except:
                        break
                    if cmd:
                        self._proccess_command(cmd)
                    else:
                        break
                self.is_connected = False
                if self.is_streaming:
                    self._stop_streaming()
                if self.is_serving:
                    self._maya_exec(self._serving_ui, self._qr_string())
                self._maya_print('Disconnected from: %s:%d'%self._tcp_clt_addr)
                self.current_camera = ''
            self._tcp_clt_socket.close()
        self._maya_print('Stopped serving')

    def _stop_tcp_accept(self):
        tempsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tempsock.connect(('127.0.0.1', self._tcp_srv_port))
        tempsock.close()

    def _serve(self, port=0):
        if not self.is_serving:
            self.is_serving = True
            self._tcp_srv_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._tcp_srv_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._tcp_srv_socket.bind(('0.0.0.0', port))
            self._tcp_srv_port = self._tcp_srv_socket.getsockname()[1]
            self._tcp_srv_socket.listen(1)
            thread.start_new_thread(self._handle_tcp_socket, ())
            self._server_register()
            self._serving_ui(self._qr_string())

    def _stop(self):
        with self._tcp_lock:
            if self.is_serving:
                self.is_serving = False
                if self.is_streaming:
                    self._stop_streaming()
                if not self.is_connected:
                    self._stop_tcp_accept()
                self._tcp_srv_socket.close()
                self._maya_exec(self._server_unregister) # For some reason it needs to be called with maya_exec to avoid crashing
                self._stopped_ui()