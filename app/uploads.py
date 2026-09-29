"""Saving technician proof photos (uploadProofPhoto() in Activity Diagram 3)."""
import os
import uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROOF_DIR = os.path.join(BASE_DIR, "static", "uploads", "proof")
# Path the browser uses, relative to the mounted /static route
PROOF_URL_PREFIX = "/static/uploads/proof"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 5 * 1024 * 1024  # 5 MB is plenty for a phone photo

os.makedirs(PROOF_DIR, exist_ok=True)


class UploadError(Exception):
    """The file was missing, the wrong type, or too big."""


def save_proof_photo(upload, ticket_id: int) -> str:
    """Store one photo and return the /static path to show it. Raises UploadError if unusable."""
    if upload is None or not upload.filename:
        raise UploadError("Choose a photo to upload.")

    extension = os.path.splitext(upload.filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadError("Photos must be JPG, PNG or WEBP.")

    contents = upload.file.read(MAX_BYTES + 1)
    if len(contents) > MAX_BYTES:
        raise UploadError("That photo is larger than 5 MB.")
    if not contents:
        raise UploadError("That file is empty.")

    # Never reuse the uploaded name: it is attacker-controlled and could collide
    filename = f"ticket{ticket_id}_{uuid.uuid4().hex}{extension}"
    with open(os.path.join(PROOF_DIR, filename), "wb") as out:
        out.write(contents)
    return f"{PROOF_URL_PREFIX}/{filename}"
