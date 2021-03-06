"""
A gui tool for editing.

Originally was a basic proof-of-concept and a test of the Python API:
The qt integration for ui together with the manually wrapped entity-component data API
and the viewer non-qt event system for mouse events thru the py plugin system.

Later has been developed to be an actually usable editing tool, and currently is the only tool for that for Naali.

TODO (most work is in api additions on the c++ side, then simple usage here):
- local & global movement
- (WIP, needs network event refactoring) sync changes from over the net to the gui dialog: listen to scene objectupdates
  (this is needed/nice when someone else is moving the same obj at the same time,
   works correctly in slviewer, i.e. the dialogs there update on net updates)
(- list all the objects to allow selection from there)

"""

from __future__ import division

from circuits import Component
import mathutils as mu

from PythonQt.QtUiTools import QUiLoader
from PythonQt.QtCore import QFile, Qt, QRect
from PythonQt.QtGui import QVector3D
from PythonQt.QtGui import QQuaternion as QQuaternion

import rexviewer as r
import naali
from naali import renderer #naali.renderer for FrustumQuery, hopefully all ex-rexviewer things soon

try:
    window
    manipulator 
    at
except: #first run
    try:
        import window
        import manipulator
        import aligntools.align as at
    except ImportError, e:
        print "couldn't load window and manipulator:", e
else:
    window = reload(window)
    manipulator = reload(manipulator)
    at = reload(at)
    
def editable(ent): #removed this from PyEntity
    return ent.HasComponent('EC_OpenSimPrim')
    
class ObjectEdit(Component):
    EVENTHANDLED = False
 
    UPDATE_INTERVAL = 0.05 #how often the networkUpdate will be sent
    
    MANIPULATE_FREEMOVE = 0
    MANIPULATE_MOVE = 1
    MANIPULATE_SCALE = 2
    MANIPULATE_ROTATE = 3

    def __init__(self):
        self.sels = []  
        Component.__init__(self)
        self.window = window.ObjectEditWindow(self)
        self.reset_values()
        self.worldstream = r.getServerConnection()
        self.using_manipulator = False
        self.useLocalTransform = False
        self.cpp_python_handler = None
        self.left_button_down = False
        self.keypressed = False

        self.shortcuts = {
            (Qt.Key_Z, Qt.ControlModifier) : self.undo,
            (Qt.Key_Delete, Qt.NoModifier) : self.delete_object,
            (Qt.Key_L, Qt.AltModifier) : self.link_objects,
            (Qt.Key_L, Qt.ControlModifier|Qt.ShiftModifier) : self.unlink_objects,
        }

        # Connect to key pressed signal from input context
        self.edit_inputcontext = naali.createInputContext("object-edit", 100)
        self.edit_inputcontext.SetTakeMouseEventsOverQt(True)
        self.edit_inputcontext.connect('KeyPressed(KeyEvent*)', self.on_keypressed)

        # Connect to mouse events
        self.edit_inputcontext.connect('MouseScroll(MouseEvent*)', self.on_mousescroll)
        self.edit_inputcontext.connect('MouseLeftPressed(MouseEvent*)', self.on_mouseleftpressed)
        self.edit_inputcontext.connect('MouseLeftReleased(MouseEvent*)', self.on_mouseleftreleased)
        self.edit_inputcontext.connect('MouseMove(MouseEvent*)', self.on_mousemove)
        
        self.reset_manipulators()
        
        self.selection_rect = QRect()
        #rectprops = r.createUiWidgetProperty(2)
        #~ print type(rectprops), dir(rectprops)
        #print rectprops.WidgetType
        #uiprops.widget_name_ = "Selection Rect"
        
        #uiprops.my_size_ = QSize(width, height) #not needed anymore, uimodule reads it
        
        self.selection_rect_startpos = None
        
        r.c = self #this is for using objectedit from command.py

        self.selection_box_entity = None
        self.selection_box = None
        self.selection_box_inited = False
        
        # Get world building modules python handler
        self.cpp_python_handler = r.getQWorldBuildingHandler()
        if self.cpp_python_handler == None:
            r.logDebug("Could not aqquire world building service to object edit")
        else:
            # Connect signals
            self.cpp_python_handler.connect('ActivateEditing(bool)', self.on_activate_editing)
            self.cpp_python_handler.connect('ManipulationMode(int)', self.on_manupulation_mode_change)
            self.cpp_python_handler.connect('RemoveHightlight()', self.deselect_all)
            self.cpp_python_handler.connect('RotateValuesToNetwork(int, int, int)', self.changerot_cpp)
            self.cpp_python_handler.connect('ScaleValuesToNetwork(double, double, double)', self.changescale_cpp)
            self.cpp_python_handler.connect('PosValuesToNetwork(double, double, double)', self.changepos_cpp)
            self.cpp_python_handler.connect('CreateObject()', self.create_object)
            self.cpp_python_handler.connect('DuplicateObject()', self.duplicate)
            self.cpp_python_handler.connect('DeleteObject()', self.delete_object)
            # Pass widgets
            self.cpp_python_handler.PassWidget("Mesh", self.window.mesh_widget)
            self.cpp_python_handler.PassWidget("Animation", self.window.animation_widget)
            self.cpp_python_handler.PassWidget("Sound", self.window.sound_widget)
            self.cpp_python_handler.PassWidget("Materials", self.window.materialTabFormWidget)
            self.cpp_python_handler.PassWidget("Align", self.window.align_widget)

            # Check if build mode is active, required on python restarts
            self.on_activate_editing(self.cpp_python_handler.IsBuildingActive())
            
    def on_keypressed(self, k):
        trigger = (k.keyCode, k.modifiers)
        if self.windowActive:
            # update manipulator for constant size
            self.manipulator.show_manipulator(self.sels)
            # check to see if a shortcut we understand was pressed, if so, trigger it
            if trigger in self.shortcuts:
                self.keypressed = True
                self.shortcuts[trigger]()

    def on_mousescroll(self, m):
        if self.windowActive:
            self.manipulator.show_manipulator(self.sels)
        
    def reset_values(self):
        self.left_button_down = False
        self.sel_activated = False #to prevent the selection to be moved on the intial click
        self.prev_mouse_abs_x = 0
        self.prev_mouse_abs_y = 0
        self.dragging = False
        self.time = 0
        self.keypressed = False
        self.windowActive = False
        self.windowActiveStoredState = None
        self.canmove = False
        #self.selection_box = None
        self.selection_rect_startpos = None
    
    def reset_manipulators(self):
        self.manipulatorsInit = False
        self.manipulators = {}
        self.manipulators[self.MANIPULATE_MOVE] =  manipulator.MoveManipulator(self)
        self.manipulators[self.MANIPULATE_SCALE] =  manipulator.ScaleManipulator(self)
        self.manipulators[self.MANIPULATE_FREEMOVE] =  manipulator.FreeMoveManipulator(self)
        self.manipulators[self.MANIPULATE_ROTATE] =  manipulator.RotationManipulator(self)
        self.manipulator = self.manipulators[self.MANIPULATE_FREEMOVE]
 
    def baseselect(self, ent):
        ent, children = self.parental_check(ent)
        
        self.sel_activated = False
        self.worldstream.SendObjectSelectPacket(ent.Id)
        self.highlight(ent)
        self.ec_selected(ent)
        self.sound_ruler(ent)
        self.window.selected(ent, False, self.has_multiple_selected_entities())
        self.change_manipulator(self.MANIPULATE_FREEMOVE)
        
        return ent, children
        
    def parental_check(self, ent):
        children = []
        
        while 1:
            try:
                qprim = ent.prim
            except AttributeError:
                # we come here when parent has no EC_opensimprim component
                break

            if qprim.ParentId != 0:
                #~ r.logInfo("Entity had a parent, lets pick that instead!")
                # get the parent entity, and if it is editable set it to ent.
                # on next loop we get prim from it and from that we get children.
                temp_ent = naali.getEntity(qprim.ParentId)
                if not editable(temp_ent):
                    # not a prim, so not selecting all children
                    break
                else:
                    ent = temp_ent
            else:
                #~ r.logInfo("Entity had no parent, maybe it has children?")
                # either we get children or not :) But this is the 'parent' in either case
                children = qprim.GetChildren()
                break
        return ent, children
        
    def select(self, ent):        
        self.deselect_all()
        ent, children = self.baseselect(ent)
        self.sels.append(ent)
        self.canmove = True
        self.highlightChildren(children)

    def multiselect(self, ent):
        self.sels.append(ent)
        ent, children = self.baseselect(ent)
        self.highlightChildren(children)
    
    def highlightChildren(self, children):
        for child_id in children:
            child = naali.getEntity(int(child_id))
            self.highlight(child)
            self.sound_ruler(child)
            
    def deselect(self, ent, valid=True):
        if valid: #the ent is still there, not already deleted by someone else
            self.remove_highlight(ent)
            self.remove_sound_ruler(ent)
            self.remove_selected(ent)
        if ent in self.sels:
            self.sels.remove(ent)
            self.worldstream.SendObjectDeselectPacket(ent.Id)

    def deselect_all(self):
        if len(self.sels) > 0:
            for ent in self.sels:
                self.remove_highlight(ent)
                self.remove_sound_ruler(ent)
                self.remove_selected(ent)
                try:
                    if self.worldstream.IsConnected():
                        self.worldstream.SendObjectDeselectPacket(ent.Id)
                except ValueError:
                    r.logInfo("objectedit.deselect_all: entity doesn't exist anymore")
            self.sels = []
           
            self.hide_manipulator()

            self.prev_mouse_abs_x = 0
            self.prev_mouse_abs_y = 0
            self.canmove = False
            self.window.deselected()
            
    def highlight(self, ent):
        try:
            ent.highlight
        except AttributeError:
            ent.GetOrCreateComponentRaw("EC_Highlight")

        h = ent.highlight
    
        if not h.IsVisible():
            h.Show()
        else:
            r.logInfo("objectedit.highlight called for an already hilited entity: %d" % ent.Id)

    # todo rename to something more sane, or check if this can be merged with def select() elsewhere
    def ec_selected(self, ent):
        try:
            s = ent.selected
        except AttributeError:
            s = ent.GetOrCreateComponentRaw("EC_Selected")
            
    def remove_selected(self, ent):
        try:
            s = ent.selected
        except:
            try:
                r.logInfo("objectedit.remove_selected called for a non-selected entity: %d" % ent.Id)
            except ValueError:
                r.logInfo("objectedit.remove_selected called, but entity already removed")
        else:
            ent.RemoveComponentRaw(s)

    def remove_highlight(self, ent):
        try:
            h = ent.highlight
        except AttributeError:
            try:
                r.logInfo("objectedit.remove_highlight called for a non-hilighted entity: %d" % ent.Id)
            except ValueError:
                r.logInfo("objectedit.remove_highlight called, but entity already removed")
        else:
            ent.RemoveComponentRaw(h)

    def sound_ruler(self, ent):
        if ent.prim and ent.prim.SoundID and ent.prim.SoundID not in (u'', '00000000-0000-0000-0000-000000000000'):
            try:
                sr = ent.GetOrCreateComponentRaw('EC_SoundRuler')
            except:
                # what to do? no soundruler O.o
                return

            sr = ent.soundruler
            sr.SetVolume(ent.prim.SoundVolume)
            sr.SetRadius(ent.prim.SoundRadius)
            sr.Show()
            sr.UpdateSoundRuler()

    def remove_sound_ruler(self, ent):
        try:
            if ent.prim and ent.prim.SoundID and ent.prim.SoundID not in (u'', '00000000-0000-0000-0000-000000000000'):
                try:
                    sr = ent.soundruler
                except AttributeError:
                    r.logInfo("objectedit.remove_sound_ruler called for an object without one: %d" % ent.Id)
                else:
                    ent.RemoveComponentRaw(sr)
        except AttributeError:
            r.logInfo("objectedit.remove_sound_ruler: entity already removed. Prim doesn't exist anymore")

    def change_manipulator(self, id):
        newmanipu = self.manipulators[id]
        if newmanipu.NAME != self.manipulator.NAME:
            #r.logInfo("was something completely different")
            self.manipulator.hide_manipulator()
            self.manipulator = newmanipu
        self.manipulator.show_manipulator(self.sels)
    
    def hide_manipulator(self):
        self.manipulator.hide_manipulator()
        
    def get_selected_object_ids(self):
        ids = []
        for ent in self.sels:
            qprim = ent.prim
            children = qprim.GetChildren()
            for child_id in children:
                #child =  naali.getEntity(int(child_id))
                id = int(child_id)
                if id not in ids:
                    ids.append(id)
            ids.append(ent.Id)
        return ids
    
    def link_objects(self):
        ids = self.get_selected_object_ids()
        self.worldstream.SendObjectLinkPacket(ids)
        self.deselect_all()
        
    def unlink_objects(self):
        ids = self.get_selected_object_ids()
        self.worldstream.SendObjectDelinkPacket(ids)
        self.deselect_all()

    def init_selection_box(self):
        self.selection_box_entity = naali.createEntity()
        self.selection_box = self.selection_box_entity.GetOrCreateComponentRaw('EC_SelectionBox')
        self.selection_box.Hide()
        self.selection_box_inited = True

    def on_mouseleftpressed(self, mouseinfo):
        if not self.windowActive:
            return

        if mouseinfo.IsItemUnderMouse():
            return

        if not self.selection_box_inited:
            self.init_selection_box()

        if mouseinfo.HasShiftModifier() and not mouseinfo.HasCtrlModifier() and not mouseinfo.HasAltModifier():
            self.on_multiselect(mouseinfo)
            return
            
        self.drag_started(mouseinfo) #need to call this to enable working dragging
        self.left_button_down = True

        results = []
        results = r.rayCast(mouseinfo.x, mouseinfo.y)
        ent = None
        if results is not None and results[0] != 0:
            id = results[0]
            ent = naali.getEntity(id)

        if not self.manipulatorsInit:
            self.manipulatorsInit = True
            for manipulator in self.manipulators.values():
                manipulator.init_visuals()


        if ent is not None and self.valid_id(ent.Id):
            if editable(ent):
                r.eventhandled = self.EVENTHANDLED
               
                if self.active is None or self.active.Id != ent.Id: #a diff ent than prev sel was changed  
                    if self.valid_id(ent.Id):
                        if not ent in self.sels:
                            self.select(ent)

                elif self.active.Id == ent.Id: #canmove is the check for click and then another click for moving, aka. select first, then start to manipulate
                    self.canmove = True
        else:
            if ent is not None and self.manipulator.compareIds(ent.Id): # don't start selection box when manipulator is hit
                self.manipulator.initManipulation(ent, results, self.sels)
                self.using_manipulator = True
            else:
                self.selection_rect_startpos = (mouseinfo.x, mouseinfo.y)
                self.selection_box.Show()
                self.canmove = False
                self.deselect_all()
            
    def drag_started(self, mouseinfo):
        width, height = renderer.GetWindowWidth(), renderer.GetWindowHeight()
        normalized_width = 1 / width
        normalized_height = 1 / height
        mouse_abs_x = normalized_width * mouseinfo.x
        mouse_abs_y = normalized_height * mouseinfo.y
        self.prev_mouse_abs_x = mouse_abs_x
        self.prev_mouse_abs_y = mouse_abs_y

    def on_mouseleftreleased(self, mouseinfo):
        self.left_button_down = False
        if self.selection_rect_startpos is not None:
            hits = renderer.FrustumQuery(self.selection_rect) #the wish

            for hit in hits:
                if not self.valid_id(hit.Id): continue
                if hit in self.sels: continue
                try:
                    self.multiselect(hit)
                except ValueError:
                    pass

            self.selection_rect_startpos = None
            self.selection_rect.setRect(0,0,0,0)
            self.selection_box.Hide()
        if self.active: #XXX something here?
            if self.sel_activated and self.dragging:
                for ent in self.sels:
                    #~ print "LeftMouseReleased, networkUpdate call"
                    parent, children = self.parental_check(ent)
                    r.networkUpdate(ent.Id)
                    for child in children:
                        child_id = int(child)
                        r.networkUpdate(child_id)
            
            self.sel_activated = True
        
        if self.dragging:
            self.dragging = False
            
        self.manipulator.stop_manipulating()
        self.manipulator.show_manipulator(self.sels)
        self.using_manipulator = False
        
    
    def selection_rect_dimensions(self, mouseinfo):
        rectx = self.selection_rect_startpos[0]
        recty = self.selection_rect_startpos[1]
        
        rectwidth = (mouseinfo.x - rectx)
        rectheight = (mouseinfo.y - recty)
        
        if rectwidth < 0:
            rectx += rectwidth
            rectwidth *= -1
            
        if rectheight < 0:
            recty += rectheight
            rectheight *= -1
            
        return rectx, recty, rectwidth, rectheight

    def on_multiselect(self, mouseinfo):
        if self.windowActive:           
            results = []
            results = r.rayCast(mouseinfo.x, mouseinfo.y)
            ent = None
            if results is not None and results[0] != 0:
                id = results[0]
                ent = naali.getEntity(id)
                
            if ent is not None:                
                if self.valid_id(ent.Id):
                    if not ent in self.sels:
                        self.multiselect(ent)
                    else:
                        self.deselect(ent)
                    self.canmove = True
            
    def valid_id(self, id):
        if id != 0 and id > 50: #terrain seems to be 4 (on w.r.o:9000) and scene objects always big numbers, so > 50 should be good, though randomly created local entities can get over 50...
            if id != naali.getUserAvatar().Id: #XXX add other avatar id's check
                if not self.manipulator.compareIds(id):
                    return True
        return False
    
    def has_multiple_selected_entities(self):
        entities = naali.getDefaultScene().GetEntitiesWithComponentRaw('EC_Selected')
        return len(entities)>1

    def on_mousemove(self, mouseinfo):
        """Handle mouse move events. When no button is pressed, just check
        for hilites necessity in manipulators. When a button is pressed, handle
        drag logic."""
        if self.windowActive:
            if self.left_button_down:
                self.on_mousedrag(mouseinfo)
            else:
                # check for manipulator hilites
                results = []
                results = r.rayCast(mouseinfo.x, mouseinfo.y)
                if results is not None and results[0] != 0:
                    id = results[0]
                    
                    if self.manipulator.compareIds(id):
                        self.manipulator.highlight(results)
                else:
                    self.manipulator.resethighlight()

    def on_mousedrag(self, mouseinfo):
        """dragging objects around - now free movement based on view,
        dragging different axis etc in the manipulator to be added."""
        if self.windowActive:
            width, height = renderer.GetWindowWidth(), renderer.GetWindowHeight()
            normalized_width = 1 / width
            normalized_height = 1 / height
            mouse_abs_x = normalized_width * mouseinfo.x
            mouse_abs_y = normalized_height * mouseinfo.y
                                
            movedx = mouse_abs_x - self.prev_mouse_abs_x
            movedy = mouse_abs_y - self.prev_mouse_abs_y
            
            if self.left_button_down:
                if self.selection_rect_startpos is not None:
                    rectx, recty, rectwidth, rectheight = self.selection_rect_dimensions(mouseinfo)
                    self.selection_rect.setRect(rectx, recty, rectwidth, rectheight)
                    self.selection_box.SetBoundingBox(self.selection_rect)
                else:
                    ent = self.active
                    if ent is not None and self.sel_activated and self.canmove:
                        self.dragging = True

                        self.manipulator.manipulate(self.sels, movedx, movedy)
                        
                        self.prev_mouse_abs_x = mouse_abs_x
                        self.prev_mouse_abs_y = mouse_abs_y
                        
                        self.window.update_guivals(ent)
   
    def on_inboundnetwork(self, evid, name):
        #print "editgui got an inbound network event:", id, name
        return False

    def undo(self):
        ent = self.active
        if ent is not None:
            self.worldstream.SendObjectUndoPacket(ent.prim.FullId)
            self.window.update_guivals(ent)
            self.modified = False
            self.deselect_all()

    #~ def redo(self):
        #~ #print "redo clicked"
        #~ ent = self.sel
        #~ if ent is not None:
            #~ #print ent.uuid
            #~ #worldstream = r.getServerConnection()
            #~ self.worldstream.SendObjectRedoPacket(ent.uuid)
            #~ #self.sel = []
            #~ self.update_guivals()
            #~ self.modified = False
            
    def duplicate(self):
        #print "duplicate clicked"
        #ent = self.active
        #if ent is not None:
        for ent in self.sels:
            self.worldstream.SendObjectDuplicatePacket(ent.Id, ent.prim.UpdateFlags, 1, 1, 0) #nasty hardcoded offset
        
    def create_object(self):
        avatar = naali.getUserAvatar()
        pos = avatar.placeable.Position

        # TODO determine what is right in front of avatar and use that instead
        start_x = pos.x() + .7
        start_y = pos.y() + .7
        start_z = pos.z()

        self.worldstream.SendObjectAddPacket(start_x, start_y, start_z)

    def delete_object(self):
        if self.active is not None:
            for ent in self.sels:
                #r.logInfo("deleting " + str(ent.Id))
                ent, children = self.parental_check(ent)
                #for child_id in children:
                #    child = naali.getEntity(int(child_id))
                #    #~ self.worldstream.SendObjectDeRezPacket(child.Id, r.getTrashFolderId())
                #~ if len(children) == 0:
                self.worldstream.SendObjectDeRezPacket(ent.Id, r.getTrashFolderId())
                #~ else:
                    #~ r.logInfo("trying to delete a parent, need to fix this!")
            
            self.manipulator.hide_manipulator()
            #self.hideSelector()        
            self.deselect_all()
            self.sels = []
            
    def float_equal(self, a,b):
        if abs(a-b)<0.01:
            return True
        else:
            return False

    def changepos(self, i, v):
        #XXX NOTE / API TODO: exceptions in qt slots (like this) are now eaten silently
        #.. apparently they get shown upon viewer exit. must add some qt exc thing somewhere
        ent = self.active
        if ent is not None:
            qpos = QVector3D(ent.placeable.Position)
            if i == 0:
                qpos.setX(v)
            elif i == 1:
                qpos.setY(v)
            elif i == 2:
                qpos.setZ(v)

            ent.placeable.Position = qpos
            ent.network.Position = qpos
            self.manipulator.moveTo(self.sels)

            if not self.dragging:
                r.networkUpdate(ent.Id)
            self.modified = True
            
    def changescale(self, i, v):
        ent = self.active
        if ent is not None:
            qscale = ent.placeable.Scale
            #oldscale = list((qscale.x(), qscale.y(), qscale.z()))
            scale = list((qscale.x(), qscale.y(), qscale.z()))
                
            if not self.float_equal(scale[i],v):
                scale[i] = v
#                if self.window.mainTab.scale_lock.checked:
#                    #XXX BUG does wrong thing - the idea was to maintain aspect ratio
#                    diff = scale[i] - oldscale[i]
#                    for index in range(len(scale)):
#                        #print index, scale[index], index == i
#                        if index != i:
#                            scale[index] += diff
                
                ent.placeable.Scale = QVector3D(scale[0], scale[1], scale[2])
                
                if not self.dragging:
                    r.networkUpdate(ent.Id)
                self.modified = True
                
    def changerot(self, i, v):
        #XXX NOTE / API TODO: exceptions in qt slots (like this) are now eaten silently
        #.. apparently they get shown upon viewer exit. must add some qt exc thing somewhere
        #print "pos index %i changed to: %f" % (i, v[i])
        ent = self.active
        if ent is not None and not self.using_manipulator:
            ort = mu.euler_to_quat(v)
            ent.placeable.Orientation = ort
            ent.network.Orientation = ort
            if not self.dragging:
                r.networkUpdate(ent.Id)
                
            self.modified = True

    def changerot_cpp(self, x, y, z):
        self.changerot(0, (x, y, z))
        
    def changescale_cpp(self, x, y, z):
        self.changescale(0, x)
        self.changescale(1, y)
        self.changescale(2, z)
        
    def changepos_cpp(self, x, y, z):
        self.changepos(0, x)
        self.changepos(1, y)
        self.changepos(2, z)
        
    def getActive(self):
        if len(self.sels) > 0:
            ent = self.sels[-1]
            return ent
        return None
        
    active = property(getActive)
    
    def on_exit(self):
        r.logInfo("Object Edit exiting..")
        # remove selection box component and entity
        if self.selection_box_entity is not None and self.selection_box_entity:
            self.selection_box_entity.RemoveComponentRaw(self.selection_box)
            naali.removeEntity(self.selection_box_entity)
        # Connect to key pressed signal from input context
        self.edit_inputcontext.disconnectAll()
        self.deselect_all()
        # Disconnect cpp python handler
        self.cpp_python_handler.disconnect('ActivateEditing(bool)', self.on_activate_editing)
        self.cpp_python_handler.disconnect('ManipulationMode(int)', self.on_manupulation_mode_change)
        self.cpp_python_handler.disconnect('RemoveHightlight()', self.deselect_all)
        self.cpp_python_handler.disconnect('RotateValuesToNetwork(int, int, int)', self.changerot_cpp)
        self.cpp_python_handler.disconnect('ScaleValuesToNetwork(double, double, double)', self.changescale_cpp)
        self.cpp_python_handler.disconnect('PosValuesToNetwork(double, double, double)', self.changepos_cpp)
        self.cpp_python_handler.disconnect('CreateObject()', self.create_object)
        self.cpp_python_handler.disconnect('DuplicateObject()', self.duplicate)
        self.cpp_python_handler.disconnect('DeleteObject()', self.delete_object)
        # Clean widgets
        self.cpp_python_handler.CleanPyWidgets()
        r.logInfo(".. done")

    def on_hide(self, shown):
        self.windowActive = shown
        if self.windowActive:
            self.sels = []
            try:
                self.manipulator.hide_manipulator()
            except RuntimeError, e:
                r.logDebug("on_hide: scene not found")
            else:
                self.deselect_all()
        else:
            self.deselect_all()
 
    def on_activate_editing(self, activate):
        r.logDebug("on_active_editing")
        # Restore stored state when exiting build mode
        if activate == False and self.windowActiveStoredState != None:
            self.windowActive = self.windowActiveStoredState
            self.windowActiveStoredState = None
            if self.windowActive == False:
                self.deselect_all()
                for ent in self.sels:
                    self.remove_highlight(ent)
                    self.remove_sound_ruler(ent)

        # Store the state before build scene activated us
        if activate == True and self.windowActiveStoredState == None:
            self.windowActiveStoredState = self.windowActive
            self.windowActive = True
        
    def on_manupulation_mode_change(self, mode):
        self.change_manipulator(mode)
            
    def update(self, time):
        #print "here", time
        if self.windowActive:
            self.time += time
            if self.sels:
                ent = self.active
                #try:
                #    ent.prim
                #except ValueError:
                #that would work also, but perhaps this is nicer:
                s = naali.getDefaultScene()
                if not s.HasEntityId(ent.Id):
                    #my active entity was removed from the scene by someone else
                    self.deselect(ent, valid=False)
                    return
                    
                if self.time > self.UPDATE_INTERVAL:
                    try:
                        arr_pos = self.manipulator.getManipulatorPosition()
                        ent_pos = ent.placeable.Position
                        self.time = 0 #XXX NOTE: is this logic correct?
                        if arr_pos != ent_pos:
                            self.manipulator.moveTo(self.sels)
                    except RuntimeError, e:
                        r.logDebug("update: scene not found")
   
    def on_logout(self, id):
        r.logInfo("Object Edit resetting due to logout")
        self.deselect_all()
        self.sels = []
        self.selection_box = None
        self.reset_values()
        self.reset_manipulators()

    def on_worldstreamready(self, id):
        r.logInfo("Worldstream ready")
        self.worldstream = r.getServerConnection()
        return False # return False, we don't want to consume the event and not have it for others available
        
    def setUseLocalTransform(self, local):
        self.useLocalTransform = local

    def do_align_axis_x_first(self):
        at.align_on_x_first(self.sels)

    def do_align_axis_x_last(self):
        at.align_on_x_last(self.sels)

    def do_align_axis_x_spaced(self):
        at.align_on_x_spaced(self.sels)

    def do_align_axis_x_random(self):
        at.align_random_x(self.sels)

    def do_align_axis_y_first(self):
        at.align_on_y_first(self.sels)

    def do_align_axis_y_last(self):
        at.align_on_y_last(self.sels)

    def do_align_axis_y_spaced(self):
        at.align_on_y_spaced(self.sels)

    def do_align_axis_y_random(self):
        at.align_random_y(self.sels)

    def do_align_axis_z_first(self):
        at.align_on_z_first(self.sels)

    def do_align_axis_z_last(self):
        at.align_on_z_last(self.sels)

    def do_align_axis_z_spaced(self):
        at.align_on_z_spaced(self.sels)

    def do_align_axis_z_random(self):
        at.align_random_z(self.sels)

    def do_align_random(self):
        at.align_random(self.sels)
