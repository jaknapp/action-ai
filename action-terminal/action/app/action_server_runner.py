import argparse
from typing import Tuple, TypedDict
from aiohttp import web

from action.app.action_server import ActionServer, make_action_server_web_app
from action.app.action_service import ActionService


class ActionServerRunner:
    def __init__(self, app: web.Application, port: int):
        self._app = app
        self._port = port

    def run(self) -> None:
        web.run_app(self._app, host="0.0.0.0", port=self._port)


def parse_args() -> Tuple[int]:
    parser = argparse.ArgumentParser(description="Run the Action Server.")
    parser.add_argument(
        "--port",
        type=int,
        default=5001,
        help="Port to bind to (default: 5001)",
    )
    return (parser.parse_args().port,)


def main():
    action_service = ActionService()
    action_server = ActionServer(action_service)
    app = make_action_server_web_app(action_server)
    port, = parse_args()
    runner = ActionServerRunner(app, port=port)
    runner.run()


if __name__ == "__main__":
    main()
