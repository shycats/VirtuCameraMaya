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

import maya.cmds as cmds
import xml.etree.ElementTree as et
import os

class VirtuCameraMayaConfig(object):
    # Constants
    _WINDOW_SIZE = (800,600)
    _LANG_PY = 1
    _LANG_MEL = 2
    _SAMPLE_PY = '# SAMPLE CODE\n# Duplicates the camera selected in VirtuCamera\n# Tip: %SELCAM% will be replaced by the path to the camera transform\n\nimport maya.cmds as cmds\n\ncam_transform = %SELCAM%\ncmds.duplicate(cam_transform)'
    _SAMPLE_MEL = '// SAMPLE CODE\n// Duplicates the camera selected in VirtuCamera\n// Tip: %SELCAM% will be replaced by the path to the camera transform\n\n$cam_transform = %SELCAM%;\nduplicate $cam_transform;\n'

    # Show existing UI if exists
    def __new__(cls, *args, **kwargs):
        window = 'VirtuCameraMayaConfigWindow'
        if cmds.window(window, q=True, exists=True):
            cmds.showWindow(window)
            return None
        else:
            return super(VirtuCameraMayaConfig, cls).__new__(cls, *args, **kwargs)

    def __init__(self, config_file_path, saved_callback):
        self.config_file_path = config_file_path
        self._saved_callback = saved_callback
        self._init_vars()
        self._start_ui()
        self._load_config()
        self._update_ui_from_cache()
        self._update_enable_state_ui()

    def _init_vars(self):
        self._script_count = 0
        self._last_script_num = 0
        self._self_updating_label = False
        self._last_label = ''
        self._script_code_cache = []
        self._script_lang_cache = []
        self._script_label_cache = []

    def _load_config(self):
        if not os.path.isfile(self.config_file_path):
            return
        tree = et.ElementTree()
        try:
            with open(self.config_file_path,'r') as file:
                tree.parse(file)
        except:
            cmds.confirmDialog(title="Error", message='Error reading config file', button='Ok', defaultButton='Ok')
        
        config = tree.getroot()
        scripts = config[0]
        self._script_count = len(scripts)
        if self._script_count > 0:
            for script in scripts:
                self._script_label_cache.append(script.get('label'))
                self._script_lang_cache.append(int(script.get('lang')))
                script_code = script.text
                if script_code == None:
                    script_code = ''
                self._script_code_cache.append(script_code)
            self._set_script_num_ui(1, 1, self._script_count)

    def _save_config(self):
        config = et.Element('virtuCameraConfig')
        scripts = et.SubElement(config, 'scripts')
        for i in range(len(self._script_code_cache)):
            script = et.SubElement(scripts, 'script'+str(i))
            script.set('label', self._script_label_cache[i])
            script.set('lang', str(self._script_lang_cache[i]))
            script.text = self._script_code_cache[i]
        tree = et.ElementTree(config)
        try:
            with open(self.config_file_path,'w') as savefile:
                tree.write(savefile)
        except:
            cmds.confirmDialog(title="Error", message='Error saving config file, make sure you have write permission in the plug-in folder', button='Ok', defaultButton='Ok')
            self._enable_control(self._ui_save)

    def _cache_pos(self):
        return self._get_script_num_ui() - 1

    def _add_cache_entry(self):
        cache_pos = self._cache_pos()
        self._script_code_cache.insert(cache_pos, self._SAMPLE_PY)
        self._script_label_cache.insert(cache_pos, '')
        self._script_lang_cache.insert(cache_pos, self._LANG_PY)

    def _remove_cache_entry(self):
        cache_pos = self._cache_pos()
        self._script_code_cache.pop(cache_pos)
        self._script_label_cache.pop(cache_pos)
        self._script_lang_cache.pop(cache_pos)

    def _update_cache(self):
        cache_pos = self._last_script_num - 1
        if cache_pos < 0:
            return
        code = self._get_script_code_ui()
        label = self._get_label_ui()
        lang = self._get_lang_ui()
        self._script_code_cache[cache_pos] = code
        self._script_label_cache[cache_pos] = label
        self._script_lang_cache[cache_pos] = lang

    def _update_ui_from_cache(self):
        cache_pos = self._cache_pos()
        code = ''
        label = ''
        lang = self._LANG_PY
        if cache_pos >= 0:
            code = self._script_code_cache[cache_pos]
            label = self._script_label_cache[cache_pos]
            lang = self._script_lang_cache[cache_pos]
        self._set_script_code_ui(code)
        self._set_label_ui(label)
        self._set_lang_ui(lang)

    def _enable_control(self, control):
        cmds.control(control, edit=True, enable=True)

    def _disable_control(self, control):
        cmds.control(control, edit=True, enable=False)

    def _zero_script_count_ui(self):
        self._disable_control(self._script_num_ui)
        self._enable_control(self._new_bt_ui)
        self._disable_control(self._rem_bt_ut)
        self._disable_control(self._label_ui)
        self._disable_control(self._lang_ui)
        self._disable_control(self._code_lb_ui)
        self._disable_control(self._ui_sfield)

    def _one_script_count_ui(self):
        self._disable_control(self._script_num_ui)
        self._enable_control(self._new_bt_ui)
        self._enable_control(self._rem_bt_ut)
        self._enable_control(self._label_ui)
        self._enable_control(self._lang_ui)
        self._enable_control(self._code_lb_ui)
        self._enable_control(self._ui_sfield)

    def _mid_script_count_ui(self):
        self._enable_control(self._script_num_ui)
        self._enable_control(self._new_bt_ui)
        self._enable_control(self._rem_bt_ut)
        self._enable_control(self._label_ui)
        self._enable_control(self._lang_ui)
        self._enable_control(self._code_lb_ui)
        self._enable_control(self._ui_sfield)

    def _full_script_count_ui(self):
        self._enable_control(self._script_num_ui)
        self._disable_control(self._new_bt_ui)
        self._enable_control(self._rem_bt_ut)
        self._enable_control(self._label_ui)
        self._enable_control(self._lang_ui)
        self._enable_control(self._code_lb_ui)
        self._enable_control(self._ui_sfield)

    def _update_enable_state_ui(self):
        if self._script_count == 0:
            self._zero_script_count_ui()
        elif self._script_count == 1:
            self._one_script_count_ui()
        elif self._script_count == 99:
            self._full_script_count_ui()
        else:
            self._mid_script_count_ui()

    def _get_script_code_ui(self):
        return cmds.scrollField(self._ui_sfield, query=True, text=True)

    def _set_script_code_ui(self, text):
        cmds.scrollField(self._ui_sfield, edit=True, text=text)

    def _get_script_num_ui(self):
        return cmds.intSliderGrp(self._script_num_ui, query=True, value=True)

    def _set_script_num_ui(self, num, min_num, max_num):
        cmds.intSliderGrp(self._script_num_ui, edit=True, minValue=min_num, maxValue=max_num, fieldMinValue=min_num, fieldMaxValue=max_num, value=num)
        self._last_script_num = num

    def _get_lang_ui(self):
        return cmds.radioButtonGrp(self._lang_ui, query=True, select=True)

    def _set_lang_ui(self, lang):
        cmds.radioButtonGrp(self._lang_ui, edit=True, select=lang)

    def _get_label_ui(self):
        return cmds.textFieldGrp(self._label_ui, query=True, text=True)

    def _set_label_ui(self, text):
        self._self_updating_label = True
        cmds.textFieldGrp(self._label_ui, edit=True, text=text)
        self._self_updating_label = False
        self._last_label = text

    def _increase_script_count(self):
        self._script_count += 1
        script_num = self._get_script_num_ui()
        script_num += 1
        self._set_script_num_ui(script_num, 1, self._script_count)

    def _decrease_script_count(self):
        self._script_count -= 1
        if self._script_count == 0:
            min_val = 0
        else:
            min_val = 1
        script_num = self._get_script_num_ui()
        script_num -= 1
        self._set_script_num_ui(script_num, min_val, self._script_count)

    def _new_script_ui(self, caller=None):
        self._update_cache()
        self._increase_script_count()
        self._add_cache_entry()
        self._update_ui_from_cache()
        self._update_enable_state_ui()
        self._enable_control(self._ui_save)
        

    def _remove_script_ui(self, caller=None):
        self._remove_cache_entry()
        self._decrease_script_count()
        self._update_ui_from_cache()
        self._update_enable_state_ui()
        self._enable_control(self._ui_save)

    def _label_changed_ui(self, caller=None):
        if self._self_updating_label:
            return
        label = self._get_label_ui()
        prev_label = self._last_label
        if len(label) > 9:
            label = label[:9]
        label = label.replace('%', '')
        self._set_label_ui(label)
        if label != prev_label:
            self._enable_control(self._ui_save)

    def _script_number_changed_ui(self, caller=None):
        self._update_cache()
        self._last_script_num = self._get_script_num_ui()
        self._update_ui_from_cache()

    def _languaje_changed_ui(self, caller=None):
        lang = self._get_lang_ui()
        script_code = self._get_script_code_ui()

        if lang == self._LANG_PY and script_code == self._SAMPLE_MEL:
            self._set_script_code_ui(self._SAMPLE_PY)
        elif lang == self._LANG_MEL  and script_code == self._SAMPLE_PY:
            self._set_script_code_ui(self._SAMPLE_MEL)
        self._enable_control(self._ui_save)

    def _code_changed_ui(self, caller=None):
        self._enable_control(self._ui_save)

    def _save_ui(self, caller=None):
        self._disable_control(self._ui_save)
        self._update_cache()
        self._save_config()
        self._saved_callback()

    def _revert_ui(self):
        self._set_script_num_ui(self._last_script_num, 1, self._script_count)
        self._enable_control(self._ui_save)
            

    def _close_ui(self, caller=None):
        not_saved = cmds.control(self._ui_save, query=True, enable=True)
        if not_saved:
            result = cmds.confirmDialog( title='Warning', message='Config not saved', button=['Save', "Don't Save", 'Cancel'], defaultButton='Save', cancelButton='Cancel', dismissString='Cancel' )
            if result == 'Save':
                self._save_ui()
            elif result == 'Cancel':
                self._update_cache()
                cmds.evalDeferred(self._start_ui)
                cmds.evalDeferred(self._revert_ui)
                cmds.evalDeferred(self._update_ui_from_cache)
                cmds.evalDeferred(self._update_enable_state_ui)
                

    def _start_ui(self):
        # Remove size preference to force the window calculate its size
        windowName = 'VirtuCameraMayaConfigWindow'
        cmds.windowPref(windowName, remove=True)

        self._ui_window = cmds.window('VirtuCameraMayaConfigWindow', width=self._WINDOW_SIZE[0], height=self._WINDOW_SIZE[1], menuBarVisible=False, titleBar=True, visible=True, sizeable=True, closeCommand=self._close_ui, title='VirtuCamera Configuration')
        form_lay = cmds.formLayout(width=505, height=300)
        col_lay = cmds.columnLayout(adjustableColumn=True, columnAttach=('both', 0), width=465)
        cmds.text(label='Custom Scripts', align='left')
        cmds.separator(height=15, style='none')
        cmds.rowLayout(numberOfColumns=3, columnWidth3=(600, 80, 80), adjustableColumn=1, columnAttach=[(1, 'both', 0), (2, 'both', 0), (3, 'both', 0)])
        self._script_num_ui = cmds.intSliderGrp(field=True, label='Script Number', minValue=0, maxValue=1, fieldMinValue=0, fieldMaxValue=1, value=0, dragCommand=self._script_number_changed_ui, enable=False)
        self._new_bt_ui = cmds.button(label='New', command=self._new_script_ui)
        self._rem_bt_ut = cmds.button(label='Remove', command=self._remove_script_ui, enable=False)
        cmds.setParent('..')
        self._label_ui = cmds.textFieldGrp(label='Button Label', textChangedCommand=self._label_changed_ui, enable=False)
        self._lang_ui = cmds.radioButtonGrp(label='Language', labelArray2=['Python', 'MEL'], numberOfRadioButtons=2, select=self._LANG_PY, changeCommand=self._languaje_changed_ui, enable=False)
        self._code_lb_ui = cmds.text(label='Script Code', align='left', enable=False)
        cmds.setParent('..')
        self._ui_sfield = cmds.scrollField(editable=True, wordWrap=False, keyPressCommand=self._code_changed_ui, enable=False)
        col_lay2 = cmds.columnLayout(adjustableColumn=True, columnAttach=('both', 0), width=465)
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(680, 80), adjustableColumn=1, columnAttach=[(1, 'both', 0), (2, 'both', 0)])
        cmds.separator(style='none')
        self._ui_save = cmds.button(label='Save', width=80, command=self._save_ui, enable=False)
        cmds.setParent('..')
        cmds.setParent('..')
        cmds.formLayout(form_lay, edit=True, attachForm=[(col_lay, 'top', 20), (col_lay, 'left', 20), (col_lay, 'right', 20), (self._ui_sfield, 'left', 20), (self._ui_sfield, 'right', 20), (col_lay2, 'bottom', 20), (col_lay2, 'left', 20), (col_lay2, 'right', 20)], attachControl=[(self._ui_sfield, 'top', 0, col_lay), (self._ui_sfield, 'bottom', 15, col_lay2)])
        cmds.setParent('..')
        cmds.showWindow(self._ui_window)


