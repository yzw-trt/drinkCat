"""DrinkCat 启动脚本。"""

from __future__ import annotations

import logging

from drink_cat.app import DrinkCatApp
from drink_cat.win_tray import set_app_user_model_id


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    set_app_user_model_id()
    app = DrinkCatApp()
    raise SystemExit(app.run())


if __name__ == "__main__":
    main()
