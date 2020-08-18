# coding: utf-8

bl_info = {
    "name": "GP clipboard",
    "description": "Copy/Cut/Paste Grease Pencil strokes to/from OS clipboard across layers and blends",
    "author": "Samuel Bernou",
    "version": (1, 0, 0),
    "blender": (2, 83, 0),
    "location": "View3D > Toolbar > Grease Pencil > GP clipboard",
    "warning": "",
    "doc_url": "https://github.com/Pullusb/GP_clipboard",
    "category": "Object" }

import bpy
import os
import mathutils
from mathutils import Vector
import json
from time import time
from operator import itemgetter
from itertools import groupby
# from pprint import pprint

def convertAttr(Attr):
    '''Convert given value to a Json serializable format'''
    if isinstance(Attr, (mathutils.Vector,mathutils.Color)):
        return Attr[:]
    elif isinstance(Attr, mathutils.Matrix):
        return [v[:] for v in Attr]
    elif isinstance(Attr,bpy.types.bpy_prop_array):
        return [Attr[i] for i in range(0,len(Attr))]
    else:
        return(Attr)

# """ def getMatrix (layer) :
#     matrix = mathutils.Matrix.Identity(4)

#     if layer.is_parented:
#         if layer.parent_type == 'BONE':
#             object = layer.parent
#             bone = object.pose.bones[layer.parent_bone]
#             matrix = bone.matrix @ object.matrix_world
#             matrix = matrix.copy() @ layer.matrix_inverse
#         else :
#             matrix = layer.parent.matrix_world * layer.matrix_inverse

#     return matrix.copy() """

# def get_object_matrix(obj):
#     return obj.matrix_world.copy()


def dump_gp_point(p, l, obj):
    '''add properties of a given points to a dic and return it'''
    pdic = {}
    #point_attr_list = ('co', 'pressure', 'select', 'strength') #select#'rna_type'
    #for att in point_attr_list:
    #    pdic[att] = convertAttr(getattr(p, att))
    if l.parent:
        mat = getMatrix(l)
        pdic['co'] = convertAttr(mat @ getattr(p,'co'))
    else:
        pdic['co'] = convertAttr(obj.matrix_world.inverted() @ getattr(p,'co'))
    pdic['pressure'] = convertAttr(getattr(p,'pressure'))
    # pdic['select'] = convertAttr(getattr(p,'select'))# need selection ? 
    pdic['strength'] = convertAttr(getattr(p,'strength'))

    ## get vertex color (long...)
    if p.vertex_color[:] != (0.0, 0.0, 0.0, 0.0):
        pdic['vertex_color'] = convertAttr(getattr(p,'vertex_color'))

    return pdic


def dump_gp_stroke_range(s, sid, l, obj):
    '''Get a grease pencil stroke and return a dic with attribute
    (points attribute being a dic of dics to store points and their attributes)
    '''

    sdic = {}
    stroke_attr_list = ('line_width',) #'select'#read-only: 'triangles'
    for att in stroke_attr_list:
        sdic[att] = getattr(s, att)
        
    ## Dump following these value only if they are non default
    if s.material_index != 0:
        sdic['material_index'] = s.material_index
    
    if s.draw_cyclic:
        sdic['draw_cyclic'] = s.draw_cyclic
    
    if s.uv_scale != 1.0:
        sdic['uv_scale'] = s.uv_scale
    
    if s.uv_rotation != 0.0:
        sdic['uv_rotation'] = s.uv_rotation
    
    if s.hardness != 1.0:
        sdic['hardness'] = s.hardness
    
    if s.uv_translation != Vector((0.0, 0.0)):
        sdic['uv_translation'] = convertAttr(s.uv_translation)

    if s.vertex_color_fill[:] != (0,0,0,0):
        sdic['vertex_color_fill'] = convertAttr(s.vertex_color_fill)

    points = []
    for pid in sid:
        points.append(dump_gp_point(s.points[pid],l,obj))
    sdic['points'] = points
    return sdic



def copycut_strokes(layers=None, copy=True, keep_empty=True):# (mayber allow filter)
    '''
    copy all visibles selected strokes on active frame
    layers can be None, a single layer object or list of layer object as filter 
    if keep_empty is False the frame is deleted when all strokes are cutted
    '''
    t0 = time()

    ### must iterate in all layers ! (since all layers are selectable / visible !)
    scene = bpy.context.scene
    obj = bpy.context.object
    gp = obj.data
    gpl = gp.layers
    # if not color:#get active color name
    #     color = gp.palettes.active.colors.active.name
    if not layers:
        #by default all visible layers
        layers = [l for l in gpl if not l.hide and not l.lock]#[]
    if not isinstance(layers, list):
        #if a single layer object is send put in a list
        layers = [layers]

    stroke_list = []#one stroke list for all layers.

    for l in layers:
        f = l.active_frame

        if f:#active frame can be None
            if not copy:
                staylist = []#init part of strokes that must survive on this layer

            for s in f.strokes:
                if s.select:
                    # separate in multiple stroke if parts of the strokes a selected.
                    sel = [i for i, p in enumerate(s.points) if p.select]
                    substrokes = []
                    for k, g in groupby(enumerate(sel), lambda x:x[0]-x[1]):
                        group = list(map(itemgetter(1), g))
                        substrokes.append(group)

                    for ss in substrokes:
                        if len(ss) > 1:#avoid copy isolated points
                            stroke_list.append(dump_gp_stroke_range(s,ss,l,obj))

                    #Cutting operation
                    if not copy:
                        maxindex = len(s.points)-1
                        if len(substrokes) == maxindex+1:#si un seul substroke, c'est le stroke entier
                            f.strokes.remove(s)
                        else:
                            neg = [i for i, p in enumerate(s.points) if not p.select]

                            staying = []
                            for k, g in groupby(enumerate(neg), lambda x:x[0]-x[1]):
                                group = list(map(itemgetter(1), g))
                                #extend group to avoid gap when cut, a bit dirty
                                if group[0] > 0:
                                    group.insert(0,group[0]-1)
                                if group[-1] < maxindex:
                                    group.append(group[-1]+1)
                                staying.append(group)

                            for ns in staying:
                                 if len(ns) > 1:
                                    staylist.append(dump_gp_stroke_range(s,ns,l,obj))
                            #make a negative list containing all last index


                    '''#full stroke version
                    # if s.colorname == color: #line for future filters
                    stroke_list.append(dump_gp_stroke(s,l))
                    #delete stroke on the fly
                    if not copy:
                        f.strokes.remove(s)
                    '''

            if not copy:
                print('in not copy')
                # delete all selected strokes...
                for s in f.strokes:
                    if s.select:
                        f.strokes.remove(s)
                # ...recreate these uncutted ones
                #pprint(staylist)
                if staylist:
                    add_multiple_strokes(staylist, l)
                #for ns in staylist:#weirdky recreate the stroke twice !
                #    add_stroke(ns, f, l)

            #if nothing left on the frame choose to leave an empty frame or delete it (let previous frame appear)
            if not copy and not keep_empty:#
                if not len(f.strokes):
                    l.frames.remove(f)



    print(len(stroke_list), 'strokes copied in', time()-t0, 'seconds')
    #print(stroke_list)
    return stroke_list



def add_stroke(s, frame, layer):
    '''add stroke on a given frame, (layer is for parentage setting)'''
    #print(3*'-',s)
    ns = frame.strokes.new()

    for att, val in s.items():
        if att not in ('points'):
            setattr(ns, att, val)
    pts_to_add = len(s['points'])
    #print(pts_to_add, 'points')#dbg


    ns.points.add(pts_to_add)
    #patch pressure 1
    pressure_flat_list = [di['pressure'] for di in s['points']] #get all pressure flatened

    if layer.is_parented:
        mat = getMatrix(layer).inverted()
        for i, pt in enumerate(s['points']):
            for k, v in pt.items():
                if k == 'co':
                    setattr(ns.points[i], k, v)
                    ns.points[i].co = mat * ns.points[i].co
                else:
                    setattr(ns.points[i], k, v)
    else:
        for i, pt in enumerate(s['points']):
            for k, v in pt.items():
                #print(k,v)
                setattr(ns.points[i], k, v)

    #patch pressure 2
    ns.points.foreach_set('pressure', pressure_flat_list)

def add_multiple_strokes(stroke_list, layer=None, use_current_frame=True):
    '''
    add a list of strokes to active frame of given layer
    if no layer specified, active layer is used
    if use_current_frame is True, a new frame will be created only if needed
    '''
    scene = bpy.context.scene
    obj = bpy.context.object
    gp = obj.data
    gpl = gp.layers

    #default: active
    if not layer:
        layer = gpl.active

    fnum = scene.frame_current
    target_frame = False
    act = layer.active_frame
    for s in stroke_list:
        if act:
            if use_current_frame or act.frame_number == fnum:
                #work on current frame if exists
                # use current frame anyway if one key exist at this scene.frame
                target_frame = act

        if not target_frame:
            #no active frame
            #or active exists but not aligned scene.current with use_current_frame disabled
            target_frame = layer.frames.new(fnum)

        add_stroke(s, target_frame, layer)
        '''
        for s in stroke_data:
            add_stroke(s, target_frame)
        '''
    print(len(stroke_list), 'strokes pasted')



##main defs
def copy_strokes_to_paperclip():
    bpy.context.window_manager.clipboard = json.dumps(copycut_strokes(copy=True, keep_empty=True))#default layers are visible one

def cut_strokes_to_paperclip():
    bpy.context.window_manager.clipboard = json.dumps(copycut_strokes(copy=False, keep_empty=True))

def paste_strokes_from_paperclip():
    #add condition to detect if clipboard contains loadable values
    add_multiple_strokes(json.loads(bpy.context.window_manager.clipboard), use_current_frame=True)#layer= layers.active


### OPERATORS

class GPCLIP_OT_copy_strokes(bpy.types.Operator):
    bl_idname = "gp.copy_strokes"
    bl_label = "GP Copy strokes"
    bl_description = "Copy strokes to str in paperclip"
    bl_options = {"REGISTER"}

    #copy = bpy.props.BoolProperty(default=True)
    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        if not context.object or not context.object.type == 'GPENCIL':
            self.report({'ERROR'},'No GP object selected')
            return {"CANCELLED"}

        t0 = time()
        #ct = check_pressure()
        strokelist = copycut_strokes(copy=True, keep_empty=True)
        if not strokelist:
            self.report({'ERROR'},'rien a copier')
            return {"CANCELLED"}
        bpy.context.window_manager.clipboard = json.dumps(strokelist)#copy=self.copy
        #if ct:
        #    self.report({'ERROR'}, "Copie OK\n{} points ont une épaisseur supérieure a 1.0 (max = {:.2f})\nCes épaisseurs seront plafonnées à 1 au 'coller'".format(ct[0], ct[1]))
        print('copy total time:', time() - t0)
        return {"FINISHED"}

class GPCLIP_OT_cut_strokes(bpy.types.Operator):
    bl_idname = "gp.cut_strokes"
    bl_label = "GP Cut strokes"
    bl_description = "Cut strokes to str in paperclip"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        if not context.object or not context.object.type == 'GPENCIL':
            self.report({'ERROR'},'No GP object selected')
            return {"CANCELLED"}

        strokelist = copycut_strokes(copy=False, keep_empty=True)#ct = check_pressure()
        if not strokelist:
            self.report({'ERROR'},'Nothing to cut')
            return {"CANCELLED"}
        bpy.context.window_manager.clipboard = json.dumps(strokelist)

        return {"FINISHED"}

class GPCLIP_OT_paste_strokes(bpy.types.Operator):
    bl_idname = "gp.paste_strokes"
    bl_label = "GP Paste strokes"
    bl_description = "paste stroke from paperclip"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        if not context.object or not context.object.type == 'GPENCIL':
            self.report({'ERROR'},'No GP object selected to paste on')
            return {"CANCELLED"}
        
        t0 = time()
        #add a validity check por the content of the paperclip (check if not data.startswith('[{') ? )
        try:
            data = json.loads(bpy.context.window_manager.clipboard)
        except:
        #:
            mess = 'Clipboard does not contain drawing data (load error)'
            self.report({'ERROR'}, mess)
            return {"CANCELLED"}

        print('data loaded', time() - t0)
        add_multiple_strokes(data, use_current_frame=True)
        print('total_time', time() - t0)

        return {"FINISHED"}


##--PANEL

class GPCLIP_PT_clipboard_ui(bpy.types.Panel):
    # bl_idname = "gp_clipboard_panel"
    bl_label = "GP Clipboard"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Gpencil"

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.operator('gp.copy_strokes', text='copy strokes', icon='COPYDOWN')
        row.operator('gp.cut_strokes', text='cut strokes', icon='PASTEFLIPUP')
        layout.operator('gp.paste_strokes', text='paste strokes', icon='PASTEDOWN')


###---TEST zone
#copy_strokes_to_paperclip()
#paste_strokes_from_paperclip()

#test direct
#li = copycut_strokes(copy=True)
#add_multiple_strokes(li, bpy.context.scene.grease_pencil.layers['correct'])


#use directly operator idname in shortcut settings :
# gp.copy_strokes
# gp.cut_strokes
# gp.paste_strokes

###---REGISTER + copy cut paste keymapping (disabled fornow)
'''
addon_keymaps = []
def register_keymaps():
    addon = bpy.context.window_manager.keyconfigs.addon
    #km = addon.keymaps.new(name = "3D View", space_type = "VIEW_3D")
    km = addon.keymaps.new(name = "Window", space_type = "EMPTY")
    # insert keymap items here
    kmi = km.keymap_items.new("gp.copy_strokes", type = "C", value = "PRESS", ctrl=True, shift=True)
    kmi = km.keymap_items.new("gp.cut_strokes", type = "X", value = "PRESS", ctrl=True, shift=True)
    kmi = km.keymap_items.new("gp.paste_strokes", type = "V", value = "PRESS", ctrl=True, shift=True)
    addon_keymaps.append(km)

def unregister_keymaps():
    wm = bpy.context.window_manager
    for km in addon_keymaps:
        for kmi in km.keymap_items:
            km.keymap_items.remove(kmi)
        wm.keyconfigs.addon.keymaps.remove(km)
    addon_keymaps.clear()
'''

classes = (
GPCLIP_OT_copy_strokes,
GPCLIP_OT_cut_strokes,
GPCLIP_OT_paste_strokes,
GPCLIP_PT_clipboard_ui,
)

def register():
    for cl in classes:
        bpy.utils.register_class(cl)
    #register_keymaps()

def unregister():
    #unregister_keymaps()
    for cl in reversed(classes):
        bpy.utils.unregister_class(cl)

if __name__ == "__main__":
    register()
