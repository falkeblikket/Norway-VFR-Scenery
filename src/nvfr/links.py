"""Directory activation without a shell or changes to Addons Linker settings."""

from __future__ import annotations

import os
from pathlib import Path

from .errors import SceneryError
from .paths import exists, is_link


def create_link(link: Path, target: Path) -> None:
    if exists(link):
        raise SceneryError(f"Activation path already exists: {link}")
    if os.name != "nt":
        link.symlink_to(target, target_is_directory=True)
        return
    # NTFS junctions do not require Developer Mode or administrator privileges.
    # FSCTL_SET_REPARSE_POINT / REPARSE_DATA_BUFFER, IO_REPARSE_TAG_MOUNT_POINT.
    import ctypes
    import struct
    from ctypes import wintypes

    target = target.resolve()
    if str(target).startswith("\\\\"):
        raise SceneryError("Junction mode requires a local drive; use direct installation for network paths")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    ioctl = kernel.DeviceIoControl
    ioctl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                      ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    ioctl.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    substitute = ("\\??\\" + str(target)).encode("utf-16-le")
    printable = str(target).encode("utf-16-le")
    path_buffer = substitute + b"\0\0" + printable + b"\0\0"
    data = struct.pack("<LHHHHHH", 0xA0000003, len(path_buffer) + 8, 0,
                       0, len(substitute), len(substitute) + 2, len(printable)) + path_buffer
    link.mkdir()
    handle = create(str(link), 0x40000000, 0, None, 3, 0x00200000 | 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        error = ctypes.WinError(ctypes.get_last_error())
        link.rmdir()
        raise SceneryError(f"Cannot create a Windows junction: {error}")
    try:
        buffer = ctypes.create_string_buffer(data)
        returned = wintypes.DWORD()
        if not ioctl(handle, 0x000900A4, buffer, len(data), None, 0, ctypes.byref(returned), None):
            raise SceneryError(f"This drive does not support junction activation: {ctypes.WinError(ctypes.get_last_error())}")
    except BaseException:
        close(handle)
        link.rmdir()
        raise
    else:
        close(handle)


def points_to(link: Path, target: Path) -> bool:
    return is_link(link) and os.path.normcase(str(link.resolve())) == os.path.normcase(str(target.resolve()))


def remove_tree(path: Path) -> None:
    """Remove a private staging tree, never the target of any junction/symlink."""
    if not exists(path):
        return
    if is_link(path):
        if os.name == "nt" and not path.is_symlink():
            path.rmdir()
        else:
            path.unlink()
    elif path.is_dir():
        for item in path.iterdir():
            remove_tree(item)
        path.rmdir()
    else:
        path.unlink()
