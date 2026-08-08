# Document coordinate system

PyMuPDF coordinates use PDF points with origin at the page's top-left. Every `BoundingBox` stores `x0,y0,x1,y1,page_width,page_height` and rejects out-of-page geometry. Its normalized projection divides x coordinates by width and y coordinates by height. OCR boxes retain their rendered-page dimensions, so the same normalization rule supports later viewer overlays without pretending pixel coordinates are PDF points.
