import os
import fitz  # PyMuPDF
import base64

def pdf_to_images(pdf_path: str, out_dir: str = None, dpi: int = 200, fmt: str = "png",
                  password: str = None, transparent: bool = False, keep_images=False):
    """
    Convert all pages of a PDF to images.

    Args:
        pdf_path: Path to the input PDF.
        out_dir: Output directory (created if missing). Defaults to <pdf_stem>_pages next to the PDF.
        dpi: Resolution (dots per inch). 200–300 is good for papers.
        fmt: Image format: 'png' or 'jpg' (others supported too).
        password: PDF password if encrypted.
        transparent: If True, keeps alpha channel (PNG only).
    """
    
    if out_dir is None:
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        out_dir = os.path.join(os.path.dirname(pdf_path), f"{base}_pages")
    os.makedirs(out_dir, exist_ok=True)

    # Open document (with password if needed)
    doc = fitz.open(pdf_path)
    if doc.needs_pass:
        if not password or not doc.authenticate(password):
            raise RuntimeError("PDF is password-protected and authentication failed.")

    # Scale by dpi/72 (PDF default is 72 dpi)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    # save images to file
    n_pages = doc.page_count
    for i in range(n_pages):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat, alpha=transparent)
        fname = f"page-{i+1:03d}.{fmt.lower()}"
        fpath = os.path.join(out_dir, fname)
        pix.save(fpath)

    # read base64 representation of the images
    images = []
    for i in range(n_pages):
        fname = f"page-{i+1:03d}.{fmt.lower()}"
        fpath = os.path.join(out_dir, fname)
        with open(fpath, "rb") as file:
            data = file.read()
        images.append(base64.b64encode(data).decode('utf-8'))

    # remove the images
    if not(keep_images):
        for i in range(n_pages):
            fname = f"page-{i+1:03d}.{fmt.lower()}"
            fpath = os.path.join(out_dir, fname)
            if os.path.exists(fpath):
                os.remove(fpath)

    return images

