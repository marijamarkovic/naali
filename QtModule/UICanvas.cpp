#include "StableHeaders.h"

#include "UICanvas.h"
#include "Profiler.h"

#ifndef Q_WS_WIN
#include <QX11Info>
#endif

#include <QCoreApplication>
#include <QPicture>
#include <QGraphicsSceneEvent>
#include <QUuid>
#include <QWidget>
#include <QGraphicsProxyWidget>

#include <OgreHardwarePixelBuffer.h>
#include <OgreTexture.h>
#include <OgreMaterial.h>
#include <OgreTextAreaOverlayElement.h>
#include <OgreFontManager.h> 
#include <OgrePanelOverlayElement.h>
#include <OgreTextureUnitState.h>


namespace QtUI
{

UICanvas::UICanvas(): overlay_(0),
                      container_(0),
                      dirty_(true),
                      mode_(Internal),
                      id_(QUuid::createUuid().toString()),
                      widgets_(0)
{
   
    setScene(new QGraphicsScene);
    setViewportUpdateMode(QGraphicsView::FullViewportUpdate);

    QObject::connect(this->scene(),SIGNAL(changed(const QList<QRectF>&)),this,SLOT(Dirty(true)));
}

UICanvas::UICanvas(Mode mode): overlay_(0),
                               container_(0),
                               dirty_(true),
                               mode_(mode),
                               id_(QUuid::createUuid().toString()),
                               widgets_(0)
{
 if (mode_ == External) 
 {
     setScene(new QGraphicsScene);

    // Deal canvas as normal QWidget. 
    // Currently do nothing

 }
 else if (mode_ == Internal)
 {
    setViewportUpdateMode(QGraphicsView::FullViewportUpdate);
    setScene(new QGraphicsScene);

    QObject::connect(this->scene(),SIGNAL(changed(const QList<QRectF>&)),this,SLOT(Dirty()));
 }
 else 
 {
     // Embedded
     ///todo How to deal Embedded canvases?
 }
    
}


UICanvas::~UICanvas()
{
    // Owned by QGraphicsScene-class. 

    QList<QGraphicsProxyWidget* >::iterator iter = scene_widgets_.begin();
    for (; iter != scene_widgets_.end(); ++iter)
        (*iter)=0;

    if (mode_ != External) 
    {
      QString surfaceName = QString("tex") + id_;
      Ogre::TextureManager::getSingleton().remove(surfaceName.toStdString().c_str());
      QString surfaceMaterial = QString("mat") + id_;
      Ogre::MaterialManager::getSingleton().remove(surfaceMaterial.toStdString().c_str());
      
      QString containerName = QString("con") + id_;
      Ogre::OverlayManager::getSingleton().destroyOverlayElement(containerName.toStdString().c_str());
      
      QString overlayName = QString("over") + id_;
      Ogre::OverlayManager::getSingleton().destroy(overlayName.toStdString().c_str());
     
       
    }
    container_ = 0;
    overlay_ = 0;
}

void UICanvas::AddWidget(QWidget* widget)
{
    
    switch(mode_)
    {
        case Internal:
            {
                  QGraphicsScene* scene = this->scene();
                  scene_widgets_.append(scene->addWidget(widget));
                  ++widgets_;
                  break;
            }
        case External: 
            {
              ///todo Here lies a desing flaw do it better, this does not work.   
              if ( widgets_ != 0)
               {
                   // Possible memory LEAK !!!
                    QGraphicsScene* scene = this->scene();
                    if(widgets_ == 1)
                    {
                        QWidget* viewport = this->viewport();
                        scene_widgets_.append(scene->addWidget(viewport));
                        scene_widgets_.append(scene->addWidget(widget));
                        setViewport(new QWidget);
                    }
                    else
                        scene_widgets_.append(scene->addWidget(widget));
                   
               }
               else
                   setViewport(widget);
               
               ++widgets_;

               break;
            }
        case Embedded:
            {
                ///todo How to deal Embedded ? 
                break;
            }
        default:
            break;
    }
}

void UICanvas::SetPosition(int x, int y)
{
    switch (mode_)
    {   
    case External:
        {
            move(x,y);
            break;
        }
    case Internal:
        {
            float relX = x/double(renderWindowSize_.width()), relY = y/double(renderWindowSize_.height());
            container_->setPosition(relX, relY);
           
            emit RequestArrange();
            dirty_ = true;
            break;
        }
    case Embedded:
        {
            ///todo How to deal Embedded windows?
            break;
        }
    default:
        break;

    }

}

QPoint UICanvas::MapToCanvas(int x, int y)
{
    if ( mode_ != External)
    {
        x -= container_->getLeft() * renderWindowSize_.width();
        y -= container_->getTop() * renderWindowSize_.height();
    }
     return QPoint(x,y);
}

QPointF UICanvas::GetPosition() const
{
    QPointF position;

    switch(mode_)
    {
        case External:
            {
                position = pos();
                break;
            }
        case Internal:
            {
                double width = container_->getLeft();
                double height = container_->getTop();
                
                // Calculate position in render window coordinate frame. 
                position.rx() = width * renderWindowSize_.width();
                position.ry() = height * renderWindowSize_.height();
                break;

            }
        case Embedded:
            {
                ///todo How to deal embedded canvases? 
                break;
            }
        default:
            break;

    }

    return position;
}


void UICanvas::SetCanvasSize(int width, int height)
{
    move(0, 0);
    resize(width, height);
    CreateOgreResources(width, height);
  
    // Repaint canvas. 
    dirty_ = true;
}

void UICanvas::ResizeOgreTexture(int width, int height)
{
    texture_->freeInternalResources();
    texture_->setWidth(width);
    texture_->setHeight(height);
    texture_->createInternalResources();
}

void UICanvas::CreateOgreResources(int width, int height)
{
    // If we've already created the resources, just resize the texture to a new size.
    
    if (texture_.get())
    {
        if (width == texture_->getWidth() && height == texture_->getHeight())
            return;
        ResizeOgreTexture(width, height);
        assert(overlay_);
        assert(container_);
        assert(material_.get());
        return;
    }

    QString overlayName = QString("over") + id_;
    overlay_ = Ogre::OverlayManager::getSingleton().create(overlayName.toStdString().c_str());
    
    QString containerName = QString("con") + id_;
    container_ = static_cast<Ogre::OverlayContainer*>(Ogre::OverlayManager::getSingleton()
                                     .createOverlayElement("Panel", containerName.toStdString().c_str()));

    // This is not done so currently -- tuoki 
    // Make the overlay cover 100% of the render window. Note that the UI surface will be 
    // rendered pixel perfect without stretching only if the GraphicsView surface dimension 
    // matches the render window size.
    //container_->setDimensions(1.0,1.0);

      container_->setPosition(0,0);
   

    // Add container in default overlay
    overlay_->add2D(container_);


    ///\todo Tell Ogre not to generate a mipmap chain. This texture only needs to have only one
    /// mip level.
    
    
  
   
    QString surfaceName = QString("tex") + id_;
  
    texture_ = Ogre::TextureManager::getSingleton().createManual(surfaceName.toStdString().c_str(), 
						        Ogre::ResourceGroupManager::DEFAULT_RESOURCE_GROUP_NAME, 
						        Ogre::TEX_TYPE_2D, width, height, 0, 
						        Ogre::PF_A8R8G8B8, Ogre::TU_DYNAMIC_WRITE_ONLY_DISCARDABLE);


    QString surfaceMaterial = QString("mat") + id_;
    material_ = Ogre::MaterialManager::getSingleton().create(surfaceMaterial.toStdString().c_str(),
						        Ogre::ResourceGroupManager::DEFAULT_RESOURCE_GROUP_NAME);
    
    Ogre::TextureUnitState *state = material_->getTechnique(0)->getPass(0)->createTextureUnitState();
    material_->getTechnique(0)->getPass(0)->setSceneBlending(Ogre::SBF_SOURCE_ALPHA, Ogre::SBF_ONE_MINUS_SOURCE_ALPHA);
    state->setTextureName(surfaceName.toStdString().c_str());

    // Generate pixel perfect texture. 

    float relWidth = (float)texture_->getWidth()/double(renderWindowSize_.width());
    float relHeight = (float)texture_->getHeight()/double(renderWindowSize_.height());
    container_->setDimensions(relWidth, relHeight);

    container_->setMaterialName(surfaceMaterial.toStdString().c_str());
    container_->show();
    container_->setEnabled(true);
    container_->setColour(Ogre::ColourValue(1,1,1,1));

    overlay_->show();
}

void UICanvas::Show()
{
    ///todo pending should we call show() for overlay, container?
    if ( mode_ != External)
    {
        QList<QGraphicsProxyWidget* >::iterator iter = scene_widgets_.begin();
        for (; iter != scene_widgets_.end(); ++iter)
            (*iter)->show();
           
         dirty_ = true;
        RenderSceneToOgreSurface();
    }
    else
        show();

}

void UICanvas::Hide()
{
    ///todo pending: should we call hide() for overlay, container?
    if ( mode_ != External)
        {
            QList<QGraphicsProxyWidget* >::iterator iter = scene_widgets_.begin();
            for (; iter != scene_widgets_.end(); ++iter)
                (*iter)->hide();
               
            dirty_ = true;
            RenderSceneToOgreSurface();
        }
    else
        hide();

}


void UICanvas::drawBackground(QPainter *painter, const QRectF &rect)
{
    QBrush black(Qt::transparent);
    painter->fillRect(rect, black);
}

void UICanvas::RenderSceneToOgreSurface()
{
	
	// Render if and only if scene is dirty.
	if (!dirty_ || mode_ == External)
		return;

	
    PROFILE(RenderSceneToOgre);
    
    // We draw the GraphicsView area to an offscreen QPixmap and blit that onto the Ogre GPU surface.
    QPixmap pixmap(this->size());
    {
        PROFILE(FillEmpty);
        pixmap.fill(Qt::transparent);
    }
    assert(pixmap.hasAlphaChannel());
    QImage img = pixmap.toImage();

    QPainter painter(&img);
    QRectF destRect(0, 0, pixmap.width(), pixmap.height());
    QRect sourceRect(0, 0, pixmap.width(), pixmap.height());
    {
        PROFILE(RenderUI);
        this->render(&painter, destRect, sourceRect);
    }
    assert(img.hasAlphaChannel());

    ///\todo Can optimize an extra blit away if we paint directly onto the GPU surface.

    Ogre::Box dimensions(0,0, img.rect().width(), img.rect().height());
    Ogre::PixelBox pixel_box(dimensions, Ogre::PF_A8R8G8B8, (void*)img.bits());
    {
        PROFILE(UIToOgreBlit);
        texture_->getBuffer()->blitFromMemory(pixel_box);
    }
	
    dirty_ = false;
}


void UICanvas::Render()
{
    RenderSceneToOgreSurface();	
}

}
