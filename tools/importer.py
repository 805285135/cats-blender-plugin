# MIT License

# Copyright (c) 2017 GiveMeAllYourCats

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the 'Software'), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Code author: Hotox
# Repo: https://github.com/michaeldegroot/cats-blender-plugin

import os
import bpy
import copy
import zipfile
import webbrowser
import bpy_extras.io_utils

from .. import globs
from . import armature_manual
from . import common as Common
from . import settings as Settings
from . import fbx_patch as Fbx_patch
from .common import version_2_79_or_older
from .register import register_wrap

mmd_tools_installed = False
try:
    import mmd_tools_local
    mmd_tools_installed = True
except:
    pass

current_blender_version = str(bpy.app.version[:2])[1:-1].replace(', ', '.')

# In blender 2.79 this string gets cut off after char 63, so don't go over that limit
# Bug Report: https://blender.stackexchange.com/questions/110788/file-browser-filter-not-working-correctly
#             <                                                               > Don't go outside these brackets
formats_279 = '*.pm*;*.xps;*.mesh;*.ascii;*.smd;*.qc;*.fbx;*.dae;*.vrm;*.zip'
formats = '*.pmx;*.pmd;*.xps;*.mesh;*.ascii;*.smd;*.qc;*.qci;*.vta;*.dmx;*.fbx;*.dae;*.vrm;*.zip'
format_list = formats.replace('*.', '').split(';')
zip_files = {}


@register_wrap
class ImportAnyModel(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = 'cats_importer.import_any_model'
    bl_label = 'Import Any Model'
    if version_2_79_or_older():
        bl_description = 'Import a model of any supported type.' \
                         '\n' \
                         '\nSupported types:' \
                         '\n- MMD: .pmx/.pmd' \
                         '\n- XNALara: .xps/.mesh/.ascii' \
                         '\n- Source: .smd/.qc' \
                         '\n- VRM: .vrm' \
                         '\n- FBX .fbx ' \
                         '\n- DAE: .dae ' \
                         '\n- ZIP: .zip'
    else:
        bl_description = 'Import a model of any supported type.' \
                         '\n' \
                         '\nSupported types:' \
                         '\n- MMD: .pmx/.pmd' \
                         '\n- XNALara: .xps/.mesh/.ascii' \
                         '\n- Source: .smd/.qc/.vta/.dmx' \
                         '\n- VRM: .vrm' \
                         '\n- FBX: .fbx' \
                         '\n- DAE: .dae ' \
                         '\n- ZIP: .zip'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    files = bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement, options={'HIDDEN', 'SKIP_SAVE'})
    directory = bpy.props.StringProperty(maxlen=1024, subtype='FILE_PATH', options={'HIDDEN', 'SKIP_SAVE'})

    filter_glob = bpy.props.StringProperty(default=formats_279 if version_2_79_or_older() else formats, options={'HIDDEN'})
    text1 = bpy.props.BoolProperty(
        name='IMPORTANT INFO (hover here)',
        description='If you want to modify the import settings, use the button next to the Import button.\n\n',
        default=False
    )

    def execute(self, context):
        global zip_files
        zip_files = {}
        has_zip_file = False

        Common.remove_unused_objects()

        # Make sure that the first layer is visible
        if hasattr(context.scene, 'layers'):
            context.scene.layers[0] = True

        # Save all current objects to check which armatures got added by the importer
        pre_import_objects = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']

        # Import the files using their corresponding importer
        if self.directory:
            for f in self.files:
                file_name = f.name
                self.import_file(self.directory, file_name)
                if file_name.lower().endswith('.zip'):
                    has_zip_file = True
        # If this operator is called with no directory but a filepath argument, import that
        elif self.filepath:
            print(self.filepath)
            self.import_file(os.path.dirname(self.filepath), os.path.basename(self.filepath))

        if has_zip_file:
            if not zip_files:
                Common.show_error(4, ['The selected zip file contains no importable models.'])

            # Import all models from zip files that contain only one importable model
            remove_keys = []
            for zip_path, files in copy.deepcopy(zip_files).items():
                context.scene.zip_content = zip_path + ' ||| ' + files[0]
                if len(files) == 1:
                    ImportAnyModel.extract_file()
                    remove_keys.append(zip_path)

            # Remove the models from zip file list that got already imported
            for key in remove_keys:
                zip_files.pop(key)

            # Only if a zip contains more than one model, open the zip model selection popup
            if zip_files.keys():
                bpy.ops.cats_importer.zip_popup('INVOKE_DEFAULT')

        # Create list of armatures that got added during import, select them in cats and fix their bone orientations if necessary
        arm_added_during_import = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE' and obj not in pre_import_objects]
        for armature in arm_added_during_import:
            print('Added: ', armature.name)
            bpy.context.scene.armature = armature.name
            self.fix_bone_orientations(armature)

        return {'FINISHED'}

    @staticmethod
    def import_file(directory, file_name):
        file_path = os.path.join(directory, file_name)
        file_ending = file_name.split('.')[-1].lower()

        # MMD
        if file_ending == 'pmx' or file_ending == 'pmd':
            try:
                bpy.ops.mmd_tools.import_model('EXEC_DEFAULT',
                                               files=[{'name': file_name}],
                                               directory=directory,
                                               scale=0.08,
                                               types={'MESH', 'ARMATURE', 'MORPHS'},
                                               log_level='WARNING')
            except AttributeError:
                bpy.ops.mmd_tools.import_model('INVOKE_DEFAULT')
            except (TypeError, ValueError):
                bpy.ops.mmd_tools.import_model('INVOKE_DEFAULT')

        # XNALara
        elif file_ending == 'xps' or file_ending == 'mesh' or file_ending == 'ascii':
            try:
                if version_2_79_or_older():
                    bpy.ops.xps_tools.import_model('EXEC_DEFAULT',
                                                   filepath=file_path,
                                                   colorizeMesh=False)
                else:
                    bpy.ops.xps_tools.import_model('EXEC_DEFAULT',
                                                   filepath=file_path)
            except AttributeError:
                bpy.ops.cats_importer.install_xps('INVOKE_DEFAULT')

        # Source Engine
        elif file_ending == 'smd' or file_ending == 'qc' or file_ending == 'qci' or file_ending == 'vta' or file_ending == 'dmx':
            try:
                bpy.ops.import_scene.smd('EXEC_DEFAULT',
                                         files=[{'name': file_name}],
                                         directory=directory)
            except AttributeError:
                bpy.ops.cats_importer.install_source('INVOKE_DEFAULT')

        # FBX
        elif file_ending == 'fbx':
            try:
                bpy.ops.import_scene.fbx('EXEC_DEFAULT',
                                         filepath=file_path,
                                         automatic_bone_orientation=False,  # Is true better? There are issues with True
                                         use_prepost_rot=False,
                                         use_anim=False)
            except (TypeError, ValueError):
                bpy.ops.import_scene.fbx('INVOKE_DEFAULT')
            except RuntimeError as e:
                if 'unsupported, must be 7100 or later' in str(e):
                    Common.show_error(6.2, ['The FBX file version is unsupported!',
                                            'Please use a tool such as the "Autodesk FBX Converter" to make it compatible.'])
                print(str(e))

        # VRM
        elif file_ending == 'vrm':
            try:
                bpy.ops.import_scene.vrm('EXEC_DEFAULT',
                                         filepath=file_path)
            except (TypeError, ValueError):
                bpy.ops.import_scene.vrm('INVOKE_DEFAULT')
            except AttributeError:
                bpy.ops.cats_importer.install_vrm('INVOKE_DEFAULT')

        # DAE
        elif file_ending == 'dae':
            try:
                bpy.ops.wm.collada_import('EXEC_DEFAULT',
                                          filepath=file_path,
                                          fix_orientation=True,
                                          auto_connect=True)
            except (TypeError, ValueError):
                bpy.ops.wm.collada_import('INVOKE_DEFAULT')

        # ZIP
        elif file_ending == 'zip':
            with zipfile.ZipFile(file_path, 'r') as zipObj:
                global zip_files

                # Check content of zip for importable models
                for content in zipObj.namelist():
                    content_name = os.path.basename(content)
                    content_format = content_name.split('.')[-1]
                    if content_format.lower() in format_list:
                        if not zip_files.get(file_path):
                            zip_files[file_path] = []
                        zip_files[file_path].append(content)

    @staticmethod
    def extract_file():
        zip_id = bpy.context.scene.zip_content.split(' ||| ')
        zip_path = zip_id[0]
        zip_extract_path = '.'.join(zip_path.split('.')[:-1])
        model_path = encode_str(zip_id[1])
        model_path_full = os.path.join(zip_extract_path, model_path)
        model_dir = os.path.dirname(model_path_full)
        model_file_name = os.path.basename(model_path_full)

        # Extract the
        with zipfile.ZipFile(zip_path, 'r') as zipObj:
            for member in zipObj.infolist():
                member.filename = encode_str(member.filename)
                zipObj.extract(member, path=zip_extract_path)

        ImportAnyModel.import_file(model_dir, model_file_name)

    @staticmethod
    def fix_bone_orientations(armature):
        Common.unselect_all()
        Common.set_active(armature)
        Common.switch('EDIT')

        fix_bones = True

        # Check if all the bones are pointing in the same direction
        for bone in armature.data.edit_bones:
            equal_axis_count = 0
            if bone.head[0] == bone.tail[0]:
                equal_axis_count += 1
            if bone.head[1] == bone.tail[1]:
                equal_axis_count += 1
            if bone.head[2] == bone.tail[2]:
                equal_axis_count += 1

            # If the bone points to more than one direction, don't fix the armatures bones
            if equal_axis_count < 2:
                fix_bones = False

        if fix_bones:
            Common.fix_bone_orientations(armature)
        Common.switch('OBJECT')


@register_wrap
class ZipPopup(bpy.types.Operator):
    bl_idname = "cats_importer.zip_popup"
    bl_label = "Zip Model Selection:"
    bl_description = 'Shows the models contained in the zip files'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        # Save all current objects to check which armatures got added by the importer
        pre_import_objects = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']

        # Import the file
        ImportAnyModel.extract_file()

        # Create list of armatures that got added during import, select them in cats and fix their bone orientations if necessary
        arm_added_during_import = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE' and obj not in pre_import_objects]
        for armature in arm_added_during_import:
            print('Added: ', armature.name)
            bpy.context.scene.armature = armature.name
            ImportAnyModel.fix_bone_orientations(armature)
        return {'FINISHED'}

    def invoke(self, context, event):
        dpi_value = Common.get_user_preferences().system.dpi
        return context.window_manager.invoke_props_dialog(self, width=dpi_value * 6, height=-550)

    def check(self, context):
        # Important for changing options
        return False

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        row = col.row(align=True)
        row.scale_y = 0.9
        row.label(text='Select which model you want to import')
        row = col.row(align=True)
        row.scale_y = 0.9
        row.label(text='Then confirm with OK')

        col.separator()
        row = col.row(align=True)
        row.scale_y = 1.3
        row.prop(context.scene, 'zip_content')


def get_zip_content(self, context):
    choices = []

    for zip_path, files in zip_files.items():
        for file_path in files:
            file_id = zip_path + ' ||| ' + file_path
            file_name = os.path.basename(file_path)
            zip_name = os.path.basename(zip_path)

            # 1. Will be returned by context.scene
            # 2. Will be shown in lists
            # 3. will be shown in the hover description (below description)
            choices.append((
                file_id,
                encode_str(file_name),
                'Import model "' + encode_str(file_name) + '" from the zip "' + encode_str(zip_name) + '"'))

    if len(choices) == 0:
        choices.append(('None', 'None', 'None'))

    bpy.types.Object.Enum = sorted(choices, key=lambda x: tuple(x[0].lower()))
    return bpy.types.Object.Enum


def encode_str(s):
    try:
        s = s.encode('cp437').decode('cp932')
    except UnicodeEncodeError:
        pass
    return s


@register_wrap
class ModelsPopup(bpy.types.Operator):
    bl_idname = "cats_importer.model_popup"
    bl_label = "Select which you want to import:"
    bl_description = 'Show individual import options'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        dpi_value = Common.get_user_preferences().system.dpi
        return context.window_manager.invoke_props_dialog(self, width=dpi_value * 3, height=-550)

    def check(self, context):
        # Important for changing options
        return True

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        row = col.row(align=True)
        row.scale_y = 1.3
        row.operator(ImportMMD.bl_idname)
        row.operator(ImportXPS.bl_idname)
        row = col.row(align=True)
        row.scale_y = 1.3
        row.operator(ImportSource.bl_idname)
        row.operator(ImportFBX.bl_idname)
        row = col.row(align=True)
        row.scale_y = 1.3
        row.operator(ImportVRM.bl_idname)


@register_wrap
class ImportMMD(bpy.types.Operator):
    bl_idname = 'cats_importer.import_mmd'
    bl_label = 'MMD'
    bl_description = 'Import a MMD model (.pmx/.pmd)'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        Common.remove_unused_objects()

        # Make sure that the first layer is visible
        if hasattr(context.scene, 'layers'):
            context.scene.layers[0] = True

        if not mmd_tools_installed:
            bpy.ops.cats_importer.enable_mmd('INVOKE_DEFAULT')
            return {'FINISHED'}

        try:
            bpy.ops.mmd_tools.import_model('INVOKE_DEFAULT',
                                           scale=0.08,
                                           types={'MESH', 'ARMATURE', 'MORPHS'},
                                           log_level='WARNING')
        except AttributeError:
            bpy.ops.cats_importer.enable_mmd('INVOKE_DEFAULT')
        except (TypeError, ValueError):
            bpy.ops.mmd_tools.import_model('INVOKE_DEFAULT')

        return {'FINISHED'}


@register_wrap
class ImportXPS(bpy.types.Operator):
    bl_idname = 'cats_importer.import_xps'
    bl_label = 'XNALara'
    bl_description = 'Import a XNALara model (.xps/.mesh/.ascii)'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        Common.remove_unused_objects()

        # Make sure that the first layer is visible
        if hasattr(context.scene, 'layers'):
            context.scene.layers[0] = True

        try:
            if version_2_79_or_older():
                bpy.ops.xps_tools.import_model('INVOKE_DEFAULT', colorizeMesh=False)
            else:
                bpy.ops.xps_tools.import_model('INVOKE_DEFAULT')
        except AttributeError:
            bpy.ops.cats_importer.install_xps('INVOKE_DEFAULT')

        return {'FINISHED'}


@register_wrap
class ImportSource(bpy.types.Operator):
    bl_idname = 'cats_importer.import_source'
    bl_label = 'Source'
    bl_description = 'Import a Source model (.smd/.qc/.vta/.dmx)'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        Common.remove_unused_objects()

        # Make sure that the first layer is visible
        if hasattr(context.scene, 'layers'):
            context.scene.layers[0] = True

        try:
            bpy.ops.import_scene.smd('INVOKE_DEFAULT')
        except AttributeError:
            bpy.ops.cats_importer.install_source('INVOKE_DEFAULT')

        return {'FINISHED'}


@register_wrap
class ImportFBX(bpy.types.Operator):
    bl_idname = 'cats_importer.import_fbx'
    bl_label = 'FBX'
    bl_description = 'Import a FBX model (.fbx)'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        Common.remove_unused_objects()

        # Make sure that the first layer is visible
        if hasattr(context.scene, 'layers'):
            context.scene.layers[0] = True

        try:
            bpy.ops.import_scene.fbx('INVOKE_DEFAULT',
                                     automatic_bone_orientation=False,
                                     use_prepost_rot=False,
                                     use_anim=False)
        except (TypeError, ValueError):
            bpy.ops.import_scene.fbx('INVOKE_DEFAULT')

        return {'FINISHED'}


@register_wrap
class ImportVRM(bpy.types.Operator):
    bl_idname = 'cats_importer.import_vrm'
    bl_label = 'VRM'
    bl_description = 'Import a VRM model (.vrm)'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        Common.remove_unused_objects()

        # Make sure that the first layer is visible
        if hasattr(context.scene, 'layers'):
            context.scene.layers[0] = True

        try:
            bpy.ops.import_scene.vrm('INVOKE_DEFAULT')
        except AttributeError:
            bpy.ops.cats_importer.install_vrm('INVOKE_DEFAULT')

        return {'FINISHED'}


@register_wrap
class InstallXPS(bpy.types.Operator):
    bl_idname = "cats_importer.install_xps"
    bl_label = "XPS Tools is not installed or enabled!"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        dpi_value = Common.get_user_preferences().system.dpi
        return context.window_manager.invoke_props_dialog(self, width=dpi_value * 4.5, height=-550)

    def check(self, context):
        # Important for changing options
        return True

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        # row = col.row(align=True)
        # row.label(text="The plugin 'XPS Tools' is required for this function.")
        col.separator()
        row = col.row(align=True)
        row.label(text="If it is not enabled please enable it in your User Preferences.")
        row = col.row(align=True)
        row.label(text="If it is not installed please download and install it manually.")
        col.separator()
        col.separator()
        row = col.row(align=True)
        row.label(text="Make sure to install the version for Blender " + current_blender_version, icon="INFO")
        col.separator()
        row = col.row(align=True)
        row.operator(XpsToolsButton.bl_idname, icon=globs.ICON_URL)


@register_wrap
class InstallSource(bpy.types.Operator):
    bl_idname = "cats_importer.install_source"
    bl_label = "Source Tools is not installed or enabled!"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        dpi_value = Common.get_user_preferences().system.dpi
        return context.window_manager.invoke_props_dialog(self, width=dpi_value * 4.5, height=-550)

    def check(self, context):
        # Important for changing options
        return True

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        # row = col.row(align=True)
        # row.label(text="The plugin 'Source Tools' is required for this function.")
        col.separator()
        row = col.row(align=True)
        row.label(text="If it is not enabled please enable it in your User Preferences.")
        row = col.row(align=True)
        row.label(text="If it is not installed please download and install it manually.")
        col.separator()
        col.separator()
        row = col.row(align=True)
        row.label(text="Make sure to install the version for Blender " + current_blender_version, icon="INFO")
        col.separator()
        row = col.row(align=True)
        row.operator(SourceToolsButton.bl_idname, icon=globs.ICON_URL)


@register_wrap
class InstallVRM(bpy.types.Operator):
    bl_idname = "cats_importer.install_vrm"
    bl_label = "VRM Importer is not installed or enabled!"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        dpi_value = Common.get_user_preferences().system.dpi
        return context.window_manager.invoke_props_dialog(self, width=dpi_value * 4.5, height=-550)

    def check(self, context):
        # Important for changing options
        return True

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        # row = col.row(align=True)
        # row.label(text="The plugin 'VRM Importer' is required for this function.")
        col.separator()
        row = col.row(align=True)
        row.label(text="If it is not enabled please enable it in your User Preferences.")
        row = col.row(align=True)
        row.label(text="Currently you have to select 'Testing' in the addons settings.")
        col.separator()
        row = col.row(align=True)
        row.label(text="If it is not installed please download and install it manually.")
        col.separator()
        row = col.row(align=True)
        row.operator(VrmToolsButton.bl_idname, icon=globs.ICON_URL)


@register_wrap
class EnableMMD(bpy.types.Operator):
    bl_idname = "cats_importer.enable_mmd"
    bl_label = "Mmd_tools is not enabled!"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        dpi_value = Common.get_user_preferences().system.dpi
        return context.window_manager.invoke_props_dialog(self, width=dpi_value * 4, height=-550)

    def check(self, context):
        # Important for changing options
        return True

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        row = col.row(align=True)
        row.label(text="The plugin 'mmd_tools' is required for this function.")
        row = col.row(align=True)
        row.label(text="Please restart Blender.")


# def popup_install_xps(self, context):
#     layout = self.layout
#     col = layout.column(align=True)
#
#     row = col.row(align=True)
#     row.label(text="The plugin 'XPS Tools' is required for this function.")
#     col.separator()
#     row = col.row(align=True)
#     row.label(text="If it is not enabled please enable it in your User Preferences.")
#     row = col.row(align=True)
#     row.label(text="If it is not installed please click here to download it and then install it manually.")
#     col.separator()
#     row = col.row(align=True)
#     row.operator('importer.download_xps_tools', icon=globs.ICON_URL)
#
#
# def popup_install_source(self, context):
#     layout = self.layout
#     col = layout.column(align=True)
#
#     row = col.row(align=True)
#     row.label(text="The plugin 'Blender Source Tools' is required for this function.")
#     col.separator()
#     row = col.row(align=True)
#     row.label(text="If it is not enabled please enable it in your User Preferences.")
#     row = col.row(align=True)
#     row.label(text="If it is not installed please click here to download it and then install it manually.")
#     col.separator()
#     row = col.row(align=True)
#     row.operator('importer.download_source_tools', icon=globs.ICON_URL)
#
#
# def popup_install_vrm(self, context):
#     layout = self.layout
#     col = layout.column(align=True)
#
#     row = col.row(align=True)
#     row.label(text="The plugin 'VRM Importer' is required for this function.")
#     col.separator()
#     row = col.row(align=True)
#     row.label(text="If it is not enabled please enable it in your User Preferences.")
#     row = col.row(align=True)
#     row.label(text="Currently you have to select 'Testing' in the addons settings")
#     row = col.row(align=True)
#     row.label(text="If it is not installed please click here to download it and then install it manually.")
#     col.separator()
#     row = col.row(align=True)
#     row.operator('importer.download_vrm', icon=globs.ICON_URL)


@register_wrap
class XpsToolsButton(bpy.types.Operator):
    bl_idname = 'cats_importer.download_xps_tools'
    bl_label = 'Download XPS Tools'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        webbrowser.open('https://github.com/johnzero7/XNALaraMesh')

        self.report({'INFO'}, 'XPS Tools link opened')
        return {'FINISHED'}


@register_wrap
class SourceToolsButton(bpy.types.Operator):
    bl_idname = 'cats_importer.download_source_tools'
    bl_label = 'Download Source Tools'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        webbrowser.open('https://github.com/Artfunkel/BlenderSourceTools')

        self.report({'INFO'}, 'Source Tools link opened')
        return {'FINISHED'}


@register_wrap
class VrmToolsButton(bpy.types.Operator):
    bl_idname = 'cats_importer.download_vrm'
    bl_label = 'Download VRM Importer'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        if Common.version_2_79_or_older():
            webbrowser.open('https://github.com/iCyP/VRM_IMPORTER_for_Blender2_79')
        else:
            webbrowser.open('https://github.com/iCyP/VRM_IMPORTER_for_Blender2_8')

        self.report({'INFO'}, 'VRM Importer link opened')
        return {'FINISHED'}


# Export checks
_meshes_count = 0
_tris_count = 0
_mat_list = []
_broken_shapes = []
_textures_found = False
_eye_meshes_not_named_body = []

max_mats = 4
max_tris = 70000
max_meshes_light = 2
max_meshes_hard = 8


@register_wrap
class ExportModel(bpy.types.Operator):
    bl_idname = 'cats_importer.export_model'
    bl_label = 'Export Model'
    bl_description = 'Export this model as .fbx for Unity.\n' \
                     '\n' \
                     'Automatically sets the optimal export settings'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    action = bpy.props.EnumProperty(
        items=(('CHECK', '', 'Please Ignore'),
               ('NO_CHECK', '', 'Please Ignore')))

    def execute(self, context):
        meshes = Common.get_meshes_objects()

        # Check for warnings
        if not self.action == 'NO_CHECK':
            global _meshes_count, _tris_count, _mat_list, _broken_shapes, _textures_found, _eye_meshes_not_named_body

            # Reset export checks
            _meshes_count = 0
            _tris_count = 0
            _mat_list = []
            _broken_shapes = []
            _textures_found = False
            _eye_meshes_not_named_body = []

            body_extists = False
            for mesh in meshes:
                if mesh.name == 'Body':
                    body_extists = True
                    break

            # Check for export warnings
            for mesh in meshes:
                # Check mesh count
                _meshes_count += 1

                # Check tris count
                _tris_count += len(mesh.data.polygons)

                # Check material count
                for mat_slot in mesh.material_slots:
                    if mat_slot and mat_slot.material and mat_slot.material.users and mat_slot.material.name not in _mat_list:
                        _mat_list.append(mat_slot.material.name)

                        # Check if any textures are found
                        if version_2_79_or_older():
                            if not _textures_found:
                                for tex_slot in mat_slot.material.texture_slots:
                                    if tex_slot and tex_slot.texture and tex_slot.texture.image:
                                        tex_path = bpy.path.abspath(tex_slot.texture.image.filepath)
                                        if os.path.isfile(tex_path):
                                            _textures_found = True
                                            break
                        else:
                            _textures_found = True
                            # TODO

                if Common.has_shapekeys(mesh):
                    # Check if there are broken shapekeys
                    for shapekey in mesh.data.shape_keys.key_blocks[1:]:
                        vert_count = 0
                        for vert in shapekey.data:
                            vert_count += 1
                            for coord in vert.co:
                                if coord >= 10000:
                                    _broken_shapes.append(shapekey.name)
                                    vert_count = 1000
                                    break
                            # Only check the first 10 vertices of this shapekey
                            if vert_count == 1000:
                                break

                    # Check if there are meshes with eye tracking, but are not named Body
                    if not body_extists:
                        for shapekey in mesh.data.shape_keys.key_blocks[1:]:
                            if mesh.name not in _eye_meshes_not_named_body:
                                if shapekey.name.startswith(('vrc.blink', 'vrc.lower')):
                                    _eye_meshes_not_named_body.append(mesh.name)
                                    break

            # Check if a warning should be shown
            if _meshes_count > max_meshes_light \
                    or _tris_count > max_tris \
                    or len(_mat_list) > max_mats \
                    or len(_broken_shapes) > 0 \
                    or not _textures_found and Settings.get_embed_textures()\
                    or len(_eye_meshes_not_named_body) > 0:
                bpy.ops.cats_importer.display_error('INVOKE_DEFAULT')
                return {'FINISHED'}

        # Continue if there are no errors or the check was skipped

        # Monkey patch FBX exporter again to import empty shape keys
        Fbx_patch.patch_fbx_exporter()

        # Check if copy protection is enabled
        mesh_smooth_type = 'OFF'
        protected_export = False
        for mesh in meshes:
            if protected_export:
                break
            if Common.has_shapekeys(mesh):
                for shapekey in mesh.data.shape_keys.key_blocks:
                    if shapekey.name == 'Basis Original':
                        protected_export = True
                        break
        if protected_export:
            mesh_smooth_type = 'FACE'

        # Check if textures are found and if they should be embedded
        path_mode = 'AUTO'
        if _textures_found and Settings.get_embed_textures():
            path_mode = 'COPY'

        # Open export window
        try:
            bpy.ops.export_scene.fbx('INVOKE_DEFAULT',
                                     object_types={'EMPTY', 'ARMATURE', 'MESH', 'OTHER'},
                                     use_mesh_modifiers=False,
                                     add_leaf_bones=False,
                                     bake_anim=False,
                                     apply_scale_options='FBX_SCALE_ALL',
                                     path_mode=path_mode,
                                     embed_textures=True,
                                     mesh_smooth_type=mesh_smooth_type)
        except (TypeError, ValueError):
            bpy.ops.export_scene.fbx('INVOKE_DEFAULT')
        except AttributeError:
            self.report({'ERROR'}, 'FBX Exporter not enabled! Please enable it in your User Preferences.')

        return {'FINISHED'}


@register_wrap
class ErrorDisplay(bpy.types.Operator):
    bl_idname = "cats_importer.display_error"
    bl_label = "Warning:"
    bl_options = {'INTERNAL'}

    tris_count = 0
    mat_list = []
    mat_count = 0
    meshes_count = 0
    broken_shapes = []
    textures_found = False
    eye_meshes_not_named_body = []

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        global _meshes_count, _tris_count, _mat_list, _broken_shapes, _textures_found, _eye_meshes_not_named_body
        self.meshes_count = _meshes_count
        self.tris_count = _tris_count
        self.mat_list = _mat_list
        self.mat_count = len(_mat_list)
        self.broken_shapes = _broken_shapes
        self.textures_found = _textures_found
        self.eye_meshes_not_named_body = _eye_meshes_not_named_body

        dpi_value = Common.get_user_preferences().system.dpi
        return context.window_manager.invoke_props_dialog(self, width=dpi_value * 6.1, height=-550)

    def check(self, context):
        # Important for changing options
        return True

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        if self.tris_count > max_tris:
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="Too many polygons!", icon='ERROR')
            col.separator()

            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="You have " + str(self.tris_count) + " tris in this model, but you shouldn't have more than 70,000!")
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="You should decimate before you export this model.")
            col.separator()
            col.separator()
            col.separator()

        # if self.mat_count > 10:
        #     row = col.row(align=True)
        #     row.scale_y = 0.75
        #     row.label(text="Too many materials!", icon='ERROR')
        #     col.separator()
        #
        #     row = col.row(align=True)
        #     row.scale_y = 0.75
        #     row.label(text="You have " + str(self.mat_count) + " materials on this model! (max 10)")
        #     row = col.row(align=True)
        #     row.scale_y = 0.75
        #     row.label(text="You should create a texture atlas before you export this model.")
        #     col.separator()
        #     row = col.row(align=True)
        #     row.scale_y = 0.75
        #     row.label(text="The Auto Atlas in CATS is now better and easier than ever, so please make use of it.")
        #     col.separator()
        #     col.separator()
        #     col.separator()

        if self.mat_count > max_mats:
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="Model not optimized!", icon='INFO')
            col.separator()

            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="This model has " + str(self.mat_count) + " materials!")
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="You should try to have a maximum of 4 materials on your model.")
            col.separator()
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="Creating a texture atlas in CATS is very easy, so please make use of it.")
            col.separator()
            col.separator()
            col.separator()

        if self.meshes_count > max_meshes_light:
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="Meshes not joined!", icon='ERROR')
            col.separator()

            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="This model has " + str(self.meshes_count) + " meshes!")
            col.separator()
            row = col.row(align=True)
            row.scale_y = 0.75
            if self.meshes_count <= max_meshes_hard:
                row.label(text="It is not very optimized and might cause lag for you and others.")
            else:
                row.label(text="It is extremely unoptimized and will cause lag for you and others.")
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="You should always join your meshes, it's very easy:")
            col.separator()
            row = col.row(align=True)
            row.scale_y = 1
            row.operator(armature_manual.JoinMeshes.bl_idname, text='Join Meshes', icon='AUTOMERGE_ON')
            col.separator()
            col.separator()
            col.separator()

        if self.broken_shapes:
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="Broken shapekeys!", icon='ERROR')
            col.separator()

            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="This model has " + str(len(self.broken_shapes)) + " broken shapekey(s):")
            col.separator()

            for shapekey in self.broken_shapes:
                row = col.row(align=True)
                row.scale_y = 0.75
                row.label(text="  - " + shapekey)

            col.separator()
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="You will not be able to upload this model until you fix these shapekeys.")
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="Either delete or repair them before export.")
            col.separator()
            col.separator()
            col.separator()

        if not self.textures_found and Settings.get_embed_textures():
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="No textures found!", icon='ERROR')
            col.separator()

            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="This model has no textures assigned but you have 'Embed Textures' enabled.")
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="Therefore, no textures will embedded into the FBX.")
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="This is not an issue, but you will have to import the textures manually into Unity.")
            col.separator()
            col.separator()
            col.separator()

        if len(self.eye_meshes_not_named_body) == 1:
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="Eyes not named 'Body'!", icon='ERROR')
            col.separator()

            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="The mesh '" + self.eye_meshes_not_named_body[0] + "' has Eye Tracking shapekeys but is not named 'Body'.")
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="If you want Eye Tracking to work, rename this mesh to 'Body'.")
            col.separator()
            col.separator()
            col.separator()

        elif len(self.eye_meshes_not_named_body) > 1:
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="Eyes not named 'Body'!", icon='ERROR')
            col.separator()

            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="Multiple meshes have Eye Tracking shapekeys but are not named 'Body'.")
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="Make sure that the mesh containing the eyes is named 'Body' in order")
            row = col.row(align=True)
            row.scale_y = 0.75
            row.label(text="to get Eye Tracking to work.")
            col.separator()
            col.separator()
            col.separator()

        row = col.row(align=True)
        row.operator(ExportModel.bl_idname, text='Continue to Export', icon=globs.ICON_EXPORT).action = 'NO_CHECK'
