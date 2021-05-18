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

import sys, os
import maya.api.OpenMaya as OpenMaya
import maya.cmds as cmds
import virtuCameraMaya

##########################################################
# Plug-in 
##########################################################
class VirtuCameraMayaPlugin( OpenMaya.MPxCommand ):
    kPluginCmdName = 'virtuCamera'
    
    def __init__(self):
        ''' Constructor. '''
        OpenMaya.MPxCommand.__init__(self)
    
    @staticmethod 
    def cmdCreator():
        ''' Create an instance of our command. '''
        return VirtuCameraMayaPlugin() 
    
    def doIt(self, args):
        ''' Command execution. '''
        import virtuCameraMaya
        #virtuCameraMaya = reload(virtuCameraMaya.virtuCameraMaya)
        virtuCameraMaya.VirtuCameraMaya()
    
##########################################################
# Plug-in initialization.
##########################################################
def maya_useNewAPI():
	"""
	The presence of this function tells Maya that the plugin produces, and
	expects to be passed, objects created using the Maya Python API 2.0.
	"""
	pass

def configPlugin():
    pluginPath = os.path.dirname(os.path.abspath(virtuCameraMaya.__file__))
    shelfName = 'VirtuCamera'
    buttonName = 'VirtuCamera'
    iconName = 'virtuCameraIcon_32pt.png'
    iconPath = os.path.join(pluginPath, iconName)
    buttonExists = False
    if not cmds.shelfLayout(shelfName, ex=True):
        cmds.shelfLayout(shelfName, p='ShelfLayout')
    else:
        buttons = cmds.shelfLayout(shelfName, q=True, ca=True)
        if buttons:
            for button in buttons:
                if cmds.shelfButton(button, q=True, l=True) == buttonName:
                    buttonExists = True
                    break
    if not buttonExists:
        cmds.shelfButton(w=35, h=35, i=iconPath, l=buttonName, c='from maya import cmds; cmds.'+VirtuCameraMayaPlugin.kPluginCmdName+'()', p=shelfName)

def initializePlugin( mobject ):
    ''' Initialize the plug-in when Maya loads it. '''
    configPlugin()
    mplugin = OpenMaya.MFnPlugin( mobject )
    try:
        mplugin.registerCommand( VirtuCameraMayaPlugin.kPluginCmdName, VirtuCameraMayaPlugin.cmdCreator )
    except:
        sys.stderr.write( 'Failed to register command: ' + VirtuCameraMayaPlugin.kPluginCmdName )

def uninitializePlugin( mobject ):
    ''' Uninitialize the plug-in when Maya un-loads it. '''
    mplugin = OpenMaya.MFnPlugin( mobject )
    try:
        mplugin.deregisterCommand( VirtuCameraMayaPlugin.kPluginCmdName )
    except:
        sys.stderr.write( 'Failed to unregister command: ' + VirtuCameraMayaPlugin.kPluginCmdName )