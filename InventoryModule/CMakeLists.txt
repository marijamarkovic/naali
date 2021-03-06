# Define target name and output directory
init_target (InventoryModule OUTPUT modules/core)

# Define source files
file (GLOB CPP_FILES *.cpp)
file (GLOB H_FILES *.h)
file (GLOB XML_FILES *.xml)
file (GLOB MOC_FILES InventoryModule.h AbstractInventoryDataModel.h AbstractInventoryItem.h
    InventoryAsset.h InventoryFolder.h InventoryItemModel.h InventoryWindow.h OpenSimInventoryDataModel.h
    WebdavInventoryDataModel.h InventoryTreeView.h ItemPropertiesWindow.h UploadProgressWindow.h
    InventoryService.h)
file (GLOB RESOURCE_FILES resource/*.qrc)
set (SOURCE_FILES ${CPP_FILES} ${H_FILES})

# Qt4 Moc files to subgroup "CMake Moc"
MocFolder ()

# Qt4 Wrap
QT4_WRAP_CPP(MOC_SRCS ${MOC_FILES})
QT4_WRAP_UI(UI_SRCS ${UI_FILES})
QT4_ADD_RESOURCES(RESOURCE_SRCS ${RESOURCE_FILES})

set (FILES_TO_TRANSLATE ${FILES_TO_TRANSLATE} ${H_FILES} ${CPP_FILES} PARENT_SCOPE)

add_definitions (-DINVENTORY_MODULE_EXPORTS)

if (UISERVICE_TEST)
    add_definitions (-DUISERVICE_TEST)
endif ()

use_package (BOOST)
use_package (POCO)
use_package (CURL)
use_package (XMLRPC)
use_package (OPENJPEG)
use_package (OGRE)
use_package (QT4)
use_package (PYTHON)
use_package (PYTHON_QT)

if (APPLE)
    use_modules (Core Foundation Interfaces RexCommon ProtocolUtilities ProtocolModuleOpenSim ProtocolModuleTaiga HttpUtilities AssetModule)
else()
    use_modules (Core Foundation Interfaces RexCommon ProtocolUtilities HttpUtilities AssetModule)
endif()

if (NOT UISERVICE_TEST)
    use_modules (UiModule)
endif ()

build_library (${TARGET_NAME} SHARED ${SOURCE_FILES} ${MOC_SRCS} ${RESOURCE_SRCS})

link_package (BOOST)
link_package (POCO)
link_package (CURL)
link_package (XMLRPC)
link_package (OPENJPEG)
link_ogre()
link_package (QT4)
link_package (PYTHON_QT)

if (APPLE)
    link_modules (Core Foundation Interfaces RexCommon ProtocolUtilities ProtocolModuleOpenSim ProtocolModuleTaiga HttpUtilities)
else()
    link_modules (Core Foundation Interfaces RexCommon ProtocolUtilities HttpUtilities)
endif()

if (NOT UISERVICE_TEST)
    link_modules (UiModule)
endif ()

SetupCompileFlagsWithPCH()
CopyModuleXMLFile()

final_target ()
