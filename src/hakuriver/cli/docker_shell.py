# src/hakuriver/cli/docker_shell.py
import argparse
import os
import sys
import json
import toml
import asyncio
import websockets

# HakuRiver imports (assume they exist in the package)
from hakuriver.core.client import CLIENT_CONFIG
from hakuriver.utils.logger import logger


async def receive_messages(websocket):
    """Receives messages from the WebSocket and prints them."""
    logger.debug("Receive task started.")
    try:
        while True:
            message_text = await websocket.recv()
            try:
                message = json.loads(message_text)
                if message.get("type") == "output" and message.get("data") is not None:
                    # Print output directly to stdout
                    sys.stdout.write(message["data"])
                    sys.stdout.flush()
                elif message.get("type") == "error" and message.get("data") is not None:
                    logger.error(f"Received error from host: {message['data']}")
                    sys.stdout.write(f"\r\nERROR: {message['data']}\r\n")
                    sys.stdout.flush()
                else:
                    logger.warning(f"Received unknown message type: {message}")
            except json.JSONDecodeError:
                logger.warning(f"Received non-JSON message: {message_text}")
                sys.stdout.write(f"\r\nReceived non-JSON message: {message_text}\r\n")
                sys.stdout.flush()
            except Exception as e:
                logger.error(f"Error processing received message: {e}", exc_info=True)

    except websockets.exceptions.ConnectionClosedOK:
        logger.info("WebSocket connection closed cleanly.")
    except websockets.exceptions.ConnectionClosedError as e:
        logger.error(f"WebSocket connection closed with error: {e}")
    except Exception as e:
        logger.error(f"Error in receive task: {e}", exc_info=True)


async def send_input(websocket):
    """Reads from the input_queue and sends messages to the WebSocket."""
    logger.debug("Send task started.")
    try:
        while True:
            line = await asyncio.to_thread(input)
            line = (
                line.rstrip("\n") + "\n"
            )  # Ensure newline is added for terminal input
            if line == "exit\n" or line == "quit\n":
                logger.info("Exit command received. Closing WebSocket.")
                await websocket.close()
                break
            # Send the input line to the WebSocket
            message = {"type": "input", "data": line}
            await websocket.send(json.dumps(message))
    except Exception as e:
        logger.error(f"Error in send task: {e}", exc_info=True)


async def main_shell():
    """Main async function to connect and manage the WebSocket terminal."""
    parser = argparse.ArgumentParser(
        description="HakuRiver Docker Shell: Connect to a Host-side container terminal via WebSocket.",
        usage="%(prog)s [options] <container-name>",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to a custom TOML configuration file to override defaults.",
        default=None,
    )
    parser.add_argument(
        "container_name", help="Name of the Host container to connect to."
    )

    args = parser.parse_args()

    # --- Load and Apply Custom Config ---
    custom_config_data = None
    if args.config:
        config_path = os.path.abspath(args.config)
        if not os.path.exists(config_path):
            logger.error(f"Custom config file not found: {config_path}")
            sys.exit(1)
        try:
            with open(config_path, "r") as f:
                custom_config_data = toml.load(f)
            logger.info(f"Loaded custom configuration from: {config_path}")
        except (toml.TomlDecodeError, IOError) as e:
            logger.error(f"Error loading or reading config file '{config_path}': {e}")
            sys.exit(1)

    if custom_config_data:
        for key, value in custom_config_data.items():
            CLIENT_CONFIG.update_setting(key, value)

    # --- Construct WebSocket URL ---
    # Assuming Host is running on ws:// or wss:// based on its configuration/setup
    # Current HakuRiver doesn't have TLS config, so assume ws://
    ws_protocol = "ws"  # Or "wss" if Host is configured for TLS
    ws_url = f"{ws_protocol}://{CLIENT_CONFIG.host_address}:{CLIENT_CONFIG.host_port}/docker/host/containers/{args.container_name}/terminal"

    logger.info(
        f"Connecting to WebSocket terminal for container '{args.container_name}' at {ws_url}"
    )

    # --- Connect WebSocket and Manage I/O ---
    try:
        async with websockets.connect(ws_url) as websocket:
            logger.info("WebSocket connection established.")
            sys.stdout.write(
                "Connected. Press Enter to send commands. Press Ctrl+D to exit.\r\n"
            )
            sys.stdout.flush()

            # Run send and receive tasks concurrently
            await asyncio.gather(
                receive_messages(websocket),
                send_input(websocket),
                # Add a task to monitor the input thread/queue if needed for graceful exit
            )

    except websockets.exceptions.ConnectionClosed as e:
        logger.error(
            f"Connection refused by host: {e}. Is the Host running and the container name correct?"
        )
        sys.stdout.write(f"\r\nConnection refused: {e}\r\n")
    except websockets.exceptions.InvalidURI as e:
        logger.error(f"Invalid WebSocket URI: {e}. Check host address and port.")
        sys.stdout.write(f"\r\nInvalid URI: {e}\r\n")
    except websockets.exceptions.WebSocketException as e:
        logger.error(f"WebSocket error occurred: {e}")
        sys.stdout.write(f"\r\nWebSocket error: {e}\r\n")
    except Exception as e:
        logger.exception(f"An unexpected error occurred during WebSocket session: {e}")
        sys.stdout.write(f"\r\nUnexpected error: {e}\r\n")
    finally:
        logger.info("WebSocket session ended.")
        sys.stdout.write("\r\nDisconnected.\r\n")
        sys.stdout.flush()


def main():
    """Entry point wrapper for asyncio."""
    # Need to explicitly set the policy on some systems (e.g., Windows)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main_shell())


if __name__ == "__main__":
    main()
