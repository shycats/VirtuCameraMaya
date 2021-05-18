# VirtuCameraMaya
# Copyright (c) 2021 Pablo Javier Garcia Gonzalez.
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDERS BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
# OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THE SOFTWARE,
# EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# Python modules
import os, sys, traceback

# Maya modules
import maya.api.OpenMaya as api
import maya.api.OpenMayaUI as apiUI
from maya import OpenMayaUI as v1apiUI
import maya.cmds as cmds
import maya.mel as mel
import maya.utils as utils

# QT
from PySide2 import QtWidgets
from shiboken2 import wrapInstance

# Config handling lib
from . import virtuCameraMayaConfig

# PyVirtuCamera core lib
from .virtucamera import VCBase, VCServer

class VirtuCameraMaya(VCBase):
    # Constants
    PLUGIN_VERSION = (2,0,0)
    WINDOW_WIDTH = 160
    WINDOW_HEIGHT = 180
    CONFIG_FILE = 'configuration.xml' # Configuration file name
    VC_TO_ZUP_MAT = api.MMatrix((1, 0, 0, 0, 0, 0, 1, 0, 0,-1, 0, 0, 0, 0, 0, 1))
    ZUP_TO_VC_MAT = api.MMatrix((1, 0, 0, 0, 0, 0,-1, 0, 0, 1, 0, 0, 0, 0, 0, 1))
    CAMERA_KEY_ATTRS = ('.focalLength','.tx','.ty','.tz','.rx','.ry','.rz')
    MAYA_FPS_PRESETS = {
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

    # Show existing UI if exists
    def __new__(cls, *args, **kwargs):
        window = 'VirtuCameraMayaWindow'
        if cmds.window(window, q=True, exists=True):
            cmds.showWindow(window)
            return None
        else:
            return super(VirtuCameraMaya, cls).__new__(cls, *args, **kwargs)

    def __init__(self):
        mayapy = None
        if os.name == 'nt':
            # On windows, get path to python executable,
            # needed for the viewport video feed to work
            mayapy = os.path.join(os.path.dirname(sys.executable), "mayapy.exe")

        # Init virtucamera.VCServer
        self.vcserver = VCServer(
            platform = "Maya",
            plugin_version = self.PLUGIN_VERSION,
            event_mode = VCServer.EVENTMODE_PUSH,
            vcbase = self,
            main_thread_func = utils.executeInMainThreadWithResult,
            python_executable = mayapy
        )

        # Load plug-in configuration
        config_file_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), self.CONFIG_FILE)
        self.config = virtuCameraMayaConfig.VirtuCameraMayaConfig(config_file_path, self.vcserver.update_script_labels)

        self.is_closing_ui = False
        self.hidden_views = []
        self.start_ui()


    # -- User Interface ------------------------------------

    def update_ui_layout(self):
        cmds.formLayout(self.ui_layout, edit=True,
            attachForm=[(self.ui_bt_serve, 'left', 5), (self.ui_bt_serve, 'top', 5), (self.ui_tx_help, 'left', 5), (self.ui_tx_help, 'right', 5), (self.ui_bt_conf, 'top', 5), (self.ui_bt_conf, 'right', 5), (self.ui_view, 'left', 5), (self.ui_view, 'right', 5), (self.ui_view, 'bottom', 5)],
            attachControl=[(self.ui_bt_serve, 'right', 5, self.ui_bt_conf), (self.ui_tx_help, 'top', 5, self.ui_bt_serve), (self.ui_view, 'top', 5, self.ui_tx_help)])

    def start_serving(self, caller=None):
        if self.vcserver.start_serving(self.config.server_port):
            self.serving_ui()

    def stop_serving(self, caller=None):
        self.vcserver.stop_serving()

    def close_ui(self, caller=None):
        self.is_closing_ui = True
        self.vcserver.stop_serving()
        
    def open_config_window(self, caller=None):
        self.config.show_window()

    def start_ui(self):
        # Remove size preference to force the window calculate its size
        windowName = 'VirtuCameraMayaWindow'
        if cmds.windowPref(windowName, exists=True):
            cmds.windowPref(windowName, remove=True)

        self.ui_window = cmds.window(windowName,
            width=self.WINDOW_WIDTH,
            height=self.WINDOW_HEIGHT,
            menuBarVisible=False,
            titleBar=True,
            visible=True,
            sizeable=True,
            closeCommand=self.close_ui,
            title='VC %s.%s.%s'%self.PLUGIN_VERSION)
        self.ui_layout = cmds.formLayout(numberOfDivisions=100)
        self.ui_bt_serve = cmds.button(label='Start Serving',
            command=self.start_serving)
        self.ui_tx_help = cmds.text(label='', width=self.WINDOW_WIDTH-10)
        self.ui_bt_conf = cmds.button(label='Config',
            command=self.open_config_window)
        self.ui_view = cmds.text(label='Click on Start Serving and\nconnect through the App',
            backgroundColor=[0.2,0.2,0.2],
            width=self.WINDOW_WIDTH-10,
            height=self.WINDOW_HEIGHT-10)
        self.update_ui_layout()

    def serving_ui(self):
        if self.is_closing_ui:
            return
        cmds.button(self.ui_bt_serve, e=True, enable=True, label='Stop Serving', command=self.stop_serving)
        cmds.text(self.ui_tx_help, e=True, label='Scan QR Code with VirtuCamera App')
        qw = v1apiUI.MQtUtil.findControl(self.ui_view)
        widget = wrapInstance(int(qw), QtWidgets.QWidget)
        widget.setPixmap(self.vcserver.get_qr_image_qt(3))

    def stopped_ui(self):
        if self.is_closing_ui:
            return
        cmds.button(self.ui_bt_serve, e=True, enable=True, label='Start Serving', command=self.start_serving)
        cmds.text(self.ui_tx_help, e=True, label='')
        cmds.text(self.ui_view, e=True, label='Click on Start Serving and\nconnect through the App')

    def connected_ui(self):
        cmds.text(self.ui_tx_help, e=True, label='')
        cmds.text(self.ui_view, e=True, label='Client App connected')

    def start_capturing_ui(self, hide_inactive_views):
        cmds.text(self.ui_view, edit=True, label='Client App connected\nStreaming viewport')
        if hide_inactive_views:
            # Workaround to make M3dView.readColorBuffer() work when multiple viewports are visible
            self.hide_inactive_views()

    def stop_capturing_ui(self):
        if self.is_closing_ui:
            return
        self.unhide_views()
        cmds.text(self.ui_view, edit=True, label='Client App connected')

    def hide_inactive_views(self):
        model_panels = cmds.getPanel(type="modelPanel")
        for pan in model_panels:
            if not cmds.modelEditor(pan, q=True, activeView=True):
                view_control = cmds.modelPanel(pan, q=True, control=True)
                if view_control:
                    cmds.control(view_control, edit=True, manage=False)
                    self.hidden_views.append(view_control)

    def unhide_views(self):
        for view in self.hidden_views:
            if cmds.control(view, q=True, exists=True):
                cmds.control(view, edit=True, manage=True)
        self.hidden_views = []

    def get_active_view(self):
        model_panels = cmds.getPanel(type="modelPanel")
        for pan in model_panels:
            if cmds.modelEditor(pan, q=True, activeView=True):
                return pan


    # -- Utility Functions ------------------------------------

    # Rotate matrix up axis from VirtuCamera (Y+) to Maya
    def vc_to_maya_up_axis(self, tr_matrix):
        if self.is_z_up:
            mat = api.MMatrix(tr_matrix)
            mat *= self.VC_TO_ZUP_MAT
            return tuple(mat)
        return tr_matrix

    # Rotate matrix up axis from Maya to VirtuCamera (Y+)
    def maya_to_vc_up_axis(self, tr_matrix):
        if self.is_z_up:
            mat = api.MMatrix(tr_matrix)
            mat *= self.ZUP_TO_VC_MAT
            return tuple(mat)
        return tr_matrix


    # SCENE STATE RELATED METHODS:
    # ---------------------------

    def get_playback_state(self, vcserver):
        """ Must Return the playback state of the scene as a tuple or list
        in the following order: (current_frame, range_start, range_end)
        * current_frame (float) - The current frame number.
        * range_start (float) - Animation range start frame number.
        * range_end (float) - Animation range end frame number.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.

        Returns
        -------
        tuple or list of 3 floats
            playback state as (current_frame, range_start, range_end)
        """

        range_start = cmds.playbackOptions(q=True, min=True)
        range_end = cmds.playbackOptions(q=True, max=True)
        current_frame = cmds.currentTime(q=True)
        return (current_frame, range_start, range_end)


    def get_playback_fps(self, vcserver):
        """ Must return a float value with the scene playback rate
        in Frames Per Second.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.

        Returns
        -------
        float
            scene playback rate in FPS.
        """

        maya_fps = cmds.currentUnit(query=True, time=True)
        if maya_fps[-3:] == 'fps':
            play_fps = float(maya_fps[:-3])
        elif maya_fps[-2:] == 'df':
            play_fps = float(maya_fps[:-2])
        else:
            play_fps = self.MAYA_FPS_PRESETS[maya_fps]
        return play_fps


    def set_frame(self, vcserver, frame):
        """ Must set the current frame number on the scene

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        frame : float
            The current frame number.
        """

        # if maya is playing, stop it
        if cmds.play(q=True, state=True):
            cmds.play(state=False)
        cmds.currentTime(frame, update=True)


    def set_playback_range(self, vcserver, start, end):
        """ Must set the animation frame range on the scene

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        start : float
            Animation range start frame number.
        end : float
            Animation range end frame number.
        """

        cmds.playbackOptions(min=start, max=end)
        

    def start_playback(self, vcserver, forward):
        """ This method must start the playback of animation in the scene.
        Not used at the moment, but must be implemented just in case
        the app starts using it in the future. At the moment
        VCBase.set_frame() is called instead.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        forward : bool
            if True, play the animation forward, if False, play it backwards.
        """

        cmds.play(forward=forward)


    def stop_playback(self, vcserver):
        """ This method must stop the playback of animation in the scene.
        Not used at the moment, but must be implemented just in case
        the app starts using it in the future.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        """

        cmds.play(state=False)


    # CAMERA RELATED METHODS:
    # -----------------------


    def get_scene_cameras(self, vcserver):
        """ Must Return a list or tuple with the names of all the scene cameras.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.

        Returns
        -------
        tuple or list
            names of all the scene cameras.
        """

        cameras = cmds.listCameras(perspective=True)
        # replace shapes with transforms (maya returns shapes when other objects are parented under a camera)
        cam_shapes = cmds.ls(cameras, shapes=True)
        cameras = list(set(cmds.ls(cameras, type="transform") + cmds.ls(cmds.listRelatives(cam_shapes, parent=True, fullPath=True), type="transform")))
        cameras.sort()
        return cameras


    def get_camera_exists(self, vcserver, camera_name):
        """ Must Return True if the specified camera exists in the scene,
        False otherwise.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        camera_name : str
            Name of the camera to check for.

        Returns
        -------
        bool
            'True' if the camera 'camera_name' exists, 'False' otherwise.
        """

        return cmds.objExists(camera_name)


    def get_camera_has_keys(self, vcserver, camera_name):
        """ Must Return whether the specified camera has animation keyframes
        in the transform or flocal length parameters, as a tuple or list,
        in the following order: (transform_has_keys, focal_length_has_keys)
        * transform_has_keys (bool) - True if the transform has keyframes.
        * focal_length_has_keys (bool) - True if the flen has keyframes.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        camera_name : str
            Name of the camera to check for.

        Returns
        -------
        tuple or list of 2 bool
            whether the camera 'camera_name' has keys or not as
            (transform_has_keys, focal_length_has_keys)
        """

        transform_has_keys = False
        focal_length_has_keys = False
        for attr in self.CAMERA_KEY_ATTRS:
            if cmds.connectionInfo(camera_name+attr, isDestination=True):
                if attr == '.focalLength':
                    focal_length_has_keys = True
                else:
                    transform_has_keys = True
                    break
        return (transform_has_keys, focal_length_has_keys)


    def get_camera_focal_length(self, vcserver, camera_name):
        """ Must Return the focal length value of the specified camera.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        camera_name : str
            Name of the camera to get the data from.

        Returns
        -------
        float
            focal length value of the camera 'camera_name'.
        """

        focal_len = cmds.getAttr(camera_name+'.focalLength')
        return focal_len


    def get_camera_transform(self, vcserver, camera_name):
        """ Must return a tuple or list of 16 floats with the 4x4
        transform matrix of the specified camera.

        * The up axis must be Y+
        * The order must be:
            (rxx, rxy, rxz, 0,
            ryx, ryy, ryz, 0,
            rzx, rzy, rzz, 0,
            tx,  ty,  tz,  1)
            Being 'r' rotation and 't' translation,

        Is your responsability to rotate or transpose the matrix if needed,
        most 3D softwares offer fast APIs to do so.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        camera_name : str
            Name of the camera to get the data from.

        Returns
        -------
        tuple or list of 16 float
            4x4 transform matrix as
            (rxx, rxy, rxz, 0, ryx, ryy, ryz, 0, rzx, rzy, rzz, 0 , tx, ty, tz, 1)
        """

        tr_matrix = cmds.xform(camera_name, q=True, matrix=True)
        return self.maya_to_vc_up_axis(tr_matrix)


    def set_camera_focal_length(self, vcserver, camera_name, focal_length):
        """ Must set the focal length of the specified camera.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        camera_name : str
            Name of the camera to set the focal length to.
        focal_length : float
            focal length value to be set on the camera 'camera_name'
        """

        cmds.setAttr(camera_name+'.focalLength', focal_length)


    def set_camera_transform(self, vcserver, camera_name, transform_matrix):
        """  Must set the transform of the specified camera.
        The transform matrix is provided as a tuple of 16 floats
        with a 4x4 transform matrix.

        * The up axis is Y+
        * The order is:
            (rxx, rxy, rxz, 0,
            ryx, ryy, ryz, 0,
            rzx, rzy, rzz, 0,
            tx,  ty,  tz,  1)
            Being 'r' rotation and 't' translation,

        Is your responsability to rotate or transpose the matrix if needed,
        most 3D softwares offer fast APIs to do so.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        camera_name : str
            Name of the camera to set the transform to.
        transform_matrix : tuple of 16 floats
            transformation matrix to be set on the camera 'camera_name'
        """

        cmds.xform(camera_name, matrix = self.vc_to_maya_up_axis(transform_matrix))


    def set_camera_flen_keys(self, vcserver, camera_name, keyframes, focal_length_values):
        """ Must set keyframes on the focal length of the specified camera.
        The frame numbers are provided as a tuple of floats and
        the focal length values are provided as a tuple of floats
        with a focal length value for every keyframe.

        The first element of the 'keyframes' tuple corresponds to the first
        element of the 'focal_length_values' tuple, the second to the second,
        and so on.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        camera_name : str
            Name of the camera to set the keyframes to.
        keyframes : tuple of floats
            Frame numbers to create the keyframes on.
        focal_length_values : tuple of floats
            focal length values to be set as keyframes on the camera 'camera_name'
        """

        for keyframe, focal_length in zip(keyframes, focal_length_values):
            self.set_camera_focal_length(vcserver, camera_name, focal_length)
            cmds.setKeyframe(camera_name, attribute='focalLength', t=keyframe)


    def set_camera_transform_keys(self, vcserver, camera_name, keyframes, transform_matrix_values):
        """ Must set keyframes on the transform of the specified camera.
        The frame numbers are provided as a tuple of floats and
        the transform matrixes are provided as a tuple of tuples of 16 floats
        with 4x4 transform matrixes, with a matrix for every keyframe.

        The first element of the 'keyframes' tuple corresponds to the first
        element of the 'transform_matrix_values' tuple, the second to the second,
        and so on.

        * The up axis is Y+
        * The order is:
            (rxx, rxy, rxz, 0,
            ryx, ryy, ryz, 0,
            rzx, rzy, rzz, 0,
            tx,  ty,  tz,  1)
            Being 'r' rotation and 't' translation,

        Is your responsability to rotate or transpose the matrixes if needed,
        most 3D softwares offer fast APIs to do so.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        camera_name : str
            Name of the camera to set the keyframes to.
        keyframes : tuple of floats
            Frame numbers to create the keyframes on.
        transform_matrix_values : tuple of tuples of 16 floats
            transformation matrixes to be set as keyframes on the camera 'camera_name'
        """

        for keyframe, matrix in zip(keyframes, transform_matrix_values):
            self.set_camera_transform(vcserver, camera_name, matrix)
            cmds.setKeyframe(camera_name, attribute=['t','r'], t=keyframe)
        anim_curves = cmds.listConnections((camera_name+'.rotateX', camera_name+'.rotateY', camera_name+'.rotateZ'), type='animCurve', skipConversionNodes=True)
        cmds.filterCurve(anim_curves)


    def remove_camera_keys(self, vcserver, camera_name):
        """ This method must remove all transform
        and focal length keyframes in the specified camera.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        camera_name : str
            Name of the camera to remove the keyframes from.
        """

        for attr in self.CAMERA_KEY_ATTRS:
            attr_path = camera_name + attr
            if cmds.connectionInfo(attr_path, isDestination=True):
                source_attr = cmds.connectionInfo(attr_path, sourceFromDestination=True)
                source = source_attr.split('.')[0]
                cmds.delete(source)


    def create_new_camera(self, vcserver):
        """ This method must create a new camera in the scene
        and return its name.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.

        Returns
        -------
        str
            Newly created camera name.
        """

        new_cam = cmds.camera()[0]
        if cmds.objExists(vcserver.current_camera):
            for attr in self.CAMERA_KEY_ATTRS:
                old_val = cmds.getAttr(vcserver.current_camera+attr)
                cmds.setAttr(new_cam+attr, old_val)
        return new_cam


    # VIEWPORT CAPTURE RELATED METHODS:
    # ---------------------------------


    def capture_will_start(self, vcserver):
        """ This method is called whenever a client app requests a video
        feed from the viewport. Usefull to init a pixel buffer
        or other objects you may need to capture the viewport

        IMPORTANT! Calling vcserver.set_capture_resolution() and
        vcserver.set_capture_mode() here is a must. Please check
        the documentation for those methods.

        You can also call vcserver.set_vertical_flip() here optionally,
        if you need to flip your pixel buffer. Disabled by default.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        """

        view = apiUI.M3dView.active3dView()
        width = view.portWidth()
        height = view.portHeight()
        self.img = api.MImage()
        vcserver.set_capture_resolution(width, height)
        vcserver.set_vertical_flip(True)
        if self.config.capture_mode == self.config.CAPMODE_SCREENSHOT:
            vcserver.set_capture_mode(vcserver.CAPMODE_SCREENSHOT)
            self.start_capturing_ui(hide_inactive_views=False)
        else:
            vcserver.set_capture_mode(vcserver.CAPMODE_BUFFER_POINTER, vcserver.CAPFORMAT_UBYTE_BGRA)
            self.start_capturing_ui(hide_inactive_views=True)


    def capture_did_end(self, vcserver):
        """ Optional, this method is called whenever a client app
        stops the viewport video feed. Usefull to destroy a pixel buffer
        or other objects you may have created to capture the viewport.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        """

        if vcserver.is_connected:
            self.stop_capturing_ui()

    def get_capture_coords(self, vcserver, camera_name):
        """ If vcserver.capture_mode == vcserver.CAPMODE_SCREENSHOT, it must
        return a tuple or list with the left-top coordinates (x,y)
        of the screen region to be captured, being 'x' the horizontal axis
        and 'y' the vertical axis. If you don't use CAPMODE_SCREENSHOT,
        you don't need to overload this method.

        If the screen region has changed in size from the previous call to
        this method, and therefore the capture resolution is different,
        vcserver.set_capture_resolution() must be called here before returning.
        You can use vcserver.capture_width and vcserver.capture_height
        to check the previous resolution.

        The name of the camera selected in the app is provided,
        as can be usefull to set-up the viewport render in some cases.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        camera_name : str
            Name of the camera that is currently selected in the App.

        Returns
        -------
        tuple or list of 2 float
            left-top screen coordinates of the capture region as (x,y).
        """

        view = apiUI.M3dView.active3dView()
        width = view.portWidth()
        height = view.portHeight()
        coords = view.getScreenPosition()
        if width != vcserver.capture_width or height != vcserver.capture_height:
            vcserver.set_capture_resolution(width, height)
        return coords


    def get_capture_pointer(self, vcserver, camera_name):
        """ If vcserver.capture_mode == vcserver.CAPMODE_BUFFER_POINTER,
        it must return an int representing a memory address to the first
        element of a contiguous buffer containing raw pixels of the 
        viewport image. The buffer must be kept allocated untill the next
        call to this function, is your responsability to do so.
        If you don't use CAPMODE_BUFFER_POINTER
        you don't need to overload this method.

        If the capture resolution has changed in size from the previous call to
        this method, vcserver.set_capture_resolution() must be called here
        before returning. You can use vcserver.capture_width and
        vcserver.capture_height to check the previous resolution.

        The name of the camera selected in the app is provided,
        as can be usefull to set-up the viewport render in some cases.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        camera_name : str
            Name of the camera that is currently selected in the App.

        Returns
        -------
        int
            value of the memory address to the first element of the buffer.
        """

        view = apiUI.M3dView.active3dView()
        width = view.portWidth()
        height = view.portHeight()
        if width != vcserver.capture_width or height != vcserver.capture_height:
            vcserver.set_capture_resolution(width, height)
        view.readColorBuffer(self.img)
        img_ptr = self.img.pixels()
        return img_ptr


    def look_through_camera(self, vcserver, camera_name):
        """ This method must set the viewport to look through
        the specified camera.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        camera_name : str
            Name of the camera to look through
        """

        cmds.modelPanel(self.get_active_view(), e=True, camera=camera_name)


    # APP/SERVER FEEDBACK METHODS:
    # ----------------------------

    def client_connected(self, vcserver, client_ip, client_port):
        """ Optional, this method is called whenever a client app
        connects to the server. Usefull to give the user
        feedback about a successfull connection.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        client_ip : str
            ip address of the remote client
        client_port : int
            port number of the remote client
        """

        self.connected_ui()
        # Store Maya Z Up axis, will be used for matrix conversion
        self.is_z_up = cmds.upAxis( q=True, axis=True ) == 'z'


    def client_disconnected(self, vcserver):
        """ Optional, this method is called whenever a client app
        disconnects from the server, even if it's disconnected by calling
        stop_serving() with the virtucamera.VCServer API. Usefull to give
        the user feedback about the disconnection.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        """

        if vcserver.is_serving:
            self.serving_ui()


    def server_did_stop(self, vcserver):
        """ Optional, calling stop_serving() on virtucamera.VCServer
        doesn't instantly stop the server, it is done in the background
        due to the asyncronous nature of some of its processes.
        This method is called when all services have been completely
        stopped.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        """

        self.stopped_ui()


    # CUSTOM SCRIPT METHODS:
    # ----------------------

    def get_script_labels(self, vcserver):
        """ Optionally Return a list or tuple of str with the labels of
        custom scripts to be called from VirtuCamera App. Each label is
        a string that identifies the script that will be showed
        as a button in the App.

        The order of the labels is important. Later if the App asks
        to execute a script, an index based on this order will be provided
        to VCBase.execute_script(), so that method must also be implemented.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.

        Returns
        -------
        tuple or list of str
            custom script labels.
        """

        return self.config.script_labels
        

    def execute_script(self, vcserver, script_index, current_camera):
        """ Only required if VCBase.get_script_labels()
        has been implemented. This method is called whenever the user
        taps on a custom script button in the app.
        
        Each of the labels returned from VCBase.get_script_labels()
        identify a custom script that is showed as a button in the app.
        The order of the labels is important and 'script_index' is a 0-based
        index representing what script to execute from that list/tuple.

        This function must return True if the script executed correctly,
        False if there where errors. It's recommended to print any errors,
        so that the user has some feedback about what went wrong.

        You may want to provide a way for the user to refer to the currently
        selected camera in their scripts, so that they can act over it.
        'current_camera' is provided for this situation.

        Parameters
        ----------
        vcserver : virtucamera.VCServer object
            Instance of virtucamera.VCServer calling this method.
        script_index : int
            Script number to be executed.
        current_camera : str
            Name of the currently selected camera
        """

        if script_index >= self.config.script_count:
            print("Can't execute script "+str(script_index+1)+". Reason: Script doesn't exist")
            return False

        script_code = self.config.script_codes[script_index]
        if script_code == '':
            print("Can't execute script "+str(script_index+1)+". Reason: Empty script")
            return False

        script_code = script_code.replace('%SELCAM%', '"'+current_camera+'"')
        script_lang = self.config.script_langs[script_index]
        # use try to prevent any possible errors in the script from stopping plug-in execution
        try:
            if script_lang == self.config.LANG_PY:
                exec(script_code)
            elif script_lang == self.config.LANG_MEL:
                mel.eval(script_code)
            return True
        except:
            # Print traceback to inform the user
            traceback.print_exc()
            return False