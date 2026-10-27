import AppKit
let output = CommandLine.arguments[1]
let size = 1024
let image = NSImage(size: NSSize(width:size,height:size))
image.lockFocus()
NSColor(calibratedRed:0.065,green:0.09,blue:0.065,alpha:1).setFill()
NSBezierPath(roundedRect:NSRect(x:16,y:16,width:992,height:992),xRadius:220,yRadius:220).fill()
let gradient=NSGradient(starting:NSColor(calibratedRed:0.22,green:0.3,blue:0.17,alpha:1),ending:NSColor(calibratedRed:0.08,green:0.12,blue:0.075,alpha:1))!
gradient.draw(in:NSBezierPath(ovalIn:NSRect(x:155,y:155,width:714,height:714)),angle:65)
NSColor(calibratedRed:0.75,green:0.93,blue:0.57,alpha:1).setStroke()
let ring=NSBezierPath(ovalIn:NSRect(x:175,y:175,width:674,height:674)); ring.lineWidth=18;ring.stroke()
let inner=NSBezierPath(ovalIn:NSRect(x:255,y:255,width:514,height:514));inner.lineWidth=3;inner.stroke()
let text="87" as NSString
let attrs:[NSAttributedString.Key:Any]=[.font:NSFont.systemFont(ofSize:260,weight:.ultraLight),.foregroundColor:NSColor(calibratedRed:0.75,green:0.93,blue:0.57,alpha:1)]
let textsize=text.size(withAttributes:attrs)
text.draw(at:NSPoint(x:(1024-textsize.width)/2,y:(1024-textsize.height)/2+18),withAttributes:attrs)
NSColor(calibratedRed:0.75,green:0.93,blue:0.57,alpha:1).setFill()
NSBezierPath(ovalIn:NSRect(x:498,y:295,width:28,height:28)).fill()
image.unlockFocus()
let rep=NSBitmapImageRep(data:image.tiffRepresentation!)!
try rep.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:output))
