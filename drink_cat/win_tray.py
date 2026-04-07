"""Windows：固定 AppUserModelID，并尝试将托盘图标设为任务栏「始终显示」（非折叠区）。"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

# 固定 ID，便于系统在「通知区域图标」里识别本程序
APP_USER_MODEL_ID = "DrinkCat.DrinkCat.Application.1"
_promote_success_logged = False


def set_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception as e:
        logger.debug("SetCurrentProcessExplicitAppUserModelID: %s", e)


def _subkey_mentions_our_exe(sk) -> bool:
    import winreg

    exe = os.path.normcase(os.path.abspath(sys.executable))
    base = os.path.basename(exe).lower()
    try:
        n_vals = winreg.QueryInfoKey(sk)[1]
    except OSError:
        return False
    for j in range(n_vals):
        try:
            name, val, typ = winreg.EnumValue(sk, j)
        except OSError:
            break
        if typ in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and isinstance(val, str):
            low = val.lower()
            if base in low or exe.lower() in low or low in exe.lower():
                return True
        if typ == winreg.REG_BINARY and isinstance(val, bytes):
            for enc in ("utf-16-le", "utf-8", "mbcs"):
                try:
                    s = val.decode(enc, errors="ignore")
                    low = s.lower()
                    if base in low or exe.lower() in low:
                        return True
                except Exception:
                    pass
    return False


def try_promote_tray_icon() -> None:
    """Win10/11：在 HKCU\\Control Panel\\NotifyIconSettings 下将匹配项 isPromoted 置 1。"""
    global _promote_success_logged
    if sys.platform != "win32":
        return
    try:
        import winreg
    except ImportError:
        return
    root = r"Control Panel\NotifyIconSettings"
    access = winreg.KEY_READ | winreg.KEY_SET_VALUE
    promoted_any = False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, root, 0, access) as k:
            n_sub = winreg.QueryInfoKey(k)[0]
            for i in range(n_sub):
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                try:
                    with winreg.OpenKey(k, sub, 0, access) as sk:
                        if not _subkey_mentions_our_exe(sk):
                            continue
                        for promoted_name in ("isPromoted", "IsPromoted"):
                            try:
                                winreg.SetValueEx(sk, promoted_name, 0, winreg.REG_DWORD, 1)
                                promoted_any = True
                            except OSError:
                                pass
                except OSError:
                    continue
    except FileNotFoundError:
        logger.debug("本系统无 NotifyIconSettings，跳过托盘推广")
        return
    except OSError as e:
        logger.debug("try_promote_tray_icon: %s", e)
        return
    if promoted_any and not _promote_success_logged:
        _promote_success_logged = True
        logger.info("已尝试将 DrinkCat 托盘图标固定到任务栏主区域（若仍折叠，请手动拖出一次）")
