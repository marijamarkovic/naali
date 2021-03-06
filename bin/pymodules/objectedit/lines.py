# This module contains the handling of the different input widget sets
# that are available in world building tools.

import rexviewer as r
from PythonQt.QtGui import QLineEdit

PRIMTYPES_REVERSED = {
    "Material": "45",
    "Texture": "0"
}

# Base class for having an edit line with drag and drop capabilities.
class DragDroppableEditline(QLineEdit):
    def __init__(self, mainedit, *args):
        self.mainedit = mainedit #to be able to query the selected entity at drop
        QLineEdit.__init__(self, *args)
        self.old_text = ""
        
        self.combobox = None #throw into another class...
        self.buttons = []
        self.spinners = []
        self.index = None 

    def accept(self, ev):
        return ev.mimeData().hasFormat("application/vnd.inventory.item")
    #XXX shouldn't accept any items, but just the right asset types
    #or better yet: accept drop to anywhere in the window and 
    #determine what to do based on the type?

    def dragEnterEvent(self, ev):
        if self.accept(ev):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev):
        if self.accept(ev):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        print "Got meshid_drop:", self, ev
        if not self.accept(ev):
            return

        mimedata = ev.mimeData()
        invitem = str(mimedata.data("application/vnd.inventory.item"))

        #some_qbytearray_thing = invitem[:4] #struct.unpack('i', 
        data = invitem[4:].decode('utf-16-be') #XXX how it happens to be an win: should be explicitly encoded to latin-1 or preferrably utf-8 in the c++ inventory code
        #print data
        asset_type, inv_id, inv_name, asset_ref = data.split(';')

        ent = self.mainedit.active #is public so no need for getter, can be changed to a property if needs a getter at some point
        if ent is not None:
            self.doaction(ent, asset_type, inv_id, inv_name, asset_ref)

            self.update_text(inv_name)

        ev.acceptProposedAction()

    def update_text(self, name):
        """called also from main/parent.select() when sel changed"""
        
        ent = self.mainedit.active
        if ent is not None:
            self.text = name #XXX add querying inventory for name
        else:
            self.text = "N/A"
            
        self.old_text = name
        self.deactivateButtons()

    def doaction(self, ent, asset_type, inv_id, inv_name, asset_ref):
        pass
        
    def applyAction(self):
        print self, "applyAction (not implemented yet in this class) !"
    
    def cancelAction(self):
        #print self, "cancelAction!"
        self.text = self.old_text
        self.deactivateButtons()
        
    def deactivateButtons(self):
        for button in self.buttons:
            button.setEnabled(False)

# Edit line for mesh assigning
class MeshAssetidEditline(DragDroppableEditline):
    def doaction(self, ent, asset_type, inv_id, inv_name, asset_ref):
        #print "doaction in MeshAssetidEditline-class..."
        applymesh(ent, asset_ref)
        self.deactivateButtons()
    
    # Apply the action (click through button)
    def applyAction(self):
        #print self, "applyAction!"
        ent = self.mainedit.active
        if ent is not None:
            applymesh(ent, self.text)
            self.deactivateButtons()
            self.mainedit.window.animation_widget.show()
            self.mainedit.window.animationline.deactivateButtons()

# Sound asset edit line handling
class SoundAssetidEditline(DragDroppableEditline):
    def doaction(self, ent, asset_type, inv_id, inv_name, asset_ref):
        self.deactivateButtons()
    
    def applyAction(self):
        ent = self.mainedit.active
        if ent is not None:
            applyaudio(ent, self.text, self.spinners[0].value, self.spinners[1].value)
            self.deactivateButtons()

    def update_soundradius(self, radius):
        ent = self.mainedit.active
        if ent is not None:
            self.spinners[0].setValue(radius)
        else:
            self.spinners[0].setValue(3.0)

    def update_soundvolume(self, volume):
        ent = self.mainedit.active
        if ent is not None:
            self.spinners[1].setValue(volume)
        else:
            self.spinners[1].setValue(3.0)

class AnimationAssetidEditline(DragDroppableEditline):
    def doaction(self, ent, asset_type, inv_id, inv_name, asset_ref):
        self.deactivateButtons()
    
    def applyAction(self):
        ent = self.mainedit.active
        if ent is not None:
            applyanimation(ent, self.text, self.combobox.currentText, self.spinners[0].value) 
            self.deactivateButtons()
            self.mainedit.window.update_animation(ent)

    def update_animationrate(self, rate):
        ent = self.mainedit.active
        if ent is not None:
            self.spinners[0].setValue(rate)
        else:
            self.spinners[0].setValue(1.0)
        
# Material/Texture edit line handling
class UUIDEditLine(DragDroppableEditline):
    def doaction(self, ent, asset_type, inv_id, inv_name, asset_ref):
        matinfo = (asset_type, asset_ref)
        self.applyMaterial(ent, matinfo, self.name)
        self.deactivateButtons()

    def applyMaterial(self, ent, matinfo, index):
        qprim = ent.prim
        mats = qprim.Materials
        mats[index] = matinfo
        qprim.Materials = mats
        r.sendRexPrimData(ent.Id)
        
    def applyAction(self):
        ent = self.mainedit.active
        if self.combobox is not None and ent is not None:
            qprim = ent.prim
            mats = qprim.Materials
            asset_type_text = self.combobox.currentText
            
            asset_type = PRIMTYPES_REVERSED[asset_type_text] #need to encode to something else?
            mats[self.index]  = (asset_type, self.text)
            qprim.Materials = mats
            
            r.sendRexPrimData(ent.Id)
            
            self.deactivateButtons()
            
def applymesh(ent, meshuuid):
    try:
        ent.mesh
    except AttributeError:
        ent.prim.MeshID = meshuuid #new
    else:
        ent.mesh.SetMesh(meshuuid)        
    r.sendRexPrimData(ent.Id)

def applyanimation(ent, animationuuid, animationname, animationrate):
    ent.prim.AnimationPackageID = animationuuid
    ent.prim.AnimationName = animationname
    ent.prim.AnimationRate = animationrate

    try:
        ent.mesh
    except:
        return

    try:
        ac = ent.animationcontroller
    except:
        ent.GetOrCreateComponentRaw('EC_AnimationController')
        ac = ent.animationcontroller
        ac.SetNetworkSyncEnabled(False)
        ac.SetMeshEntity(ent.mesh)
    r.sendRexPrimData(ent.Id)

# Apply new audio settings as set in UI.
def applyaudio(ent, audiouuid, soundRadius, soundVolume):
    # First try to get an existing sound component (EC_AttachedSound)
    try:
        ent.sound
    except AttributeError:
        # It didn't exist, so we only set the ID, radius and volume.
        # The network roundtrip will ensure that a sound component 
        # (EC_AttachedSound) will be created
        ent.prim.SoundID = audiouuid
        ent.prim.SoundRadius = soundRadius
        ent.prim.SoundVolume = soundVolume
    else:
        ent.prim.SoundID = audiouuid
        ent.prim.SoundRadius = soundRadius
        ent.prim.SoundVolume = soundVolume
        ent.sound.SetSound(audiouuid, ent.placeable.Position, ent.prim.SoundRadius, ent.prim.SoundVolume)
    sound_ruler_update(ent)
    r.sendRexPrimData(ent.Id)

def sound_ruler_update(ent):
    # Check first to see if a sound ruler exists
    # and create it if there was none found
    sr = ent.GetOrCreateComponentRaw("EC_SoundRuler")
    sr = ent.soundruler
    sr.Show()
    sr.UpdateSoundRuler()
