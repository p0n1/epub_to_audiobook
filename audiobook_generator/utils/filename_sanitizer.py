import hashlib
import os
import unicodedata


def _detect_name_max(path):
    """Return NAME_MAX for filesystem containing path, or sane default."""
    directory = path if os.path.isdir(path) else os.path.dirname(path) or "."
    try:
        name_max = os.pathconf(directory, "PC_NAME_MAX")
        if isinstance(name_max, int) and name_max >= 64:
            return name_max
    except (OSError, AttributeError, ValueError):
        pass
    return 255


def _sanitize_base_name(name):
    """Normalize and sanitize text for use in filename (no extension)."""
    if not name:
        return ""

    # Unicode normalize
    name = unicodedata.normalize("NFKC", name)

    # Replace path separators and control chars
    forbidden = set('<>:"/\\|?*\n\r\t')
    sanitized_chars = []
    for ch in name:
        if ch in forbidden:
            sanitized_chars.append("_")
        else:
            # On Windows, also avoid names ending with space or dot, handle later
            sanitized_chars.append(ch)

    sanitized = "".join(sanitized_chars)

    sanitized = " ".join(sanitized.split())
    sanitized = sanitized.replace(" ", "_")
    sanitized = sanitized.strip(" .")

    return sanitized or "untitled"


def make_safe_filename(
    title, idx, output_dir, ext, reserve=16, collision_check=True
):
    """
    Build filesystem-safe filename for given title and chapter index.

    - Uses NAME_MAX (if available) for output_dir.
    - Produces cross-platform safe filenames.
    - Truncates by UTF-8 bytes to respect filesystem limits.
    - Adds a short hash on truncation for stability.
    - Raises RuntimeError on collision if collision_check is True.
    """
    if not ext:
        raise ValueError("Extension must be non-empty")
    if not ext.startswith("."):
        ext = "." + ext

    name_max = _detect_name_max(output_dir)

    prefix = ""
    if idx is not None:
        prefix = f"{idx:04d}_"

    base = _sanitize_base_name(title)

    # Use real or typical filename length limit
    effective_name_max = max(64, min(name_max, 255))

    prefix_bytes = prefix.encode("utf-8")
    ext_bytes = ext.encode("utf-8")

    if len(prefix_bytes) + len(ext_bytes) + 8 >= effective_name_max:
        raise RuntimeError(
            "Cannot construct safe filename: prefix and extension are too long "
            "for filesystem limits."
        )

    max_base_bytes = effective_name_max - len(prefix_bytes) - len(ext_bytes) - reserve
    if max_base_bytes <= 0:
        raise RuntimeError(
            "Cannot construct safe filename: no space left for base name "
            "under filesystem limits."
        )

    base_bytes = base.encode("utf-8")
    if len(base_bytes) <= max_base_bytes:
        return prefix + base + ext

    truncated_bytes = base_bytes[:max_base_bytes]
    while truncated_bytes and (truncated_bytes[-1] & 0b11000000) == 0b10000000:
        truncated_bytes = truncated_bytes[:-1]

    truncated_base = truncated_bytes.decode("utf-8", errors="ignore").rstrip("._- ")
    if not truncated_base:
        truncated_base = "chapter"

    h = hashlib.sha1(base_bytes).hexdigest()[:8]
    candidate = "%s%s_%s%s" % (prefix, truncated_base, h, ext)

    if len(candidate.encode("utf-8")) > effective_name_max:
        minimal = "%s%s%s" % (prefix, h, ext)
        if len(minimal.encode("utf-8")) > effective_name_max:
            raise RuntimeError(
                "Cannot construct safe filename: even minimal hashed name exceeds "
                "filesystem limits."
            )
        candidate = minimal

    if collision_check:
        full_path = os.path.join(output_dir, candidate)
        if os.path.exists(full_path):
            raise RuntimeError(
                "Filename collision detected for '%s'. Adjust make_safe_filename "
                "strategy." % full_path
            )

    return candidate