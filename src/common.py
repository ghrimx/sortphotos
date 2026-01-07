IMAGE_EXTENSIONS = {
    # Common
    ".jpg", ".jpeg", ".jpe",
    ".png",
    ".gif",
    ".bmp",
    ".tiff", ".tif",
    ".webp",
    ".heic", ".heif",

    # RAW formats (major brands)
    ".cr2", ".cr3",      # Canon
    ".nef", ".nrw",      # Nikon
    ".arw", ".srf", ".sr2",  # Sony
    ".dng",              # Adobe / generic RAW
    ".orf",              # Olympus
    ".rw2",              # Panasonic
    ".raf",              # Fujifilm
    ".pef", ".ptx",      # Pentax
    ".3fr",              # Hasselblad
    ".iiq",              # Phase One
    ".erf",              # Epson
    ".kdc",              # Kodak
    ".mef",              # Mamiya
    ".mos",              # Leaf
    ".srw",              # Samsung
    ".x3f",              # Sigma

    # Other photographic formats
    ".jp2", ".jpf", ".jpx", ".j2k",
    ".psd",              # Photoshop (often has metadata)
}

VIDEO_EXTENSIONS = {
    # Common
    ".mp4", ".m4v",
    ".mov",
    ".avi",
    ".mkv",
    ".wmv",
    ".flv",
    ".webm",

    # Mobile / camera
    ".3gp", ".3g2",
    ".mts", ".m2ts",     # AVCHD
    ".tod",

    # Professional / less common
    ".mpg", ".mpeg",
    ".vob",
    ".ogv",
    ".asf",
    ".rm", ".rmvb",

    # RAW / camera-specific video
    ".insv",             # Insta360
    ".lrv",              # GoPro low-res
    ".thm",              # Camera thumbnail videos
}

MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
